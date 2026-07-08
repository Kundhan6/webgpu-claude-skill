"""Tests for kuro_core.nodeutils — NodeGraphBuilder, ensure_group, inject/eject."""

import bpy

from kuro_core import nodeutils
from tests import harness


def _make_material(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    return mat


def test_builder_add_creates_node_with_inputs_set():
    mat = _make_material("kuro_nu_1")
    b = nodeutils.NodeGraphBuilder(mat)
    noise = b.add("ShaderNodeTexNoise", name="MyNoise", Scale=5.0)
    harness.assert_equal(noise.name, "MyNoise")
    harness.assert_almost_equal(noise.inputs["Scale"].default_value, 5.0)


def test_builder_add_bad_input_raises_key_error():
    mat = _make_material("kuro_nu_2")
    b = nodeutils.NodeGraphBuilder(mat)
    harness.assert_raises(KeyError, b.add, "ShaderNodeTexNoise", NotARealInput=1.0)


def test_builder_link_connects_sockets():
    mat = _make_material("kuro_nu_3")
    b = nodeutils.NodeGraphBuilder(mat)
    noise = b.add("ShaderNodeTexNoise", name="Noise")
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    b.link(noise, "Fac", bsdf, "Roughness")
    link = bsdf.inputs["Roughness"].links[0]
    harness.assert_true(link.from_node == noise)


def test_builder_link_accepts_integer_socket_index():
    # Math nodes expose two inputs both literally named "Value" — only an
    # integer index disambiguates them.
    mat = _make_material("kuro_nu_link_index")
    b = nodeutils.NodeGraphBuilder(mat)
    noise = b.add("ShaderNodeTexNoise", name="Noise")
    math = b.add("ShaderNodeMath", name="Math")
    math.operation = "SUBTRACT"
    b.link(noise, "Fac", math, 1)
    harness.assert_true(math.inputs[1].links[0].from_node == noise)
    harness.assert_true(len(math.inputs[0].links) == 0)


def test_tag_all_stamps_created_nodes_and_tree():
    mat = _make_material("kuro_nu_4")
    b = nodeutils.NodeGraphBuilder(mat)
    node = b.add("ShaderNodeTexNoise", name="Noise")
    b.tag_all("stormkit:test")
    harness.assert_equal(node[nodeutils.ADDON_PROP], "stormkit:test")
    harness.assert_equal(mat.node_tree[nodeutils.ADDON_PROP], "stormkit:test")


def test_auto_layout_orders_nodes_by_dependency_depth():
    mat = _make_material("kuro_nu_5")
    b = nodeutils.NodeGraphBuilder(mat)
    a = b.add("ShaderNodeTexNoise", name="A")
    c = b.add("ShaderNodeValToRGB", name="C")
    b.link(a, "Fac", c, "Fac")
    b.auto_layout()
    harness.assert_true(c.location.x > a.location.x, "downstream node should be placed further right")


def test_ensure_group_is_idempotent_across_calls():
    def build(tree):
        nodeutils.add_group_input(tree, "In", "NodeSocketFloat")
        nodeutils.add_group_output(tree, "Out", "NodeSocketFloat")

    g1 = nodeutils.ensure_group("KURO_TEST_GROUP", build, schema_version=1)
    g2 = nodeutils.ensure_group("KURO_TEST_GROUP", build, schema_version=1)
    harness.assert_true(g1 is g2, "re-registering must not duplicate the group")
    harness.assert_equal(len([g for g in bpy.data.node_groups if g.name.startswith("KURO_TEST_GROUP")]), 1)


def test_ensure_group_rebuilds_on_schema_version_bump():
    def build_v1(tree):
        nodeutils.add_group_input(tree, "In", "NodeSocketFloat")

    def build_v2(tree):
        nodeutils.add_group_input(tree, "In", "NodeSocketFloat")
        nodeutils.add_group_input(tree, "Extra", "NodeSocketFloat")

    g1 = nodeutils.ensure_group("KURO_TEST_GROUP_V", build_v1, schema_version=1)
    harness.assert_equal(len(g1.interface.items_tree), 1)
    g2 = nodeutils.ensure_group("KURO_TEST_GROUP_V", build_v2, schema_version=2)
    harness.assert_true(g1 is g2, "rebuild happens in place, same datablock")
    harness.assert_equal(len(g2.interface.items_tree), 2)


def _wetness_group():
    def build(tree):
        nodeutils.add_group_input(tree, "Base Color", "NodeSocketColor")
        nodeutils.add_group_output(tree, "Base Color", "NodeSocketColor")

    return nodeutils.ensure_group("KURO_TEST_WETNESS", build, schema_version=1)


def test_inject_between_reroutes_unlinked_default_and_eject_restores_it():
    mat = _make_material("kuro_nu_inject_1")
    tree = mat.node_tree
    bsdf = tree.nodes["Principled BSDF"]
    original = tuple(bsdf.inputs["Base Color"].default_value)

    group_def = _wetness_group()
    group_node = tree.nodes.new("ShaderNodeGroup")
    group_node.node_tree = group_def

    nodeutils.inject_between(tree, bsdf, "Base Color", group_node, "Base Color", "Base Color", "stormkit:wetness")

    # Base Color is now fed by the group, not a literal default.
    harness.assert_true(len(bsdf.inputs["Base Color"].links) == 1)
    harness.assert_true(bsdf.inputs["Base Color"].links[0].from_node == group_node)

    removed = nodeutils.eject(tree, "stormkit:wetness")
    harness.assert_equal(removed, 1)
    harness.assert_true(len(bsdf.inputs["Base Color"].links) == 0)
    restored = tuple(bsdf.inputs["Base Color"].default_value)
    for a, b in zip(original, restored):
        harness.assert_almost_equal(a, b)


def test_inject_between_preserves_and_restores_existing_link():
    mat = _make_material("kuro_nu_inject_2")
    tree = mat.node_tree
    bsdf = tree.nodes["Principled BSDF"]

    rgb = tree.nodes.new("ShaderNodeRGB")
    rgb.outputs["Color"].default_value = (0.1, 0.2, 0.3, 1.0)
    tree.links.new(rgb.outputs["Color"], bsdf.inputs["Base Color"])

    group_def = _wetness_group()
    group_node = tree.nodes.new("ShaderNodeGroup")
    group_node.node_tree = group_def

    nodeutils.inject_between(tree, bsdf, "Base Color", group_node, "Base Color", "Base Color", "stormkit:wetness")
    harness.assert_true(bsdf.inputs["Base Color"].links[0].from_node == group_node)
    harness.assert_true(group_node.inputs["Base Color"].links[0].from_node == rgb)

    nodeutils.eject(tree, "stormkit:wetness")
    harness.assert_true(bsdf.inputs["Base Color"].links[0].from_node == rgb, "original link must be restored exactly")


def test_add_scene_driver_mirrors_scene_property():
    scene = bpy.context.scene
    scene.unit_settings.scale_length = 2.0

    bpy.ops.object.empty_add(type="PLAIN_AXES")
    empty = bpy.context.active_object

    nodeutils.add_scene_driver(empty, "empty_display_size", "unit_settings.scale_length", scene=scene)

    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = empty.evaluated_get(depsgraph)
    harness.assert_almost_equal(evaluated.empty_display_size, 2.0)

    scene.unit_settings.scale_length = 3.0
    depsgraph = bpy.context.evaluated_depsgraph_get()
    depsgraph.update()
    evaluated = empty.evaluated_get(depsgraph)
    harness.assert_almost_equal(evaluated.empty_display_size, 3.0)


def test_eject_is_a_noop_for_untagged_tree():
    mat = _make_material("kuro_nu_inject_3")
    removed = nodeutils.eject(mat.node_tree, "stormkit:nonexistent")
    harness.assert_equal(removed, 0)
