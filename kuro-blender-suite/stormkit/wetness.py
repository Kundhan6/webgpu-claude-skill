"""Surface wetness & snow-cover injection — §4.2.4, the hardest part of
StormKit: non-destructively wrapping existing materials via
kuro_core.nodeutils.inject_between/eject.

Injection mode (default): each material whose output is fed directly by a
Principled BSDF gets its Base Color/Roughness/Normal wrapped through a
shared SK_Wetness or SK_SnowCover group instance, driven by one global
scene slider. Materials that don't match that shape are skipped and
reported — never guessed at (§4.2.4 "Override mode").

NOTE on API confidence: the unified Mix node (data_type RGBA/FLOAT/VECTOR,
sockets Factor/A/B/Result), Map Range, Bump, and Geometry(Normal) are
long-standing stable nodes. Written without a live Blender to introspect
against — see DECISIONS.md and ground rule #2.
"""

import bpy

from kuro_core import compat, nodeutils

WETNESS_ADDON_ID = "stormkit:wetness"
SNOWCOVER_ADDON_ID = "stormkit:snowcover"
SNOW_GEOMETRY_ADDON_ID = "stormkit:snowgeometry"

WETNESS_GROUP_NAME = "SK_Wetness"
SNOWCOVER_GROUP_NAME = "SK_SnowCover"
SNOW_GEOMETRY_GROUP_NAME = "SK_SnowGeometry"


# ---------------------------------------------------------------------------
# Node group builders
# ---------------------------------------------------------------------------

def _build_wetness_group(tree):
    nodeutils.add_group_input(tree, "Base Color", "NodeSocketColor", default=(0.5, 0.5, 0.5, 1.0))
    nodeutils.add_group_input(tree, "Roughness", "NodeSocketFloat", default=0.5, min_value=0.0, max_value=1.0)
    nodeutils.add_group_input(tree, "Normal", "NodeSocketVector")
    nodeutils.add_group_input(tree, "Wetness", "NodeSocketFloat", default=0.0, min_value=0.0, max_value=1.0)
    nodeutils.add_group_output(tree, "Base Color", "NodeSocketColor")
    nodeutils.add_group_output(tree, "Roughness", "NodeSocketFloat")
    nodeutils.add_group_output(tree, "Normal", "NodeSocketVector")

    b = nodeutils.NodeGraphBuilder(tree)
    gi = b.add("NodeGroupInput", name="GroupInput")
    go = b.add("NodeGroupOutput", name="GroupOutput")

    # Base Color darkens toward ~55% at full wetness.
    darken_fixed = b.add("ShaderNodeMix", name="DarkenFixed", data_type="RGBA", Factor=0.45)
    darken_fixed.inputs["B"].default_value = (0.0, 0.0, 0.0, 1.0)
    b.link(gi, "Base Color", darken_fixed, "A")

    darken_by_wetness = b.add("ShaderNodeMix", name="DarkenByWetness", data_type="RGBA")
    b.link(gi, "Base Color", darken_by_wetness, "A")
    b.link(darken_fixed, "Result", darken_by_wetness, "B")
    b.link(gi, "Wetness", darken_by_wetness, "Factor")

    # Roughness drops toward 0.05 at full wetness.
    roughness_wet = b.add("ShaderNodeMix", name="RoughnessWet", data_type="FLOAT")
    roughness_wet.inputs["B"].default_value = 0.05
    b.link(gi, "Roughness", roughness_wet, "A")
    b.link(gi, "Wetness", roughness_wet, "Factor")

    # Puddle mask: up-facing normal x noise, hard ramp, grows with Wetness.
    geometry = b.add("ShaderNodeNewGeometry", name="Geometry")
    separate_n = b.add("ShaderNodeSeparateXYZ", name="SeparateNormalZ")
    b.link(geometry, "Normal", separate_n, "Vector")

    noise = b.add("ShaderNodeTexNoise", name="PuddleNoise", Scale=6.0, Detail=2.0)

    mask_raw = b.add("ShaderNodeMath", name="MaskRaw")
    mask_raw.operation = "MULTIPLY"
    b.link(separate_n, "Z", mask_raw, 0)
    b.link(noise, "Fac", mask_raw, 1)

    threshold = b.add("ShaderNodeMath", name="Threshold")
    threshold.operation = "SUBTRACT"
    threshold.inputs[0].default_value = 1.0
    b.link(gi, "Wetness", threshold, 1)

    from_min = b.add("ShaderNodeMath", name="FromMin")
    from_min.operation = "SUBTRACT"
    from_min.inputs[1].default_value = 0.05
    b.link(threshold, "Value", from_min, 0)

    from_max = b.add("ShaderNodeMath", name="FromMax")
    from_max.operation = "ADD"
    from_max.inputs[1].default_value = 0.05
    b.link(threshold, "Value", from_max, 0)

    puddle_mask = b.add("ShaderNodeMapRange", name="PuddleMask", **{"To Min": 0.0, "To Max": 1.0})
    puddle_mask.clamp = True
    b.link(mask_raw, "Value", puddle_mask, "Value")
    b.link(from_min, "Value", puddle_mask, "From Min")
    b.link(from_max, "Value", puddle_mask, "From Max")

    roughness_puddle = b.add("ShaderNodeMix", name="RoughnessPuddle", data_type="FLOAT")
    roughness_puddle.inputs["B"].default_value = 0.02
    b.link(roughness_wet, "Result", roughness_puddle, "A")
    b.link(puddle_mask, "Result", roughness_puddle, "Factor")

    normal_puddle = b.add("ShaderNodeMix", name="NormalPuddle", data_type="VECTOR")
    b.link(gi, "Normal", normal_puddle, "A")
    b.link(geometry, "Normal", normal_puddle, "B")
    b.link(puddle_mask, "Result", normal_puddle, "Factor")

    b.link(darken_by_wetness, "Result", go, "Base Color")
    b.link(roughness_puddle, "Result", go, "Roughness")
    b.link(normal_puddle, "Result", go, "Normal")

    b.tag_all(WETNESS_ADDON_ID)
    b.auto_layout()


