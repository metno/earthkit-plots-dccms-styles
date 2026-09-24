"""
Translate the earthkit-plots DCCMS style library into a Magics style library.

Output goes into ``share/magics/styles/dccms`` -- a vendored copy of the stock
ECMWF library from https://github.com/ecmwf/magics -- following the layout that
Magics uses for ``share/magics/styles/<library>/``:

* ``styles.json``        - style name -> Magics visual definition. The DCCMS
                           definitions are **merged into** the stock ones; the
                           576 upstream entries are left byte-for-byte intact.
* ``dccms_<param>.json`` - a list of parameter entries, each matching data on
                           its metadata and listing the style names for it.
* ``coastlines.json``    - map decoration (coastlines, borders, grid, land,
                           sea), i.e. the Magics theme named ``dccms``.

plus ``share/magics/dccms_units-rules.json``, a unit-conversion fragment that
belongs beside Magics' own ``units-rules.json`` rather than in a style library.

Naming: ``styles.json`` and ``coastlines.json`` are fixed names that Magics
looks up by path, so they cannot be prefixed. Parameter files are found by
scanning the directory, so they carry a ``dccms_`` prefix and are named after
the shortName they actually match, which keeps them from colliding with the
stock library's ``2t.json``, ``tp_interval.json`` and friends.

Running this repeatedly is safe: the DCCMS block in ``styles.json`` is replaced
rather than appended to.

Usage (requires earthkit-plots and matplotlib)::

    python tools/earthkit_to_magics.py

Colours are resolved through earthkit-plots itself (``Style.to_matplotlib_kwargs``)
rather than copied verbatim from the YAML, so that a named matplotlib colormap
such as ``Spectral_r`` is expanded into the very same per-interval colours which
earthkit-plots would draw.
"""

import json
import pathlib
import re

import matplotlib.colors as mcolors
import yaml
from earthkit.plots import styles as ekp_styles

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "earthkit_plots_dccms_styles"
SHARE = ROOT / "share" / "magics"
OUT = SHARE / "styles" / "dccms"

# Every DCCMS style name and parameter filename starts with this.
PREFIX = "dccms_"

# Magics can only convert to a unit for which its installation carries a rule
# in share/magics/units-rules.json. Stock Magics has no m s**-1 -> km/h rule, so
# asking for it would silently plot m s**-1 data against a km h**-1 scale. The
# m s**-1 style is therefore listed first for wind speed, even though DCCMS
# marks km h**-1 as optimal. See share/magics/dccms_units-rules.json and the
# library README.
STYLE_ORDER_OVERRIDES = {
    "wind-speed-at-10m": [
        "WIND_SPEED_AT_10M_IN_METERS_PER_SECOND",
        "WIND_SPEED_AT_10M_IN_KM_PER_HOUR",
    ],
}

# earthkit style id -> (the stock parameter file this identity extends,
#                       eccharts-style layer name, units Magics converts to)
#
# The DCCMS styles are folded into the stock library's own parameter files
# rather than shipped beside them, so that exactly one record matches any given
# field. The file named here is the fallback owner: criteria that name a
# paramId go to whichever record already claims it (see extend_stock_files),
# and everything else lands here.
PARAMS = {
    "near-surface-air-temperature": ("2t.json", "2t", "C"),
    "dew-point-temperature": ("2t_dewpoint.json", "2t_dewpoint", "C"),
    "sea-surface-temperature": ("sst.json", "sst", "C"),
    "mean-sea-level-pressure": ("msl.json", "msl", "hPa"),
    "total-precipitation": ("tp_interval.json", "tp_interval", "mm"),
    "relative-humidity": ("rh1000.json", "rh1000", None),
    "cloud-cover": ("lcc.json", "lcc", None),
    "wind-speed-at-10m": ("wind_speed.json", "wind_speed", None),
    "vertical-velocity-at-100m": ("700w.json", "700w", None),
}

