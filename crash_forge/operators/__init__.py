"""Crash Forge operators package."""

if "prep" in locals():
    import importlib
    importlib.reload(prep)
    importlib.reload(tag)
    importlib.reload(drive)
    importlib.reload(rig)
    importlib.reload(bake)
else:
    from . import prep
    from . import tag
    from . import drive
    from . import rig
    from . import bake

modules = (prep, tag, drive, rig, bake)


def register():
    for m in modules:
        m.register()


def unregister():
    for m in reversed(modules):
        m.unregister()
