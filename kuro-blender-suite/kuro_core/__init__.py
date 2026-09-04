"""kuro_core — shared library for the KURO Blender Suite add-ons.

Vendored into each add-on package at build time by scripts/build.sh.
Never import this package by its top-level name from inside an add-on;
add-ons import their own vendored copy (e.g. `from .kuro_core import compat`)
so each shipped zip is self-contained.
"""

from . import compat, nodeutils, presets, uiutils, log, cleanup

__all__ = ["compat", "nodeutils", "presets", "uiutils", "log", "cleanup"]