# earthkit style name -> Magics style name
STYLE_NAMES = {
    "NEAR_SURFACE_AIR_TEMPERATURE_IN_CELSIUS": "dccms_sh_2t_fM4t50i2",
    "DEW_POINT_TEMPERATURE_IN_CELSIUS": "dccms_sh_dpt_fM12t46i2",
    "SEA_SURFACE_TEMPERATURE_IN_CELSIUS": "dccms_sh_sst_fM1t30i1",
    "SEA_SURFACE_TEMPERATURE_IN_KELVIN": "dccms_sh_sst_f272t300i1",
    "MEAN_SEA_LEVEL_PRESSURE_IN_HPA": "dccms_ct_msl_i4",
    "MEAN_SEA_LEVEL_PRESSURE_IN_PA": "dccms_ct_msl_i400_pa",
    "TOTAL_PRECIPITATION_IN_MM": "dccms_sh_tp_f0t200lst",
    "RELATIVE_HUMIDITY": "dccms_sh_r_f0t100i5",
    "CLOUD_COVER": "dccms_sh_cloud_f0t1i01",
    "WIND_SPEED_AT_10M_IN_KM_PER_HOUR": "dccms_sh_ws_f0t110lst",
    "WIND_SPEED_AT_10M_IN_METERS_PER_SECOND": "dccms_sh_ws_f0t31lst",
    "VERTICAL_VELOCITY_AT_100M_IN_KMH": "dccms_sh_w_fM20t15lst",
}

# Magics has no notion of matplotlib's "extend": values outside the level list
# are simply left unshaded. To keep the earthkit-plots appearance, the level
# list is padded with a sentinel bound one full range beyond each end, shaded
# with the colour earthkit-plots uses for its under/over triangle.
EXTEND_PAD = 1.0


def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f)


def fmt_number(value):
    """Format a level for a Magics ``/``-separated list."""
    if value == int(value):
        return str(int(value))
    return repr(round(float(value), 6))


def fmt_colour(rgba):
    r, g, b = (round(float(c), 4) for c in rgba[:3])
    alpha = round(float(rgba[3]), 4) if len(rgba) > 3 else 1.0
    if alpha < 1.0:
        return f"rgba({r},{g},{b},{alpha})"
    return f"rgb({r},{g},{b})"


def hex_to_magics(colour):
    """Convert ``#rrggbb`` (or a matplotlib colour) to a Magics ``rgb(...)``."""
    return fmt_colour(mcolors.to_rgba(colour))


# Malformed level values in the source YAML which YAML parses as strings, and
# the value they are read as here. See magics/README.md.
LEVEL_REPAIRS = {"0..5": 0.5}


def resolve_levels(config):
    """Return the explicit level list of a style config, or None if dynamic."""
    levels = config.get("levels")
    if isinstance(levels, str) and levels.startswith("range"):
        args = [int(i) for i in re.findall(r"-?\d+", levels)]
        return list(range(*args))
    if isinstance(levels, dict):
        return None
    if isinstance(levels, (list, tuple)):
        return [float(LEVEL_REPAIRS.get(v, v)) for v in levels]
    return None


def repair_config(config):
    """Return a copy of `config` with any malformed level values repaired."""
    config = dict(config)
    levels = config.get("levels")
    if isinstance(levels, (list, tuple)):
        config["levels"] = [LEVEL_REPAIRS.get(v, v) for v in levels]
    return config


def n_expected_colours(levels, extend):
    """Number of colours a style needs: one per interval, plus any extension."""
    return len(levels) - 1 + {"both": 2, "min": 1, "max": 1}.get(extend, 0)


