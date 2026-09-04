"""Tests for stormkit.fog — §4.6 build/idempotency/driver/teardown coverage."""

import bpy

from kuro_core import nodeutils
from stormkit import fog, properties
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


def test_build_creates_tagged_fog_object_and_material():
    _ensure_registered()
    context = bpy.context
    obj, mat = fog.build(context)

    harness.assert_equal(obj[nodeutils.ADDON_PROP], fog.ADDON_ID)
    harness.assert_equal(mat[nodeutils.ADDON_PROP], fog.ADDON_ID)
    harness.assert_true(obj.data.materials[0] == mat)
    volume_node = mat.node_tree.nodes[fog.VOLUME_NODE_NAME]
    harness.assert_true(len(volume_node.inputs["Density"].links) == 1)


def test_build_is_idempotent():
    _ensure_registered()
    context = bpy.context
    fog.build(context)
    fog.build(context)

    fog_objects = [o for o in bpy.data.objects if o.name == fog.FOG_OBJECT_NAME]
    harness.assert_equal(len(fog_objects), 1)
    fog_materials = [m for m in bpy.data.materials if m.name == fog.FOG_MATERIAL_NAME]
    harness.assert_equal(len(fog_materials), 1)
    fog_groups = [g for g in bpy.data.node_groups if g.name == fog.HEIGHT_FALLOFF_GROUP_NAME]
    harness.assert_equal(len(fog_groups), 1)


def test_fog_density_and_height_are_driven_from_scene_state():
    _ensure_registered()
    context = bpy.context
    obj, mat = fog.build(context)
    context.scene.stormkit.fog_density = 0.65
    context.scene.stormkit.fog_height = 4.5

    evaluated_mat = _eval(mat)
    group_instance = evaluated_mat.node_tree.nodes[fog.GROUP_INSTANCE_NAME]
    harness.assert_almost_equal(group_instance.inputs["Fog Density"].default_value, 0.65)
    harness.assert_almost_equal(group_instance.inputs["Fog Height"].default_value, 4.5)


def test_eevee_volumetrics_hint_never_raises():
    result = fog.eevee_volumetrics_hint(bpy.context)
    harness.assert_true(result in (True, None))


def test_teardown_removes_object_material_and_group():
    _ensure_registered()
    context = bpy.context
    fog.build(context)
    fog.teardown(context)

    harness.assert_true(bpy.data.objects.get(fog.FOG_OBJECT_NAME) is None)
    harness.assert_true(bpy.data.materials.get(fog.FOG_MATERIAL_NAME) is None)
    harness.assert_true(bpy.data.node_groups.get(fog.HEIGHT_FALLOFF_GROUP_NAME) is None)
