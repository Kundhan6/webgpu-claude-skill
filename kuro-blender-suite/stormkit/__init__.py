"""StormKit — Procedural Weather Engine.

See BLENDER_ADDON_MASTER_PLAN.md §4 for the full spec. This file wires up
add-on registration; each subsystem lives in its own module and exposes
register()/unregister().

NOTE (dev-time import path): this module imports its shared library as a
top-level `kuro_core` package (present as a sibling at the repo root
during development, and importable directly by the test suite). At build
time, scripts/build.sh vendors kuro_core into stormkit/kuro_core/ and
rewrites these imports to relative (`from .kuro_core import ...`) so the
shipped .zip has no external dependency — see §1 "Vendoring rule".
"""

from kuro_core import compat, log

bl_info = {
    "name": "StormKit",
    "author": "KURO",
    "version": (0, 1, 0),
    "blender": (4, 5, 0),
    "location": "View3D > Sidebar > KURO > StormKit",
    "description": "Procedural weather: sky, fog, precipitation, wetness/snow, wind, lightning",
    "category": "Scene",
}

_logger = log.get_logger("stormkit")

_SUBMODULES = (
    "properties",
    "presets",
    "sky",
    "fog",
    "precipitation",
    "wetness",
    "wind",
    "lightning",
    "operators",
    "ui",
)

_loaded_modules = []


def _import_submodules():
    import importlib

    modules = []
    for name in _SUBMODULES:
        modules.append(importlib.import_module(f".{name}", __name__))
    return modules


def register():
    compat.check_min_version()
    global _loaded_modules
    _loaded_modules = _import_submodules()
    for module in _loaded_modules:
        if hasattr(module, "register"):
            module.register()
    _logger.info("StormKit registered")


def unregister():
    for module in reversed(_loaded_modules):
        if hasattr(module, "unregister"):
            module.unregister()
    _logger.info("StormKit unregistered")


if __name__ == "__main__":
    register()
