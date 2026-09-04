"""§4.6 acceptance: "Injection/ejection byte-level restore test across a
fixture library of 15 tricky materials (node groups, mix shaders,
no-Principled, muted nodes)." Also covers the skip-and-report override
path and the single global driver.
"""

import bpy

from kuro_core import nodeutils
from stormkit import properties, wetness
from tests import harness


def _ensure_registered():
    try:
        properties.register()
    except ValueError:
        pass


def _dv(socket):
    v = socket.default_value
    try:
        return tuple(v)
    except TypeError:
        return v


def _signature(material):
    tree = material.node_tree
    nodes = {}
    for node in tree.nodes:
        nodes[node.name] = (
            node.bl_idname,
            tuple(sorted((s.name, _dv(s)) for s in node.inputs if not s.is_linked)),
        )
    links = sorted(
        (l.from_node.name, l.from_socket.name, l.to_node.name, l.to_socket.name) for l in tree.links
    )
    return nodes, links


def _new_material(name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    return mat


def _principled(mat):
    return mat.node_tree.nodes["Principled BSDF"]


# --- 15 fixtures --------------------------------------------------------

def fixture_01_plain_defaults():
    return _new_material("fx01_plain")


def fixture_02_base_color_linked():
    mat = _new_material("fx02_basecolor")
    tree = mat.node_tree
    rgb = tree.nodes.new("ShaderNodeRGB")
    rgb.outputs["Color"].default_value = (0.2, 0.4, 0.6, 1.0)
    tree.links.new(rgb.outputs["Color"], _principled(mat).inputs["Base Color"])
    return mat


def fixture_03_roughness_linked():
    mat = _new_material("fx03_roughness")
    tree = mat.node_tree
    val = tree.nodes.new("ShaderNodeValue")
    val.outputs["Value"].default_value = 0.3
    tree.links.new(val.outputs["Value"], _principled(mat).inputs["Roughness"])
    return mat


def fixture_04_normal_linked():
    mat = _new_material("fx04_normal")
    tree = mat.node_tree
    nmap = tree.nodes.new("ShaderNodeNormalMap")
    tree.links.new(nmap.outputs["Normal"], _principled(mat).inputs["Normal"])
    return mat


def fixture_05_all_three_linked():
    mat = _new_material("fx05_all")
    tree = mat.node_tree
    bsdf = _principled(mat)
    rgb = tree.nodes.new("ShaderNodeRGB")
    rgb.outputs["Color"].default_value = (0.7, 0.1, 0.1, 1.0)
    tree.links.new(rgb.outputs["Color"], bsdf.inputs["Base Color"])
    val = tree.nodes.new("ShaderNodeValue")
    val.outputs["Value"].default_value = 0.6
    tree.links.new(val.outputs["Value"], bsdf.inputs["Roughness"])
    nmap = tree.nodes.new("ShaderNodeNormalMap")
    tree.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def fixture_06_image_texture_chain():
    mat = _new_material("fx06_imgtex")
    tree = mat.node_tree
    img = bpy.data.images.new("fx06_tex", 8, 8)
    tex = tree.nodes.new("ShaderNodeTexImage")
    tex.image = img
    ramp = tree.nodes.new("ShaderNodeValToRGB")
    tree.links.new(tex.outputs["Color"], ramp.inputs["Fac"])
    tree.links.new(ramp.outputs["Color"], _principled(mat).inputs["Base Color"])
    return mat


def fixture_07_foreign_node_group_upstream():
    mat = _new_material("fx07_foreigngroup")
    tree = mat.node_tree
    group_def = bpy.data.node_groups.new("Fx07ForeignGroup", "ShaderNodeTree")
    group_def.interface.new_socket(name="Out", in_out="OUTPUT", socket_type="NodeSocketColor")
    inner_b = nodeutils.NodeGraphBuilder(group_def)
    gout = inner_b.add("NodeGroupOutput", name="Out")
    gout.inputs["Out"].default_value = (0.3, 0.3, 0.3, 1.0)
    group_node = tree.nodes.new("ShaderNodeGroup")
    group_node.node_tree = group_def
    tree.links.new(group_node.outputs["Out"], _principled(mat).inputs["Base Color"])
    return mat


def fixture_08_muted_node_upstream():
    mat = _new_material("fx08_muted")
    tree = mat.node_tree
    rgb = tree.nodes.new("ShaderNodeRGB")
    rgb.mute = True
    rgb.outputs["Color"].default_value = (0.9, 0.9, 0.1, 1.0)
    tree.links.new(rgb.outputs["Color"], _principled(mat).inputs["Base Color"])
    return mat


def fixture_09_reroute_between():
    mat = _new_material("fx09_reroute")
    tree = mat.node_tree
    rgb = tree.nodes.new("ShaderNodeRGB")
    rgb.outputs["Color"].default_value = (0.1, 0.6, 0.3, 1.0)
    reroute = tree.nodes.new("NodeReroute")
    tree.links.new(rgb.outputs["Color"], reroute.inputs[0])
    tree.links.new(reroute.outputs[0], _principled(mat).inputs["Base Color"])
    return mat


def fixture_10_shared_upstream_source():
    mat = _new_material("fx10_shared")
    tree = mat.node_tree
    bsdf = _principled(mat)
    rgb = tree.nodes.new("ShaderNodeRGB")
    rgb.outputs["Color"].default_value = (0.4, 0.4, 0.4, 1.0)
    tree.links.new(rgb.outputs["Color"], bsdf.inputs["Base Color"])
    to_bw = tree.nodes.new("ShaderNodeRGBToBW")
    tree.links.new(rgb.outputs["Color"], to_bw.inputs["Color"])
    tree.links.new(to_bw.outputs["Val"], bsdf.inputs["Roughness"])
    return mat


def fixture_11_vector_math_normal():
    mat = _new_material("fx11_vecmath")
    tree = mat.node_tree
    vm = tree.nodes.new("ShaderNodeVectorMath")
    vm.operation = "NORMALIZE"
    vm.inputs[0].default_value = (0.1, 0.1, 1.0)
    tree.links.new(vm.outputs["Vector"], _principled(mat).inputs["Normal"])
    return mat


def fixture_12_no_principled_diffuse_only():
    mat = _new_material("fx12_diffuse_only")
    tree = mat.node_tree
    bsdf = tree.nodes["Principled BSDF"]
    tree.nodes.remove(bsdf)
    diffuse = tree.nodes.new("ShaderNodeBsdfDiffuse")
    output = next(n for n in tree.nodes if n.bl_idname == "ShaderNodeOutputMaterial")
    tree.links.new(diffuse.outputs["BSDF"], output.inputs["Surface"])
    return mat


def fixture_13_mix_shader_two_principled():
    mat = _new_material("fx13_mixshader")
    tree = mat.node_tree
    bsdf_a = tree.nodes["Principled BSDF"]
    bsdf_b = tree.nodes.new("ShaderNodeBsdfPrincipled")
    mix = tree.nodes.new("ShaderNodeMixShader")
    tree.links.new(bsdf_a.outputs["BSDF"], mix.inputs[1])
    tree.links.new(bsdf_b.outputs["BSDF"], mix.inputs[2])
    output = next(n for n in tree.nodes if n.bl_idname == "ShaderNodeOutputMaterial")
    for link in list(output.inputs["Surface"].links):
        tree.links.remove(link)
    tree.links.new(mix.outputs["Shader"], output.inputs["Surface"])
    return mat


def fixture_14_dark_metal_variant():
    mat = _new_material("fx14_darkmetal")
    bsdf = _principled(mat)
    bsdf.inputs["Base Color"].default_value = (0.05, 0.05, 0.06, 1.0)
    bsdf.inputs["Metallic"].default_value = 1.0
    bsdf.inputs["Roughness"].default_value = 0.15
    return mat


def fixture_15_inactive_secondary_output():
    mat = _new_material("fx15_dualoutput")
    tree = mat.node_tree
    bsdf = _principled(mat)
    extra_output = tree.nodes.new("ShaderNodeOutputMaterial")
    extra_output.is_active_output = False
    rgb = tree.nodes.new("ShaderNodeRGB")
    rgb.outputs["Color"].default_value = (0.5, 0.2, 0.8, 1.0)
    tree.links.new(rgb.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


RESTORABLE_FIXTURES = [
    fixture_01_plain_defaults,
    fixture_02_base_color_linked,
    fixture_03_roughness_linked,
    fixture_04_normal_linked,
    fixture_05_all_three_linked,
    fixture_06_image_texture_chain,
    fixture_07_foreign_node_group_upstream,
    fixture_08_muted_node_upstream,
    fixture_09_reroute_between,
    fixture_10_shared_upstream_source,
    fixture_11_vector_math_normal,
    fixture_14_dark_metal_variant,
    fixture_15_inactive_secondary_output,
]

SKIPPED_FIXTURES = [
    fixture_12_no_principled_diffuse_only,
    fixture_13_mix_shader_two_principled,
]


def test_all_15_fixtures_are_covered():
    harness.assert_equal(len(RESTORABLE_FIXTURES) + len(SKIPPED_FIXTURES), 15)


def test_wetness_inject_eject_is_byte_level_identical_on_all_restorable_fixtures():
    _ensure_registered()
    for make in RESTORABLE_FIXTURES:
        mat = make()
        before = _signature(mat)
        node, err = wetness._inject(
            mat, wetness.WETNESS_GROUP_NAME, wetness._build_wetness_group,
            wetness.WETNESS_ADDON_ID, "Wetness", "stormkit.wetness",
        )
        harness.assert_true(node is not None, f"{mat.name}: expected injection to succeed, got error: {err}")
        removed = nodeutils.eject(mat.node_tree, wetness.WETNESS_ADDON_ID)
        harness.assert_equal(removed, 1)
        after = _signature(mat)
        harness.assert_equal(before, after, f"{mat.name}: material not byte-identical after inject+eject")


def test_wetness_skips_and_reports_non_principled_materials():
    _ensure_registered()
    for make in SKIPPED_FIXTURES:
        mat = make()
        before = _signature(mat)
        node, err = wetness._inject(
            mat, wetness.WETNESS_GROUP_NAME, wetness._build_wetness_group,
            wetness.WETNESS_ADDON_ID, "Wetness", "stormkit.wetness",
        )
        harness.assert_true(node is None, f"{mat.name}: expected injection to be skipped")
        harness.assert_true(bool(err), f"{mat.name}: expected a human-readable skip reason")
        after = _signature(mat)
        harness.assert_equal(before, after, f"{mat.name}: skipped material must be left untouched")


def test_apply_wetness_to_scene_reports_applied_and_skipped():
    _ensure_registered()
    materials = [make() for make in (RESTORABLE_FIXTURES + SKIPPED_FIXTURES)]
    applied, skipped = wetness.apply_wetness_to_scene(materials)
    harness.assert_equal(len(applied), len(RESTORABLE_FIXTURES))
    harness.assert_equal(len(skipped), len(SKIPPED_FIXTURES))


def test_single_global_driver_controls_every_injected_instance():
    _ensure_registered()
    mats = [fixture_02_base_color_linked(), fixture_05_all_three_linked()]
    wetness.apply_wetness_to_scene(mats)
    bpy.context.scene.stormkit.wetness = 0.77

    depsgraph = bpy.context.evaluated_depsgraph_get()
    depsgraph.update()
    for mat in mats:
        evaluated = mat.evaluated_get(depsgraph)
        group_node = next(n for n in evaluated.node_tree.nodes if n.get(nodeutils.ADDON_PROP) == wetness.WETNESS_ADDON_ID)
        harness.assert_almost_equal(group_node.inputs["Wetness"].default_value, 0.77)


def test_remove_wetness_from_scene_ejects_everything_and_purges_group():
    _ensure_registered()
    mats = [make() for make in RESTORABLE_FIXTURES]
    wetness.apply_wetness_to_scene(mats)

    removed = wetness.remove_wetness_from_scene()
    harness.assert_equal(removed, len(RESTORABLE_FIXTURES))
    harness.assert_true(bpy.data.node_groups.get(wetness.WETNESS_GROUP_NAME) is None)


def test_wetness_and_snowcover_stack_and_unwind_in_order():
    _ensure_registered()
    mat = fixture_02_base_color_linked()
    before = _signature(mat)

    wetness.apply_wetness_to_scene([mat])
    wetness.apply_snowcover_to_scene([mat])

    removed_snow = wetness.remove_snowcover_from_scene()
    removed_wet = wetness.remove_wetness_from_scene()
    harness.assert_equal(removed_snow, 1)
    harness.assert_equal(removed_wet, 1)

    after = _signature(mat)
    harness.assert_equal(before, after, "stacked wetness+snowcover must fully unwind in reverse order")
