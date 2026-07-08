"""Tests for stormkit.presets — §4.3 "ship >= 10 presets" + apply/transition."""

import bpy

from stormkit import presets as sk_presets, properties
from tests import harness

EXPECTED_PRESETS = {
    "clear", "golden_hour", "overcast", "light_rain", "thunderstorm",
    "drizzle_fog", "blizzard", "fresh_snow_morning", "sandstorm_haze", "night_storm",
}


def _ensure_registered():
    try:
        properties.register()
    except ValueError:
        pass


def test_at_least_ten_presets_are_shipped():
    found = dict(sk_presets.list_presets())
    harness.assert_true(len(found) >= 10, f"expected >= 10 presets, found {len(found)}")
    harness.assert_true(EXPECTED_PRESETS.issubset(found.keys()))


def test_every_shipped_preset_loads_and_validates():
    found = dict(sk_presets.list_presets())
    for name in EXPECTED_PRESETS:
        data = sk_presets.load(name)
        harness.assert_true(data is not None, f"preset '{name}' failed to load/validate")
        harness.assert_true("name" in data)


def test_apply_to_scene_sets_all_fields_instantly():
    _ensure_registered()
    context = bpy.context
    data = sk_presets.load("thunderstorm")
    sk_presets.apply_to_scene(context, data, transition_frames=0)

    state = context.scene.stormkit
    harness.assert_almost_equal(state.time_of_day, data["time_of_day"])
    harness.assert_equal(state.precipitation_type, data["precipitation_type"])
    harness.assert_almost_equal(state.storm_intensity, data["storm_intensity"])


def test_apply_to_scene_with_transition_keyframes_start_and_end():
    # Deliberately verified by *evaluating* the keyframed result at each
    # frame (frame_set + read the property) rather than by walking the
    # Action's internal fcurve/layer/strip structure — ground rule #3
    # calls out exactly this scenario ("preset transitions") as needing
    # the new slotted-action API on Blender 5.x, and this test has no
    # need to touch that API at all to prove the transition worked.
    _ensure_registered()
    context = bpy.context
    scene = context.scene
    scene.frame_set(10)
    scene.stormkit.wetness = 0.0

    data = sk_presets.load("blizzard")
    sk_presets.apply_to_scene(context, data, transition_frames=20)

    scene.frame_set(10)
    harness.assert_almost_equal(scene.stormkit.wetness, 0.0, tol=1e-3)

    scene.frame_set(30)
    harness.assert_almost_equal(scene.stormkit.wetness, data["wetness"], tol=1e-3)

    scene.frame_set(20)
    midpoint = scene.stormkit.wetness
    harness.assert_true(
        min(0.0, data["wetness"]) < midpoint < max(0.0, data["wetness"]) or data["wetness"] == 0.0,
        f"expected an interpolated midpoint value, got {midpoint}",
    )