def band_colours(config, style, levels):
    """Resolve the colour of every interval of `levels`.

    Returns ``(under, bands, over)`` where ``under``/``over`` are ``None``
    unless the style extends in that direction.

    When the source declares an explicit colour list of exactly the right
    length, that list is used verbatim - it is the authored intent. Otherwise
    (a named matplotlib colormap, or a list whose length does not match the
    levels) the colours are read back out of the colormap earthkit-plots
    actually builds, so that the Magics output matches what earthkit-plots
    draws today.
    """
    extend = style.extend
    declared = config.get("colors")

    if isinstance(declared, list) and len(declared) == n_expected_colours(
        levels, extend
    ):
        colours = [mcolors.to_rgba(c) for c in declared]
    else:
        kwargs = style.to_matplotlib_kwargs(None)
        cmap, norm = kwargs["cmap"], kwargs["norm"]
        span = levels[-1] - levels[0]
        colours = []
        if extend in ("min", "both"):
            colours.append(cmap(norm(levels[0] - span * EXTEND_PAD / 2)))
        colours += [cmap(norm((a + b) / 2)) for a, b in zip(levels[:-1], levels[1:])]
        if extend in ("max", "both"):
            colours.append(cmap(norm(levels[-1] + span * EXTEND_PAD / 2)))

    under = over = None
    if extend in ("min", "both"):
        under, colours = colours[0], colours[1:]
    if extend in ("max", "both"):
        over, colours = colours[-1], colours[:-1]
    return under, colours, over


def shade_style(name, config, style, levels):
    """Build a Magics area-fill visual definition from an earthkit style."""
    under, bands, over = band_colours(config, style, levels)

    shade_levels = list(levels)
    colours = list(bands)
    span = levels[-1] - levels[0]
    if under is not None:
        shade_levels.insert(0, levels[0] - span * EXTEND_PAD)
        colours.insert(0, under)
    if over is not None:
        shade_levels.append(levels[-1] + span * EXTEND_PAD)
        colours.append(over)

    lo, hi = fmt_number(levels[0]), fmt_number(levels[-1])
    units = config.get("units", "")
    # Magics labels every boundary of a level_list legend and offers no
    # equivalent of earthkit's `ticks`, so the intended tick values are only
    # recorded in the description. See magics/README.md.
    ticks = config.get("ticks")
    description = (
        f"Method: area fill. Level list: {lo} to {hi} "
        f"({len(levels) - 1} intervals{', ' + str(units) if units else ''}). "
        f"DCCMS colour scheme."
    )
    if ticks:
        description += " Intended legend ticks: " + "/".join(
            fmt_number(float(t)) for t in ticks
        ) + "."
    title = f"DCCMS shade ({lo} / {hi}{' ' + str(units) if units else ''})"

    visdef = {
        "contour": "off",
        "contour_description": description,
        "contour_highlight": "off",
        "contour_hilo": "off",
        "contour_label": "off",
        "contour_legend_text": title,
        "contour_level_list": "/".join(fmt_number(v) for v in shade_levels),
        "contour_level_selection_type": "level_list",
        "contour_shade": "on",
        "contour_shade_colour_list": "/".join(fmt_colour(c) for c in colours),
        "contour_shade_colour_method": "list",
        "contour_shade_method": "area_fill",
        "contour_shade_min_level": shade_levels[0],
        "contour_shade_max_level": shade_levels[-1],
        "contour_title": title,
        "legend": "on",
        "legend_display_type": "continuous",
    }

    if under is not None:
        visdef["legend_user_minimum"] = "on"
        visdef["legend_user_minimum_text"] = f"< {lo}"
    if over is not None:
        visdef["legend_user_maximum"] = "on"
        visdef["legend_user_maximum_text"] = f"> {hi}"
    return visdef