def _build_snowcover_group(tree):
    nodeutils.add_group_input(tree, "Base Color", "NodeSocketColor", default=(0.5, 0.5, 0.5, 1.0))
    nodeutils.add_group_input(tree, "Roughness", "NodeSocketFloat", default=0.5, min_value=0.0, max_value=1.0)
    nodeutils.add_group_input(tree, "Normal", "NodeSocketVector")
    nodeutils.add_group_input(tree, "Snow Cover", "NodeSocketFloat", default=0.0, min_value=0.0, max_value=1.0)
    nodeutils.add_group_output(tree, "Base Color", "NodeSocketColor")
    nodeutils.add_group_output(tree, "Roughness", "NodeSocketFloat")
    nodeutils.add_group_output(tree, "Normal", "NodeSocketVector")

    b = nodeutils.NodeGraphBuilder(tree)
    gi = b.add("NodeGroupInput", name="GroupInput")
    go = b.add("NodeGroupOutput", name="GroupOutput")

    geometry = b.add("ShaderNodeNewGeometry", name="Geometry")
    separate_n = b.add("ShaderNodeSeparateXYZ", name="SeparateNormalZ")
    b.link(geometry, "Normal", separate_n, "Vector")

    noise = b.add("ShaderNodeTexNoise", name="EdgeNoise", Scale=8.0, Detail=3.0)

    mask_raw = b.add("ShaderNodeMath", name="MaskRaw")
    mask_raw.operation = "MULTIPLY"
    b.link(separate_n, "Z", mask_raw, 0)
    b.link(noise, "Fac", mask_raw, 1)

    threshold = b.add("ShaderNodeMath", name="Threshold")
    threshold.operation = "SUBTRACT"
    threshold.inputs[0].default_value = 1.0
    b.link(gi, "Snow Cover", threshold, 1)

    from_min = b.add("ShaderNodeMath", name="FromMin")
    from_min.operation = "SUBTRACT"
    from_min.inputs[1].default_value = 0.05
    b.link(threshold, "Value", from_min, 0)

    from_max = b.add("ShaderNodeMath", name="FromMax")
    from_max.operation = "ADD"
    from_max.inputs[1].default_value = 0.05
    b.link(threshold, "Value", from_max, 0)

    snow_mask = b.add("ShaderNodeMapRange", name="SnowMask", **{"To Min": 0.0, "To Max": 1.0})
    snow_mask.clamp = True
    b.link(mask_raw, "Value", snow_mask, "Value")
    b.link(from_min, "Value", snow_mask, "From Min")
    b.link(from_max, "Value", snow_mask, "From Max")

    snow_color = b.add("ShaderNodeMix", name="SnowColor", data_type="RGBA")
    snow_color.inputs["B"].default_value = (0.95, 0.96, 1.0, 1.0)
    b.link(gi, "Base Color", snow_color, "A")
    b.link(snow_mask, "Result", snow_color, "Factor")

    snow_roughness = b.add("ShaderNodeMix", name="SnowRoughness", data_type="FLOAT")
    snow_roughness.inputs["B"].default_value = 0.5
    b.link(gi, "Roughness", snow_roughness, "A")
    b.link(snow_mask, "Result", snow_roughness, "Factor")

    bump_noise = b.add("ShaderNodeTexNoise", name="BumpNoise", Scale=40.0, Detail=4.0)
    bump = b.add("ShaderNodeBump", name="SnowBump")
    bump.inputs["Strength"].default_value = 0.3
    b.link(bump_noise, "Fac", bump, "Height")
    b.link(gi, "Normal", bump, "Normal")

    snow_normal = b.add("ShaderNodeMix", name="SnowNormal", data_type="VECTOR")
    b.link(gi, "Normal", snow_normal, "A")
    b.link(bump, "Normal", snow_normal, "B")
    b.link(snow_mask, "Result", snow_normal, "Factor")

    b.link(snow_color, "Result", go, "Base Color")
    b.link(snow_roughness, "Result", go, "Roughness")
    b.link(snow_normal, "Result", go, "Normal")

    b.tag_all(SNOWCOVER_ADDON_ID)
    b.auto_layout()


