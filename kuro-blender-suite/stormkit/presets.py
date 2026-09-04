"""Preset load/apply for StormKit — a thin wrapper over kuro_core.presets
that knows StormKit's state schema, file locations, and how to push a
preset (optionally as a keyframed transition) onto scene.stormkit.
"""

from kuro_core import presets as preset_lib

STATE_FIELDS = (
    "time_of_day", "overcast", "fog_density", "fog_height",
    "precipitation_type", "precipitation_amount", "wind_speed",
    "wind_direction", "wetness", "snow_cover", "storm_intensity",
    "turbulence", "latitude",
)

_NUMERIC_FIELDS = tuple(f for f in STATE_FIELDS if f != "precipitation_type")

STATE_SCHEMA = {
    "type": "object",
    "required": {"name": {"type": "string"}},
    "optional": {
        **{field: {"type": "number", "min": -360.0, "max": 400.0} for field in _NUMERIC_FIELDS},
        "precipitation_type": {"type": "string", "enum": ["NONE", "RAIN", "SNOW"]},
    },
}


def builtin_dir():
    return preset_lib.builtin_presets_dir(__file__)


def user_dir():
    return preset_lib.user_presets_dir("stormkit")


def list_presets():
    return preset_lib.list_preset_files(builtin_dir(), user_dir())


def load(name, logger=None):
    found = dict(list_presets())
    path = found.get(name)
    if path is None:
        if logger:
            logger.warning(f"Preset '{name}' not found in {builtin_dir()} or {user_dir()}")
        return None
    return preset_lib.load_preset(path, schema=STATE_SCHEMA, logger=logger)


def apply_to_scene(context, data, transition_frames=0):
    """Apply a preset dict's fields onto scene.stormkit. If
    `transition_frames` > 0, keyframes the *current* state at the current
    frame and the *target* state `transition_frames` later, instead of
    snapping instantly — Blender clamps each assignment to the
    property's declared min/max automatically, so no manual clamping is
    needed here."""
    state = context.scene.stormkit
    start_frame = context.scene.frame_current

    if transition_frames > 0:
        for field in _NUMERIC_FIELDS:
            state.keyframe_insert(field, frame=start_frame)

    for field in STATE_FIELDS:
        if field in data:
            setattr(state, field, data[field])

    if transition_frames > 0:
        for field in _NUMERIC_FIELDS:
            state.keyframe_insert(field, frame=start_frame + transition_frames)


def register():
    pass


def unregister():
    pass
