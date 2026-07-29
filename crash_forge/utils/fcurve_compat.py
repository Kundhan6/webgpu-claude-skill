"""F-Curve access that works regardless of Action API shape.

Blender 5.0 removed the legacy Action API entirely (`action.fcurves`,
`action.groups`, `action.id_root` no longer exist) in favor of the
layered/slotted model: `action.layers[i].strips[j].channelbags[k].fcurves`.
Blender 5.1.2 (this addon's target) only exposes the new shape, but every
function here still checks defensively with hasattr() rather than assuming,
so a future Blender version that changes shape again fails loudly instead of
silently through every stage that animates the car.
"""


def iter_fcurves(action):
    """Yield every FCurve in an Action, regardless of API shape."""
    if action is None:
        return

    if hasattr(action, "layers"):
        for layer in action.layers:
            for strip in layer.strips:
                if not hasattr(strip, "channelbags"):
                    continue
                for channelbag in strip.channelbags:
                    for fcurve in channelbag.fcurves:
                        yield fcurve
        return

    if hasattr(action, "fcurves"):
        for fcurve in action.fcurves:
            yield fcurve
        return

    raise RuntimeError(
        "Crash Forge: unrecognized Action F-Curve API shape — "
        "neither 'layers' nor 'fcurves' found on this Action."
    )


def get_fcurve(action, data_path, index=-1):
    """Find a single FCurve by data_path (and optionally array_index)."""
    for fcurve in iter_fcurves(action):
        if fcurve.data_path == data_path and (index < 0 or fcurve.array_index == index):
            return fcurve
    return None


def get_fcurves(action, data_path):
    """Find every FCurve matching data_path (e.g. all 3 axes of 'location')."""
    return [fc for fc in iter_fcurves(action) if fc.data_path == data_path]


def object_action(obj):
    """Return obj's active Action, or None if it has no animation data."""
    if obj.animation_data is None:
        return None
    return obj.animation_data.action