def line_style(name, config):
    """Build a Magics line-contour visual definition from an earthkit style."""
    colour = hex_to_magics(config.get("linecolors", "black"))
    widths = config.get("linewidths", [1])
    if not isinstance(widths, (list, tuple)):
        widths = [widths]
    # matplotlib cycles `linewidths` over the levels; Magics expresses the same
    # idea with a "highlight" contour drawn every N levels.
    base = min(widths)
    emphasis = max(widths)

    def thickness(width):
        return max(1, int(round(width / 0.5)))

    units = config.get("units", "")
    levels = config.get("levels") or {}
    step = levels.get("step") if isinstance(levels, dict) else None

    description = (
        f"Method: line contour. Interval: {step} {units}. DCCMS colour scheme."
    )
    title = f"DCCMS contour (interval {step} {units})".strip()

    visdef = {
        "contour": "on",
        "contour_description": description,
        "contour_hilo": "off",
        "contour_level_selection_type": "interval",
        "contour_interval": step,
        "contour_line_colour": colour,
        "contour_line_thickness": thickness(base),
        "contour_shade": "off",
        "contour_legend_text": title,
        "contour_title": title,
    }
    if emphasis != base:
        visdef.update(
            {
                "contour_highlight": "on",
                "contour_highlight_colour": colour,
                "contour_highlight_frequency": len(widths),
                "contour_highlight_thickness": thickness(emphasis),
            }
        )
    else:
        visdef["contour_highlight"] = "off"

    if config.get("labels"):
        visdef["contour_label"] = "on"
        visdef["contour_label_height"] = 0.35
        visdef["contour_label_colour"] = colour
        visdef["contour_label_frequency"] = 1
    else:
        visdef["contour_label"] = "off"

    if "legend_style" in config and config["legend_style"] is None:
        visdef["legend"] = "off"
    else:
        visdef["legend"] = "on"
    return visdef


def build_styles():
    """Return ``(styles.json contents, {identity: [style names]})``."""
    definitions = {}
    per_identity = {}
    warnings = []

    for identity in PARAMS:
        config = load_yaml(SRC / "styles" / f"{identity}.yml")
        optimal = config["optimal"]
        names = STYLE_ORDER_OVERRIDES.get(
            identity, [optimal] + [n for n in config["styles"] if n != optimal]
        )
        assert sorted(names) == sorted(config["styles"]), identity
        per_identity[identity] = [STYLE_NAMES[n] for n in names]

        for ek_name in names:
            ek_config = config["styles"][ek_name]
            magics_name = STYLE_NAMES[ek_name]
            levels = resolve_levels(ek_config)

            for bad, good in LEVEL_REPAIRS.items():
                if bad in (ek_config.get("levels") or []):
                    warnings.append(
                        f"{ek_name}: level {bad!r} is not a number in the source "
                        f"YAML; translated as {good}"
                    )

            if ek_config.get("colors") is None:
                definitions[magics_name] = line_style(magics_name, ek_config)
                continue

            if levels is None:
                warnings.append(f"{ek_name}: dynamic levels are not translatable")
                continue

            style = ekp_styles.Style.from_dict(repair_config(ek_config))
            definitions[magics_name] = shade_style(
                magics_name, ek_config, style, levels
            )

            colours = ek_config["colors"]
            if isinstance(colours, list):
                extend = ek_config.get("extend")
                expected = n_expected_colours(levels, extend)
                if len(colours) != expected:
                    warnings.append(
                        f"{ek_name}: source declares {len(colours)} colours but "
                        f"{len(levels)} levels need {expected} (extend={extend}); "
                        f"colours taken from the interpolated earthkit colormap"
                    )

    return definitions, per_identity, warnings


def dccms_criteria(identity):
    """The DCCMS match criteria for an identity, as Magics match entries."""
    criteria = load_yaml(SRC / "identities" / f"{identity}.yml")["criteria"]
    return [{key: str(value) for key, value in entry.items()} for entry in criteria]


# paramId is the only identifier precise enough to decide that two entries are
# about the same field. shortName alone is not: the stock library uses "t" and
# "ws" for pressure-level fields the DCCMS styles have nothing to do with.
IDENTITY_KEY = "paramId"

# A record narrowed by any of these is about a more specific field than the
# DCCMS styles cover -- a pressure level, or an ensemble product whose values
# live on a different scale. It is not the owner of a plain paramId.
NARROWING_KEYS = ("levelist", "level", "levtype", "type")


