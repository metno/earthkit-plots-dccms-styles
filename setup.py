"""Shim for the one thing that cannot be declared in pyproject.toml.

Everything about this package is configured in pyproject.toml except the
Magics style library under ``share/``, which has to be installed into the
environment's data prefix rather than into site-packages so that it ends up at
``<sys.prefix>/share/magics/styles/dccms`` -- the layout Magics uses for its
own style libraries.

That needs ``data_files``, and setuptools has removed ``data_files`` from its
pyproject schema (``tool.setuptools must not contain {'data_files'}``); it
survives only as an argument to ``setup()``. Hence this file.

The list is built by walking ``share/`` so that new files are picked up
without editing anything here. ``data_files`` destinations are interpreted
relative to the install prefix, and the source layout under ``share/`` already
mirrors the layout Magics expects, so each directory maps to itself.
"""

from pathlib import Path

from setuptools import setup

SHARE = Path("share")


def share_data_files():
    """Map every directory under share/ to the files it contains."""
    entries = []
    for directory in sorted(p for p in [SHARE, *SHARE.rglob("*")] if p.is_dir()):
        files = sorted(str(f) for f in directory.iterdir() if f.is_file())
        if files:
            entries.append((directory.as_posix(), files))
    return entries


setup(data_files=share_data_files())
