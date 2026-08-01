"""RNA range table + clamp-with-warning (§6, §10.1). No bpy import.

§3 rule 2: no silent clamping. Every physics value is range-checked
before assignment, and a clamp always produces a visible Notice — never
just a quietly different number. This exists specifically because of the
§2.3 transcription artifacts: `goal_default = 8` (meant 0.8) silently
becomes 1.0 under Blender's own hard clamp, which pins every vertex to
its goal and produces *zero* deformation — a failure that looks exactly
like broken code, not a bad value.

All 11 SoftBodySettings entries below are now confirmed against a live
Stage 0 probe (Blender 5.1.2, via crash_forge/tests/blender_probe_script.py)
and match this table exactly, including the two that started as
documented placeholders: bend=(0, 10) and push=(0, 0.999). `bl/probe.py`
still reads the real hard_min/hard_max off bl_rna at every run and
`apply_probe_overrides()` can still correct this table if a future
Blender build ever disagrees — verified=True means "confirmed once", not
"exempt from being probed again".
"""
from dataclasses import dataclass
from typing import Optional, Union

Number = Union[int, float]


@dataclass(frozen=True)
class RangeSpec:
    hard_min: Number
    hard_max: Number
    value_type: type = float
    verified: bool = True


@dataclass(frozen=True)
class ClampResult:
    value: Number
    clamped: bool
    warning: Optional[str] = None


# §6 "known ground truth" + §10.1 baseline preset.
RANGE_TABLE: dict = {
    "goal_default": RangeSpec(0.0, 1.0, float),
    "goal_min": RangeSpec(0.0, 1.0, float),
    "goal_max": RangeSpec(0.0, 1.0, float),
    "goal_spring": RangeSpec(0.0, 0.999, float),
    "goal_friction": RangeSpec(0.0, 50.0, float),
    "plastic": RangeSpec(0, 100, int),
    "pull": RangeSpec(0.0, 0.999, float),
    "mass": RangeSpec(0.0, 50000.0, float),
    # Confirmed live on Blender 5.1.2 (Stage 0 probe): (0, 10), matching the
    # placeholder this started as. §6 said "probe it" precisely because this
    # wasn't in the spec's own ground truth table; now it's been probed.
    "bend": RangeSpec(0.0, 10.0, float),
    # Confirmed live on Blender 5.1.2: (0, 0.999).
    "push": RangeSpec(0.0, 0.999, float),
    # Confirmed live on Blender 5.1.2: (0, 1).
    "damping": RangeSpec(0.0, 1.0, float),
}


def apply_probe_overrides(overrides: dict) -> None:
    """Replace table entries with live bl_rna readings from bl/probe.py."""
    RANGE_TABLE.update(overrides)


def clamped(prop: str, value: Number) -> ClampResult:
    """Clamp `value` for `prop` against RANGE_TABLE. Never clamps silently."""
    spec = RANGE_TABLE.get(prop)
    if spec is None:
        raise KeyError(f"core.ranges: no range entry for property {prop!r}")

    coerced = spec.value_type(value)
    low, high = spec.hard_min, spec.hard_max

    if coerced < low or coerced > high:
        result_value = spec.value_type(max(low, min(high, coerced)))
        unverified = (
            "" if spec.verified
            else " (range UNVERIFIED against live bl_rna — confirm via Stage 0 probe before trusting)"
        )
        warning = (
            f"{prop}={value!r} is outside its RNA range [{low}, {high}] and was "
            f"clamped to {result_value!r}.{unverified}"
        )
        return ClampResult(result_value, True, warning)

    return ClampResult(coerced, False, None)
