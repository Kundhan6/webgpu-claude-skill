"""Crash Forge — register/unregister only (§5).

No module-level bpy import. Everything that touches bpy — bl/, ops/, ui/ —
is imported lazily inside register()/unregister(). That is what lets
`crash_forge.core.*` be imported and unit-tested with plain CPython and
zero Blender installed: importing this package must never require bpy,
only *registering* it does.

bl_info below is the legacy fallback path (§4) for Blender builds/setups
that load this as a classic add-on rather than an Extension reading
blender_manifest.toml.
"""

bl_info = {
    "name": "Crash Forge",
    "author": "Krish",
    "version": (0, 2, 0),
    "blender": (5, 0, 0),
    "location": "View3D > Sidebar > Crash Forge",
    "description": "Automated pre-baked rigid-to-soft-body car crash rig",
    "category": "Physics",
}

_SUBMODULES = None


def _submodules():
    global _SUBMODULES
    if _SUBMODULES is None:
        from .bl import scene as bl_scene
        from .ops import prep as ops_prep
        from .ops import reset as ops_reset
        from .ops import rig as ops_rig
        from .ui import panel as ui_panel

        _SUBMODULES = (bl_scene, ops_reset, ops_prep, ops_rig, ui_panel)
    return _SUBMODULES


def register():
    """Deliberately does NOT run the Stage 0 probe. Confirmed on a real
    Blender run: `bpy.context` is a restricted proxy during registration
    (`_RestrictContext`), and `.scene` on it raises `AttributeError`
    rather than returning `None` — the probe used to run here, wrapped
    in a bare try/except that caught exactly that exception and just
    printed it, so registration "succeeded" while the probe had
    validated nothing at all. See `bl/probe.py::ensure_probed()`'s
    docstring — the probe now runs lazily, from each stage operator's
    own `execute()`, where real context is guaranteed, and it never
    swallows a failure."""
    for module in _submodules():
        module.register()


def unregister():
    from .bl import probe as bl_probe

    for module in reversed(_submodules()):
        module.unregister()
    bl_probe.reset_probe_cache()
