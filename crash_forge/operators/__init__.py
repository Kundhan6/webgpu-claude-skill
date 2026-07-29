"""Crash Forge operators package."""

if "prep" in locals():
    import importlib
    importlib.reload(prep)
    importlib.reload(tag)
    importlib.reload(drive)
    importlib.reload(rig)
    importlib.reload(bake)
    importlib.reload(export)
    importlib.reload(setup)
else:
    from . import prep
    from . import tag
    from . import drive
    from . import rig
    from . import bake
    from . import export
    from . import setup

# setup registers the Scene props the simple panel reads, so it goes first.
modules = (setup, prep, tag, drive, rig, bake, export)


def register():
    for m in modules:
        m.register()


def unregister():
    for m in reversed(modules):
        m.unregister()