def _build_snow_geometry_group(tree):
    nodeutils.add_group_input(tree, "Geometry", "NodeSocketGeometry")
    nodeutils.add_group_input(tree, "Snow Cover", "NodeSocketFloat", default=0.0, min_value=0.0, max_value=1.0)
    nodeutils.add_group_input(tree, "Max Thickness", "NodeSocketFloat", default=0.05, min_value=0.0, max_value=1.0)
    nodeutils.add_group_output(tree, "Geometry", "NodeSocketGeometry")

    b = nodeutils.NodeGraphBuilder(tree)
    gi = b.add("NodeGroupInput", name="GroupInput")
    go = b.add("NodeGroupOutput", name="GroupOutput")

    normal = b.add("GeometryNodeInputNormal", name="Normal")
    separate_n = b.add("ShaderNodeSeparateXYZ", name="SeparateNormalZ")
    b.link(normal, "Normal", separate_n, "Vector")

    selection = b.add("ShaderNodeMath", name="TopFacing")
    selection.operation = "GREATER_THAN"
    selection.inputs[1].default_value = 0.5
    b.link(separate_n, "Z", selection, 0)

    thickness = b.add("ShaderNodeMath", name="Thickness")
    thickness.operation = "MULTIPLY"
    b.link(gi, "Snow Cover", thickness, 0)
    b.link(gi, "Max Thickness", thickness, 1)

    extrude = b.add("GeometryNodeExtrudeMesh", name="Extrude")
    extrude.mode = "FACES"
    b.link(gi, "Geometry", extrude, "Mesh")
    b.link(selection, "Value", extrude, "Selection")
    b.link(thickness, "Value", extrude, "Offset Scale")

    b.link(extrude, "Mesh", go, "Geometry")

    b.tag_all(SNOW_GEOMETRY_ADDON_ID)
    b.auto_layout()


# ---------------------------------------------------------------------------
# Injection / ejection across the scene's materials
# ---------------------------------------------------------------------------

def _find_principled_feeding_output(material):
    """Return the Principled BSDF node directly feeding this material's
    active output, or None if the material's shader graph doesn't have
    that simple shape (§4.2.4 "skip and report, never guess")."""
    tree = material.node_tree
    if tree is None:
        return None
    outputs = [n for n in tree.nodes if n.bl_idname == "ShaderNodeOutputMaterial"]
    output = next((n for n in outputs if n.is_active_output), None) or (outputs[0] if outputs else None)
    if output is None:
        return None
    surface = output.inputs.get("Surface")
    if surface is None or not surface.links:
        return None
    source = surface.links[0].from_node
    if source.bl_idname != "ShaderNodeBsdfPrincipled":
        return None
    return source


