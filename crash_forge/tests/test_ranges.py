"""Tier A (§13) — pure core, no bpy, no stub needed.

Proves the §2.3 transcription artifacts are caught: `goal_default = 8`
(meant 0.8) must clamp to 1.0 *and* raise a visible warning, and
`bend = 110` (meant 10) must clamp and warn too. A silent clamp here
produces zero visible soft-body deformation — a failure that looks
exactly like broken code, not a bad input value. This is the single most
safety-critical test in the add-on.
"""
import pytest

from crash_forge.core import ranges


def test_goal_default_8_clamps_to_1_and_warns():
    result = ranges.clamped("goal_default", 8)
    assert result.value == 1.0
    assert result.clamped is True
    assert result.warning is not None
    assert "goal_default" in result.warning


def test_bend_110_clamps_and_warns():
    result = ranges.clamped("bend", 110)
    assert result.clamped is True
    assert result.value < 110
    assert result.warning is not None
    assert "bend" in result.warning


def test_plastic_100_passes_unclamped():
    result = ranges.clamped("plastic", 100)
    assert result.value == 100
    assert result.clamped is False
    assert result.warning is None


def test_goal_default_within_range_passes_unclamped():
    result = ranges.clamped("goal_default", 0.8)
    assert result.value == 0.8
    assert result.clamped is False
    assert result.warning is None


def test_negative_value_clamps_to_min():
    result = ranges.clamped("goal_friction", -5)
    assert result.value == 0.0
    assert result.clamped is True
    assert result.warning is not None


def test_unknown_property_raises_keyerror():
    with pytest.raises(KeyError):
        ranges.clamped("not_a_real_property", 1.0)


def test_plastic_is_coerced_to_int():
    result = ranges.clamped("plastic", 42.9)
    assert isinstance(result.value, int)
    assert result.value == 42


def test_unverified_ranges_say_so_in_the_warning():
    result = ranges.clamped("bend", 110)
    assert "UNVERIFIED" in result.warning


def test_all_baseline_preset_values_from_10_1_pass_clean():
    """§10.1's proven baseline preset must never itself trigger a clamp."""
    baseline = {
        "goal_default": 0.8,
        "goal_min": 0.98,
        "goal_max": 1.0,
        "goal_spring": 0.1,
        "goal_friction": 50,
        "plastic": 100,
        "bend": 10,
    }
    for prop, value in baseline.items():
        result = ranges.clamped(prop, value)
        assert result.clamped is False, f"{prop}={value} unexpectedly clamped"
