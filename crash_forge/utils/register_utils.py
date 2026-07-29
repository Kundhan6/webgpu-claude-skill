"""Reload-safe register_class/unregister_class wrappers.

Reinstalling over a live Blender session (Install from Disk again without a
full restart, or a previous install that failed partway through register())
can leave classes from the earlier load still registered under the same
name. Blender raises RuntimeError for both "already registered" and "not
registered" instead of offering a clean is-registered check, so we catch
those specific messages and skip rather than let one leftover class abort
the whole register()/unregister() chain.
"""

import bpy


def register_classes(classes):
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except RuntimeError as exc:
            if "already registered" not in str(exc):
                raise
            print(f"Crash Forge: {cls.__name__} already registered, skipping.")


def unregister_classes(classes):
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError as exc:
            if "not registered" not in str(exc) and "unknown" not in str(exc).lower():
                raise
            print(f"Crash Forge: {cls.__name__} was not registered, skipping.")
