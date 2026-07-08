"""Tests for stormkit.wind — §4.6 build/idempotency/driver/teardown coverage."""

import bpy

from kuro_core import nodeutils
from stormkit import properties, wind
from tests import harness


def _ensure_registered():
    try:
        properties.register()
    except ValueError:
        pass


def _eval(datablock):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    depsgraph.update()
    return datablock.evaluated_get(depsgraph)


def test_build_creates_tagged_wind_and_turbulence_fields():
    _ensure_registered()
    context = bpy.context
    wind_obj, turbulence_obj, group = wind.build(context)

    harness.assert_equal(wind_obj.field.type, "WIND")
    harness.assert_equal(turbulence_obj.field.type, "TURBULENCE")
    harness.assert_equal(wind_obj[nodeutils.ADDON_PROP], wind.ADDON_ID)
    harness.assert_equal(group.name, wind.WIND_SHADER_GROUP_NAME)


def test_build_is_idempotent():
    _ensure_registered()
    context = bpy.context
    wind.build(context)
    wind.build(context)

    wind_objs = [o for o in bpy.data.objects if o.name == wind.WIND_OBJECT_NAME]
    harness.assert_equal(len(wind_objs), 1)
    groups = [g for g in bpy.data.node_groups if g.name == wind.WIND_SHADER_GROUP_NAME]
    harness.assert_equal(len(groups), 1)


def test_wind_speed_and_turbulence_drive_field_strength():
    _ensure_registered()
    context = bpy.context
    wind_obj, turbulence_obj, _group = wind.build(context)

    context.scene.stormkit.wind_speed = 7.5
    context.scene.stormkit.turbulence = 0.4

    harness.assert_almost_equal(_eval(wind_obj).field.strength, 7.5)
    harness.assert_almost_equal(_eval(turbulence_obj).field.strength, 0.4)


def test_wind_direction_drives_rotation():
    _ensure_registered()
    context = bpy.context
    wind_obj, _turbulence_obj, _group = wind.build(context)

    context.scene.stormkit.wind_direction = 1.0
    harness.assert_almost_equal(_eval(wind_obj).rotation_euler[2], 1.0)


def test_teardown_removes_objects_and_group():
    _ensure_registered()
    context = bpy.context
    wind.build(context)
    wind.teardown(context)

    harness.assert_true(bpy.data.objects.get(wind.WIND_OBJECT_NAME) is None)
    harness.assert_true(bpy.data.objects.get(wind.TURBULENCE_OBJECT_NAME) is None)
    harness.assert_true(bpy.data.node_groups.get(wind.WIND_SHADER_GROUP_NAME) is None)