def param_ids(match_entries):
    """The paramIds these match entries claim."""
    ids = set()
    for entry in match_entries:
        value = entry.get(IDENTITY_KEY)
        if value is None:
            continue
        for item in value if isinstance(value, list) else [value]:
            ids.add(str(item))
    return ids


def stock_styles(record):
    """A record's own styles, with any DCCMS names removed.

    Stripping the prefix is half of what makes this idempotent: it recovers the
    upstream list no matter how many times the generator has run before.
    """
    return [s for s in record.get("styles", []) if not s.startswith(PREFIX)]


def stock_param_files():
    """Every parameter file in the library, parsed."""
    for path in sorted(OUT.glob("*.json")):
        if path.name == "styles.json" or path.name.startswith(PREFIX):
            continue
        try:
            records = json.loads(path.read_text())
        except json.JSONDecodeError:
            continue
        if isinstance(records, list):
            yield path, records


def dump_stock(path, records):
    """Rewrite a parameter file, keeping its key order and 2-space indent."""
    with open(path, "w") as f:
        json.dump(records, f, indent=2)
        f.write("\n")


def find_owner(pairs, paramid):
    """The record that already claims this paramId without narrowing it."""
    for path, records in pairs:
        for index, record in enumerate(records):
            if not record.get("styles"):
                continue
            for entry in record.get("match", []):
                if any(key in entry for key in NARROWING_KEYS):
                    continue
                if paramid in param_ids([entry]):
                    return path, index
    return None


# Records every addition made to the vendored stock files, so the next run can
# undo it exactly. Stripping by value is not safe: several DCCMS criteria are
# identical to the upstream entry they sit beside (mcc.json genuinely says
# {paramId: 187, shortName: mcc}), so a value-based strip deletes stock data.
MANIFEST = SHARE / "dccms_manifest.json"


def note(manifest, path, index, field, value):
    """Record one addition to record `index` of `path`."""
    slot = manifest.setdefault(path.name, {}).setdefault(str(index), {})
    if field == "prefered_units":
        slot[field] = value
    else:
        slot.setdefault(field, []).append(value)


def undo_manifest(by_path):
    """Remove everything the previous run added, using the manifest it wrote."""
    if not MANIFEST.is_file():
        return
    try:
        manifest = json.loads(MANIFEST.read_text())
    except json.JSONDecodeError:
        return
    for name, per_index in manifest.items():
        path = OUT / name
        if path not in by_path:
            continue
        for index, added in per_index.items():
            try:
                record = by_path[path][int(index)]
            except (ValueError, IndexError):
                continue
            for entry in added.get("match", []):
                if entry in record.get("match", []):
                    record["match"].remove(entry)
            for style in added.get("styles", []):
                if style in record.get("styles", []):
                    record["styles"].remove(style)
            if "prefered_units" in added:
                record.pop("prefered_units", None)


