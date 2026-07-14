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
else:
    from . import properties
    from . import preferences


def register():
    properties.register()
    preferences.register()


def unregister():
    preferences.unregister()
    properties.unregister()
