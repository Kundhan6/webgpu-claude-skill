"""Crash Forge operators package."""

if "prep" in locals():
    import importlib
    importlib.reload(prep)
    importlib.reload(tag)
else:
    from . import prep
    from . import tag

modules = (prep, tag)


def register():
    for m in modules:
        m.register()


def unregister():
    for m in reversed(modules):
        m.unregister()
