"""Crash Forge operators package."""

if "prep" in locals():
    import importlib
    importlib.reload(prep)
else:
    from . import prep

modules = (prep,)


def register():
    for m in modules:
        m.register()


def unregister():
    for m in reversed(modules):
        m.unregister()
