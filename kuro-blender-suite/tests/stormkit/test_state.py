"""§4.6 acceptance: state round-trip through save/load, cheap update callback."""

import bpy

from stormkit import properties
from tests import harness


def _ensure_registered():
    try:
        properties.register()
    except ValueError:
        pass  # already registered by an earlier test in this process


def test_state_roundtrip_through_save_and_load(path="/tmp/kuro_state_roundtrip.blend"):
    _ensure_registered()
    state = bpy.context.scene.stormkit
    state.time_of_day = 18.5
    state.overcast = 0.7
    state.fog_density = 0.3
    state.fog_height = 5.0
    state.precipitation_type = "SNOW"
    state.precipitation_amount = 0.9
    state.wind_speed = 12.0
    state.wind_direction = 1.2
    state.wetness = 0.4
    state.snow_cover = 0.6
    state.storm_intensity = 0.8
    state.turbulence = 0.2
    state.latitude = 51.5

    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)

    reloaded = bpy.context.scene.stormkit
    harness.assert_almost_equal(reloaded.time_of_day, 18.5)
    harness.assert_almost_equal(reloaded.overcast, 0.7)
    harness.assert_almost_equal(reloaded.fog_density, 0.3)
    harness.assert_almost_equal(reloaded.fog_height, 5.0)
    harness.assert_equal(reloaded.precipitation_type, "SNOW")
    harness.assert_almost_equal(reloaded.precipitation_amount, 0.9)
    harness.assert_almost_equal(reloaded.wind_speed, 12.0)
    harness.assert_almost_equal(reloaded.wind_direction, 1.2)
    harness.assert_almost_equal(reloaded.wetness, 0.4)
    harness.assert_almost_equal(reloaded.snow_cover, 0.6)
    harness.assert_almost_equal(reloaded.storm_intensity, 0.8)
    harness.assert_almost_equal(reloaded.turbulence, 0.2)
    harness.assert_almost_equal(reloaded.latitude, 51.5)


def test_precipitation_type_update_toggles_tagged_object_visibility():
    _ensure_registered()
    scene = bpy.context.scene

    bpy.ops.mesh.primitive_plane_add()
    rain_obj = bpy.context.active_object
    rain_obj.name = "SK_Rain"
    rain_obj[properties.PRECIP_KIND_PROP] = "RAIN"

    bpy.ops.mesh.primitive_plane_add()
    snow_obj = bpy.context.active_object
    snow_obj.name = "SK_Snow"
    snow_obj[properties.PRECIP_KIND_PROP] = "SNOW"

    scene.stormkit.precipitation_type = "RAIN"
    harness.assert_true(not rain_obj.hide_viewport)
    harness.assert_true(snow_obj.hide_viewport)

    scene.stormkit.precipitation_type = "SNOW"
    harness.assert_true(rain_obj.hide_viewport)
    harness.assert_true(not snow_obj.hide_viewport)