def extend_stock_files(per_identity):
    """Fold the DCCMS criteria and styles into the stock parameter files.

    Rather than shipping a parallel set of dccms_<param>.json files, each DCCMS
    identity is merged into the stock record that already owns the field. That
    leaves exactly one record matching any given field, so Magics -- which
    returns the style list of the single best-scoring record and never unions
    across files -- has no tie to break.

    Each criterion goes to whichever record already claims its paramId without
    narrowing it by level or product type. Criteria with no such owner, and
    criteria naming no paramId at all, go to the identity's primary file. That
    keeps a DCCMS identity spanning several upstream files (cloud cover) from
    creating the very ties this is meant to avoid.

    Idempotent by way of a manifest: every addition is recorded in
    share/magics/dccms_manifest.json and undone on the next run. The manifest
    is what makes this safe -- several DCCMS criteria are character-for-
    character identical to the upstream entry they sit beside (mcc.json really
    does say {paramId: 187, shortName: mcc}), so stripping by value would
    delete the stock library's own criteria.
    """
    by_path = {path: records for path, records in stock_param_files()}
    # Snapshot before mutating, so untouched files are not rewritten and the
    # diff stays confined to the handful of files that actually gain something.
    before = {path: json.dumps(records, sort_keys=True) for path, records in by_path.items()}
    undo_manifest(by_path)

    pairs = list(by_path.items())
    touched, problems, manifest = {}, [], {}

    for identity, style_names in per_identity.items():
        primary_name, _, units = PARAMS[identity]
        primary_path = OUT / primary_name
        if primary_path not in by_path:
            problems.append(f"{identity}: {primary_name} is not in the library")
            continue

        targets = set()
        for entry in dccms_criteria(identity):
            ids = param_ids([entry])
            owner = find_owner(pairs, sorted(ids)[0]) if ids else None
            path, index = owner or (primary_path, 0)
            record = by_path[path][index]
            if entry not in record.setdefault("match", []):
                record["match"].append(entry)
                note(manifest, path, index, "match", entry)
            targets.add((path, index))

        # DCCMS styles go first so they stay the default: Magics and skinnyWMS
        # both take styles[0] when the caller asks for no particular style.
        for path, index in targets:
            record = by_path[path][index]
            base = record.get("styles", [])
            added = [s for s in style_names if s not in base]
            record["styles"] = style_names + [s for s in base if s not in style_names]
            for name in added:
                note(manifest, path, index, "styles", name)
            touched.setdefault(path.name, set()).add(identity)

        record = by_path[primary_path][0]
        if units is not None:
            existing = record.get("prefered_units")
            if existing is None:
                record["prefered_units"] = units
                note(manifest, primary_path, 0, "prefered_units", units)
            elif existing != units:
                problems.append(
                    f"{identity}: {primary_name} already asks for {existing!r}, "
                    f"DCCMS wants {units!r}"
                )

    for path, records in by_path.items():
        if json.dumps(records, sort_keys=True) != before[path]:
            dump_stock(path, records)
    dump(MANIFEST, manifest)

    return touched, problems


def build_coastlines():
    """Translate the DCCMS map decoration from schema.yml."""
    schema = load_yaml(SRC / "schema.yml")
    return {
        "foreground": {
            "contour_legend_text": "DCCMS coastlines",
            "map_coastline": "on",
            "map_coastline_colour": hex_to_magics(schema["coastlines"]["edgecolor"]),
            "map_coastline_thickness": 1,
            "map_coastline_land_shade": "off",
            "map_coastline_sea_shade": "off",
            "map_grid": "off",
            "map_label": "off",
        },
        "background": {
            "contour_legend_text": "DCCMS land/sea background",
            "map_coastline": "on",
            "map_coastline_colour": hex_to_magics(schema["coastlines"]["edgecolor"]),
            "map_coastline_thickness": 1,
            "map_coastline_land_shade": "on",
            "map_coastline_land_shade_colour": hex_to_magics(schema["land"]["color"]),
            "map_coastline_sea_shade": "on",
            "map_coastline_sea_shade_colour": hex_to_magics(schema["ocean"]["color"]),
            "map_grid": "off",
            "map_label": "off",
        },
        "boundaries": {
            "contour_legend_text": "DCCMS boundaries",
            "map_boundaries": "on",
            "map_boundaries_colour": hex_to_magics(schema["borders"]["edgecolor"]),
            "map_boundaries_thickness": 1,
            "map_disputed_boundaries": "on",
            "map_disputed_boundaries_colour": hex_to_magics(
                schema["disputed_boundaries"]["edgecolor"]
            ),
            "map_disputed_boundaries_style": "dash",
            "map_administrative_boundaries": "off",
            "map_administrative_boundaries_colour": hex_to_magics(
                schema["administrative_areas"]["edgecolor"]
            ),
            "map_administrative_boundaries_style": "solid",
            "map_coastline": "off",
            "map_grid": "off",
            "map_label": "off",
        },
        "grid": {
            "contour_legend_text": "DCCMS grid",
            "map_coastline": "off",
            "map_grid": "on",
            "map_grid_colour": hex_to_magics(schema["gridlines"]["color"]),
            "map_grid_line_style": "solid",
            "map_grid_thickness": 1,
            "map_label": "on",
            "map_label_colour": hex_to_magics(
                schema["gridlines"]["xlabel_style"]["color"]
            ),
            "map_label_height": 0.35,
        },
    }


