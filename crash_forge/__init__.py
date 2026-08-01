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
        from .ui import panel as ui_panel

        _SUBMODULES = (bl_scene, ops_reset, ops_prep, ui_panel)
    return _SUBMODULES


def _run_stage0_probe():
    """§6: probe runs at registration and again at the pipeline's start."""
    import json

    import bpy

    from .bl import probe as bl_probe

    try:
        result = bl_probe.run_probe()
    except Exception as exc:  # a probe must never take the add-on down with it
        print(f"[Crash Forge] Stage 0 probe raised unexpectedly: {exc}")
        return

    print(bl_probe.format_report(result))

    scene = bpy.context.scene
    if scene is not None and hasattr(scene, "crash_forge"):
        scene.crash_forge.probe_report = json.dumps(
            {
                "ok": result.ok,
                "errors": [str(e) for e in result.errors],
                "warnings": [str(w) for w in result.warnings],
                "data": {k: str(v) for k, v in result.data.items()},
            }
        )


def register():
    for module in _submodules():
        module.register()
    _run_stage0_probe()


def unregister():
    for module in reversed(_submodules()):
        module.unregister()