def _inject(material, group_name, builder_fn, addon_id, driver_input_name, scene_path):
    tree = material.node_tree
    existing = next((n for n in tree.nodes if n.get(nodeutils.ADDON_PROP) == addon_id), None)
    if existing is not None:
        return existing, None

    bsdf = _find_principled_feeding_output(material)
    if bsdf is None:
        return None, "material output is not fed directly by a Principled BSDF"

    try:
        base_color_socket = compat.resolve_input_socket(bsdf, "Base Color")
        roughness_socket = compat.resolve_input_socket(bsdf, "Roughness")
        normal_socket = compat.resolve_input_socket(bsdf, "Normal")
    except compat.SocketResolutionError as e:
        return None, str(e)

    group_def = nodeutils.ensure_group(group_name, builder_fn, schema_version=1)
    group_node = tree.nodes.new("ShaderNodeGroup")
    group_node.name = f"{group_name}_{material.name}"
    group_node.label = group_name
    group_node.node_tree = group_def

    nodeutils.inject_between(tree, bsdf, base_color_socket.name, group_node, "Base Color", "Base Color", addon_id)
    nodeutils.inject_between(tree, bsdf, roughness_socket.name, group_node, "Roughness", "Roughness", addon_id)
    nodeutils.inject_between(tree, bsdf, normal_socket.name, group_node, "Normal", "Normal", addon_id)

    nodeutils.add_scene_driver(
        group_node.inputs[driver_input_name], "default_value", scene_path, scene=bpy.context.scene
    )
    return group_node, None


def apply_wetness_to_scene(materials=None):
    """Inject SK_Wetness into every material (or `materials`, if given)
    whose output is fed directly by a Principled BSDF. Returns
    (applied_names, skipped_name_reason_pairs)."""
    materials = list(materials) if materials is not None else list(bpy.data.materials)
    applied, skipped = [], []
    for mat in materials:
        if mat.node_tree is None:
            continue
        node, err = _inject(mat, WETNESS_GROUP_NAME, _build_wetness_group, WETNESS_ADDON_ID, "Wetness", "stormkit.wetness")
        if node is not None:
            applied.append(mat.name)
        else:
            skipped.append((mat.name, err))
    return applied, skipped


def apply_snowcover_to_scene(materials=None):
    materials = list(materials) if materials is not None else list(bpy.data.materials)
    applied, skipped = [], []
    for mat in materials:
        if mat.node_tree is None:
            continue
        node, err = _inject(
            mat, SNOWCOVER_GROUP_NAME, _build_snowcover_group, SNOWCOVER_ADDON_ID, "Snow Cover", "stormkit.snow_cover"
        )
        if node is not None:
            applied.append(mat.name)
        else:
            skipped.append((mat.name, err))
    return applied, skipped


def remove_wetness_from_scene():
    total = 0
    for mat in bpy.data.materials:
        if mat.node_tree is not None:
            total += nodeutils.eject(mat.node_tree, WETNESS_ADDON_ID)
    group = bpy.data.node_groups.get(WETNESS_GROUP_NAME)
    if group is not None and group.users == 0:
        bpy.data.node_groups.remove(group)
    return total


def remove_snowcover_from_scene():
    total = 0
    for mat in bpy.data.materials:
        if mat.node_tree is not None:
            total += nodeutils.eject(mat.node_tree, SNOWCOVER_ADDON_ID)
    group = bpy.data.node_groups.get(SNOWCOVER_GROUP_NAME)
    if group is not None and group.users == 0:
        bpy.data.node_groups.remove(group)
    return total


# ---------------------------------------------------------------------------
# Optional visible snow geometry (off by default — §4.2.4)
# ---------------------------------------------------------------------------

def add_snow_geometry(obj):
    group = nodeutils.ensure_group(
        SNOW_GEOMETRY_GROUP_NAME, _build_snow_geometry_group, schema_version=1, tree_type="GeometryNodeTree"
    )
    existing = next((m for m in obj.modifiers if m.type == "NODES" and m.node_group == group), None)
    if existing is not None:
        return existing
    mod = obj.modifiers.new(name="StormKit Snow Geometry", type="NODES")
    mod.node_group = group
    mod[nodeutils.ADDON_PROP] = SNOW_GEOMETRY_ADDON_ID
    identifiers = nodeutils.gn_input_identifiers(mod)
    snow_cover_id = identifiers.get("Snow Cover")
    if snow_cover_id:
        nodeutils.add_scene_driver(mod, f'["{snow_cover_id}"]', "stormkit.snow_cover", scene=bpy.context.scene)
    return mod


def remove_snow_geometry(obj):
    for mod in list(obj.modifiers):
        if mod.get(nodeutils.ADDON_PROP) == SNOW_GEOMETRY_ADDON_ID:
            obj.modifiers.remove(mod)
    group = bpy.data.node_groups.get(SNOW_GEOMETRY_GROUP_NAME)
    if group is not None and group.users == 0:
        bpy.data.node_groups.remove(group)


def register():
    pass


def unregister():
    pass
