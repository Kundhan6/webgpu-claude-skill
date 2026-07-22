"""Crash Forge — procedural crash/impact destruction toolkit.

Stage 0: data model, preferences, and environment verification only.
panels.py and operators/ are added in later stages.
"""

bl_info = {
    "name": "Crash Forge",
    "author": "Crash Forge",
    "version": (0, 1, 0),
    "blender": (5, 1, 0),
    "location": "Preferences > Add-ons > Crash Forge (viewport panel arrives in a later stage)",
    "description": "Procedural crash/impact destruction toolkit: prep, tag, drive, rig, bake, export",
    "category": "Object",
}

import bpy

if "properties" in locals():
    import importlib
    importlib.reload(properties)
    importlib.reload(preferences)
    importlib.reload(operators)
    importlib.reload(panels)
else:
    from . import properties
    from . import preferences
    from . import operators
    from . import panels


def register():
    properties.register()
    preferences.register()
    operators.register()
    panels.register()


def unregister():
    panels.unregister()
    operators.unregister()
    preferences.unregister()
    properties.unregister()