# Unit conversions the DCCMS styles need which stock Magics does not know
# about. Magics reads these from its own installation, not from the style path.
EXTRA_UNITS_RULES = {
    "km/h": [{"from": "m s**-1", "to": "km/h", "offset": 0.0, "scaling": 3.6}],
}


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
        f.write("\n")


def merge_styles_json(path, ours):
    """Replace the DCCMS block in a Magics ``styles.json``, leaving the rest alone.

    The file is a vendored copy of the stock ECMWF library, so the 576 upstream
    definitions are edited textually rather than round-tripped through ``json``:
    that keeps their formatting, key order and numeric spelling byte-for-byte
    identical, so the only thing a diff ever shows is the DCCMS block.

    Idempotent -- a previous run's block is cut out before the new one is
    written, so the definitions never accumulate.
    """
    text = path.read_text()
    before = json.loads(text)
    stock = {k: v for k, v in before.items() if not k.startswith(PREFIX)}

    # Our block is always written last and every key in it is prefixed, so the
    # first prefixed key marks where the stock entries stop.
    match = re.search(rf'^\s*"{PREFIX}[^"]*"\s*:', text, re.M)
    if match:
        head = text[: match.start()].rstrip().rstrip(",")
    else:
        head = text.rstrip()
        if not head.endswith("}"):
            raise ValueError(f"{path} does not look like a JSON object")
        head = head[:-1].rstrip()

    # Match the upstream file's 4-space indent and " : " key separator.
    block = json.dumps(ours, indent=4, separators=(",", " : "))
    body = "\n".join(block.splitlines()[1:-1])
    path.write_text(head + ",\n" + body + "\n}\n")

    after = json.loads(path.read_text())
    kept = {k: v for k, v in after.items() if not k.startswith(PREFIX)}
    added = {k: v for k, v in after.items() if k.startswith(PREFIX)}
    if kept != stock:
        raise AssertionError("merge altered the stock style definitions")
    if added != ours:
        raise AssertionError("merge did not write the DCCMS definitions verbatim")
    return len(stock), len(added)


def main():
    if not (OUT / "styles.json").is_file():
        raise SystemExit(
            f"{OUT / 'styles.json'} is missing.\n"
            "This tool merges into a vendored copy of the stock Magics style "
            "library; copy share/magics/styles/ecmwf from ecmwf/magics into "
            f"{OUT} first."
        )

    definitions, per_identity, warnings = build_styles()
    n_stock, n_ours = merge_styles_json(OUT / "styles.json", definitions)

    touched, problems = extend_stock_files(per_identity)

    dump(OUT / "coastlines.json", build_coastlines())
    dump(SHARE / "dccms_units-rules.json", EXTRA_UNITS_RULES)

    print(f"{OUT}")
    print(f"  styles.json: {n_stock} stock + {n_ours} DCCMS definitions")
    print(f"  {len(touched)} parameter files extended in place:")
    for name in sorted(touched):
        print(f"    {name:22} {', '.join(sorted(touched[name]))}")
    print(f"  coastlines.json")
    print(f"{SHARE / 'dccms_units-rules.json'}")
    for warning in warnings:
        print(f"  note: {warning}")
    for name in problems:
        print(f"  PROBLEM: {name}")
    leftover = sorted(f.name for f in OUT.glob(f"{PREFIX}*.json"))
    for name in leftover:
        print(f"  stale: {name} is not generated any more -- delete it")


if __name__ == "__main__":
    main()
