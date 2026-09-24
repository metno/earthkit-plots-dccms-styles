# DCCMS styles for Magics

This directory is a complete Magics style library: a vendored copy of the
stock ECMWF one from [ecmwf/magics](https://github.com/ecmwf/magics)
(`share/magics/styles/ecmwf/`), with the DCCMS styles from
[`src/earthkit_plots_dccms_styles`](../../../../src/earthkit_plots_dccms_styles)
merged in.

The DCCMS parts are generated. To rebuild them after changing the YAML styles,
from the root of the repository:

```bash
python tools/earthkit_to_magics.py
```

That merges the DCCMS definitions into `styles.json` without touching the 576
stock ones, extends the stock parameter files that own each field, and is safe
to run repeatedly.

## Layout

| File | Role | How Magics finds it |
|------|------|---------------------|
| `styles.json` | The 576 stock visual definitions plus the 12 DCCMS ones | `MAGICS_STYLE_PATH` |
| 11 stock parameter files | Extended in place with the DCCMS criteria and style names | `MAGICS_STYLE_PATH` |
| the other 187 `*.json` | The stock ECMWF library, untouched | `MAGICS_STYLE_PATH` |
| `coastlines.json` | DCCMS map decoration (land, sea, coast, borders, grid) | `page_theme`, from the Magics installation |
| `../../dccms_units-rules.json` | One extra unit conversion Magics does not ship | The Magics installation |
| `../../dccms_manifest.json` | Exactly what the generator added, so it can undo it | not read by Magics |

There are **no separate `dccms_*.json` parameter files**. Each DCCMS identity
is folded into the stock file that already owns the field, so exactly one
record matches any given field. The reason is in **How the styles resolve**
below.

### Naming

Magics looks up `styles.json` and `coastlines.json` **by path**, so those names
are fixed — renaming `styles.json` makes every lookup fail with `Cannot find
the preset ...`, and a theme without a `coastlines.json` is not found at all.

Style *names* all carry a `dccms_` prefix. That is what lets the generator find
and remove its own additions, and it makes the DCCMS entries obvious in a file
that is otherwise upstream's.

## Using the styles

Installing the package deploys the library to the environment's data prefix, at
`<sys.prefix>/share/magics/styles/dccms`. Point `MAGICS_STYLE_PATH` at it:

```bash
export MAGICS_STYLE_PATH="$(python -c 'import sys; print(sys.prefix)')/share/magics/styles/dccms"
```

Magics never picks this up on its own — it reads only its own bundled share
directory unless `MAGICS_STYLE_PATH` says otherwise. Working from a checkout
instead of an install, point it at this directory in the repo.

Then let Magics pick the style from the field's metadata:

```python
from Magics import macro as magics

magics.plot(
    magics.output(output_formats=["png"], output_name="2t"),
    magics.mmap(subpage_map_projection="cylindrical"),
    magics.mgrib(grib_input_file_name="2t.grib"),
    magics.mcont(contour_automatic_setting="ecmwf"),
    magics.mlegend(),
    magics.mcoast(),
)
```

Or name a style explicitly:

```python
magics.mcont(
    contour_automatic_setting="style_name",
    contour_style_name="dccms_sh_2t_fM4t50i2",
)
```

Set `MAGICS_STYLES_DEBUG=1` to see which style was matched and why.

### Styles

| Magics style | earthkit style | Parameter |
|--------------|----------------|-----------|
| `dccms_sh_2t_fM4t50i2` | `NEAR_SURFACE_AIR_TEMPERATURE_IN_CELSIUS` | 2m temperature, °C |
| `dccms_sh_dpt_fM12t46i2` | `DEW_POINT_TEMPERATURE_IN_CELSIUS` | Dew point, °C |
| `dccms_sh_sst_fM1t30i1` | `SEA_SURFACE_TEMPERATURE_IN_CELSIUS` | SST, °C |
| `dccms_sh_sst_f272t300i1` | `SEA_SURFACE_TEMPERATURE_IN_KELVIN` | SST, K |
| `dccms_ct_msl_i4` | `MEAN_SEA_LEVEL_PRESSURE_IN_HPA` | MSLP, hPa |
| `dccms_ct_msl_i400_pa` | `MEAN_SEA_LEVEL_PRESSURE_IN_PA` | MSLP, Pa |
| `dccms_sh_tp_f0t200lst` | `TOTAL_PRECIPITATION_IN_MM` | Total precipitation, mm |
| `dccms_sh_r_f0t100i5` | `RELATIVE_HUMIDITY` | Relative humidity, % |
| `dccms_sh_cloud_f0t1i01` | `CLOUD_COVER` | Cloud cover, fraction |
| `dccms_sh_ws_f0t31lst` | `WIND_SPEED_AT_10M_IN_METERS_PER_SECOND` | 10m wind speed, m s⁻¹ |
| `dccms_sh_ws_f0t110lst` | `WIND_SPEED_AT_10M_IN_KM_PER_HOUR` | 10m wind speed, km h⁻¹ |
| `dccms_sh_w_fM20t15lst` | `VERTICAL_VELOCITY_AT_100M_IN_KMH` | Vertical velocity |

## Using the map decoration

`coastlines.json` is a Magics *theme*, which Magics loads from its own
installation rather than from `MAGICS_STYLE_PATH`. Install it as a theme
directory:

```bash
MAGICS_SHARE=$(python -c "import ecmwflibs, os; print(os.path.join(os.path.dirname(ecmwflibs.__file__), 'share', 'magics'))")
mkdir -p "$MAGICS_SHARE/styles/dccms"
cp coastlines.json "$MAGICS_SHARE/styles/dccms/"  # name is fixed
```

Then select it per page, and pick a preset with
`map_coastline_general_style`:

```python
magics.plot(
    magics.output(output_formats=["png"], output_name="malawi"),
    magics.page(page_theme="dccms"),
    magics.mmap(subpage_map_projection="cylindrical"),
    magics.mcoast(map_coastline_general_style="background"),
    magics.mcoast(map_coastline_general_style="boundaries"),
    magics.mcoast(map_coastline_general_style="grid"),
)
```

The presets are `background` (shaded land and sea plus coastlines),
`foreground` (coastlines only), `boundaries` (national and disputed borders)
and `grid` (graticule and labels).

## Translation notes

These are the places where Magics and earthkit-plots do not line up one to one.

**Out-of-range values.** earthkit's `extend: min | max | both` colours data
beyond the ends of the level list; Magics simply leaves it unshaded. To keep
the DCCMS appearance, each extended level list is padded with a sentinel bound
one full range beyond the end, shaded with the colour earthkit uses for its
under/over triangle. `legend_user_minimum_text` / `legend_user_maximum_text`
label those bands `< first` and `> last` so the sentinel value never appears in
the legend.

**Legend ticks.** earthkit's `ticks` selects a subset of levels to label.
Magics labels every boundary of a `level_list` legend and has no equivalent
setting (`legend_values_list` has no effect here, and setting it suppresses the
`> last` label). The intended tick values are recorded in each style's
`contour_description` so the information is not lost, but they are not applied.

**Wind speed in km h⁻¹.** Magics converts units only where its installation
carries a rule in `share/magics/units-rules.json`, and stock Magics has no
`m s**-1` → `km/h` rule. Neither a `scaling` block in the parameter file nor
`grib_scaling_factor` in the style is honoured for this. `wind_speed.json`
therefore lists the **m s⁻¹** style first, so an out-of-the-box plot is numerically
correct — note this differs from the earthkit library, where km h⁻¹ is
`optimal`. To get km h⁻¹, merge `dccms_units-rules.json` into the Magics
installation:

```bash
python - <<'EOF'
import json, os, ecmwflibs
share = os.path.join(os.path.dirname(ecmwflibs.__file__), "share", "magics")
path = os.path.join(share, "units-rules.json")
rules = json.load(open(path))
rules.update(json.load(open("dccms_units-rules.json")))
json.dump(rules, open(path, "w"), indent=1)
EOF
```

then add `"prefered_units": "km/h"` to `wind_speed.json` and move
`dccms_sh_ws_f0t110lst` to the front of its `styles` list.

**Contour line widths.** `MEAN_SEA_LEVEL_PRESSURE_*` cycles matplotlib
`linewidths: [0.5, 0.5, 0.5, 1]` over its levels. Magics expresses this as a
highlight contour: `contour_line_thickness: 1` with
`contour_highlight_thickness: 2` every `contour_highlight_frequency: 4` levels.

**Colours.** Where a style declares an explicit colour list of exactly the
right length, that list is used verbatim. Where it names a matplotlib colormap
(`binary_r` for cloud cover, `Spectral_r` for SST, `RdBu` for vertical
velocity), the per-interval colours are read back out of the colormap
earthkit-plots builds, so the two libraries draw the same thing.

## How the styles resolve

`MAGICS_STYLE_PATH` selects **one** library; it is not a search path, and a
colon-separated list does not work — only the first entry is used. So this
directory is a composite: the stock ECMWF library with the DCCMS styles merged
in, rather than a DCCMS-only library that would leave every other parameter
falling back to `default`.

Merging matters because of how Magics resolves a style. It scores every
parameter record against the field's metadata, picks the **single**
best-scoring record, and returns that record's `styles` array. It never unions
across files. Shipping DCCMS parameter files *beside* the stock ones therefore
does not work: for 2t, both would match `{paramId: 167, shortName: 2t}` at
score 2, and whichever won the tie-break would decide the entire list — the
loser's styles advertised nowhere, even though their definitions are loaded and
still render by name.

So `tools/earthkit_to_magics.py` extends the stock files in place instead.
Each DCCMS criterion is added to whichever record already claims its paramId
without narrowing it by level or product type; criteria with no such owner, and
criteria naming no paramId, go to the identity's primary file. The DCCMS style
names go in front of that record's own, so they stay the default — Magics and
skinnyWMS both take `styles[0]` when the caller asks for no particular style.

One record matches, no tie to break, and every field keeps its stock
alternatives:

| Field | Extends | Advertised | Default |
|-------|---------|-----------:|---------|
| 2t | `2t.json` | 13 | `dccms_sh_2t_fM4t50i2` |
| msl | `msl.json` | 15 | `dccms_ct_msl_i4` |
| dpt | `2t_dewpoint.json` | 11 | `dccms_sh_dpt_fM12t46i2` |
| tp | `tp_interval.json` | 9 | `dccms_sh_tp_f0t200lst` |
| ws | `wind_speed.json` | 8 | `dccms_sh_ws_f0t31lst` |
| sst | `sst.json` | 7 | `dccms_sh_sst_fM1t30i1` |
| w | `700w.json` | 6 | `dccms_sh_w_fM20t15lst` |
| tcc | `lcc.json`, `hcc.json`, `mcc.json` | 5 | `dccms_sh_cloud_f0t1i01` |
| r | `rh1000.json` | 4 | `dccms_sh_r_f0t100i5` |

Cloud cover spans three upstream files because one DCCMS identity covers what
upstream splits by cloud layer. Sending every criterion to a single file would
have re-created the ties this design exists to avoid, so each paramId goes to
its own owner.

### Undoing and re-vendoring

Every addition is recorded in `share/magics/dccms_manifest.json` and undone at
the start of the next run, which is what makes the generator idempotent.

The manifest is not a nicety. Several DCCMS criteria are character-for-
character identical to the upstream entry they sit beside — `mcc.json` really
does say `{paramId: 187, shortName: mcc}` — so removing previous additions by
value would silently delete the stock library's own criteria.

To re-vendor a newer Magics: replace this directory with the upstream
`share/magics/styles/ecmwf/`, delete the manifest, and re-run the generator.

## Issues found in the source styles

The translation surfaced three problems in the earthkit YAML. They are carried
over as-is or worked around here, but they are worth fixing upstream.

1. **`vertical-velocity-at-100m.yml` has `0..5` in its level list.** YAML reads
   that as the string `"0..5"`, not a number, which breaks the style in
   earthkit-plots too. It is translated here as `0.5`, which is what the tick
   list implies.
2. **`near-surface-air-temperature.yml` and `dew-point-temperature.yml` declare
   30 colours** for 29 and 31 intervals respectively. earthkit-plots resolves
   this by interpolating the list into a `LinearSegmentedColormap`, so the
   colours actually drawn are not the ones written in the YAML. The translation
   reproduces what is drawn.
3. **`cloud-cover.yml` declares `units: "%"` but levels from 0 to 1.** No unit
   conversion is requested here, so the style matches fraction-valued fields
   such as ERA5 `tcc`. A field that really is in percent will not plot.
