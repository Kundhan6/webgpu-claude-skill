"""Crash Forge operators package."""

if "prep" in locals():
    import importlib
    importlib.reload(prep)
    importlib.reload(tag)
    importlib.reload(drive)
else:
    from . import prep
    from . import tag
    from . import drive

modules = (prep, tag, drive)


def register():
    for m in modules:
        m.register()


def unregister():
    for m in reversed(modules):
        m.unregister()
