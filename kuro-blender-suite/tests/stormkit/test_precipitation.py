"""Tests for stormkit.precipitation — §4.6 "GN evaluates at frames 1/50/250
without error (point counts > 0, bounded)", idempotency, and teardown."""

import bpy

from kuro_core import nodeutils
from stormkit import precipitation, properties
from tests import harness


def _ensure_registered():
    try:
        properties.register()
    except ValueError:
        pass


def _evaluated_vertex_count(obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        return len(mesh.vertices)
    finally:
        evaluated.to_mesh_clear()


def test_build_rain_creates_tagged_object_with_gn_modifier():
    _ensure_registered()
    context = bpy.context
    obj, modifier = precipitation.build(context, "RAIN")

    harness.assert_equal(obj[nodeutils.ADDON_PROP], precipitation.ADDON_ID)
    harness.assert_equal(obj[properties.PRECIP_KIND_PROP], "RAIN")
    harness.assert_equal(modifier.type, "NODES")
    harness.assert_equal(modifier.node_group.name, precipitation.RAIN_GROUP_NAME)


def test_build_snow_creates_tagged_object_with_gn_modifier():
    _ensure_registered()
    context = bpy.context
    obj, modifier = precipitation.build(context, "SNOW")

    harness.assert_equal(obj[properties.PRECIP_KIND_PROP], "SNOW")
    harness.assert_equal(modifier.node_group.name, precipitation.SNOW_GROUP_NAME)


def test_build_is_idempotent_for_both_kinds():
    _ensure_registered()
    context = bpy.context
    precipitation.build(context, "RAIN")
    precipitation.build(context, "RAIN")
    precipitation.build(context, "SNOW")
    precipitation.build(context, "SNOW")

    rain_objs = [o for o in bpy.data.objects if o.name == precipitation.RAIN_OBJECT_NAME]
    snow_objs = [o for o in bpy.data.objects if o.name == precipitation.SNOW_OBJECT_NAME]
    harness.assert_equal(len(rain_objs), 1)
    harness.assert_equal(len(snow_objs), 1)
    harness.assert_equal(len(rain_objs[0].modifiers), 1)


def test_rain_gn_evaluates_across_frames_without_raising():
    _ensure_registered()
    context = bpy.context
    obj, modifier = precipitation.build(context, "RAIN")

    identifiers = precipitation._input_identifiers(modifier)
    modifier[identifiers["Viewport Density"]] = 0.5

    counts = []
    for frame in (1, 50, 250):
        context.scene.frame_set(frame)
        counts.append(_evaluated_vertex_count(obj))

    for count in counts:
        harness.assert_true(count > 0, "expected nonzero geometry once instanced at density 0.5")
        harness.assert_true(
            count <= precipitation.MAX_VIEWPORT_POINTS * 200,
            f"vertex count {count} looks unbounded for a viewport-capped rain emitter",
        )


def test_zero_density_produces_no_points():
    _ensure_registered()
    context = bpy.context
    obj, modifier = precipitation.build(context, "SNOW")
    identifiers = precipitation._input_identifiers(modifier)
    modifier[identifiers["Viewport Density"]] = 0.0

    context.scene.frame_set(1)
    count = _evaluated_vertex_count(obj)
    harness.assert_equal(count, 0)


def test_teardown_removes_objects_groups_and_materials():
    _ensure_registered()
    context = bpy.context
    precipitation.build(context, "RAIN")
    precipitation.build(context, "SNOW")

    precipitation.teardown(context)

    harness.assert_true(bpy.data.objects.get(precipitation.RAIN_OBJECT_NAME) is None)
    harness.assert_true(bpy.data.objects.get(precipitation.SNOW_OBJECT_NAME) is None)
    harness.assert_true(bpy.data.node_groups.get(precipitation.RAIN_GROUP_NAME) is None)
    harness.assert_true(bpy.data.node_groups.get(precipitation.SNOW_GROUP_NAME) is None)


def test_render_pre_post_handlers_boost_and_restore_density():
    _ensure_registered()
    context = bpy.context
    obj, modifier = precipitation.build(context, "RAIN")
    identifiers = precipitation._input_identifiers(modifier)
    modifier[identifiers["Viewport Density"]] = 0.2

    precipitation._on_render_pre(context.scene)
    boosted = modifier[identifiers["Viewport Density"]]
    harness.assert_true(boosted > 0.2)

    precipitation._on_render_post(context.scene)
    restored = modifier[identifiers["Viewport Density"]]
    harness.assert_almost_equal(restored, 0.2)
