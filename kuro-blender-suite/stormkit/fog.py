"""Ground fog subsystem — §4.2.2.

A single tagged cube volume object with a Principled Volume material whose
density is `fog_density * height_falloff(fog_height)`. Deliberately an
*object* volume, never a World volume — a world volume fills the entire
scene with no way to art-direct its extent and tanks render performance
(explicitly forbidden by the master plan).

NOTE on API confidence: `ShaderNodeVolumePrincipled`'s "Density" input and
the Geometry node's world-space "Position" output are long-standing,
stable Cycles/EEVEE-shared API. EEVEE's volumetric-enable property names
have moved across versions (EEVEE Next), so this module only best-effort
*detects* whether volumetrics look enabled and surfaces a UI hint rather
than writing to a property name that might not exist on this Blender —
see DECISIONS.md and ground rule #3.
"""

import bpy

from kuro_core import nodeutils

ADDON_ID = "stormkit:fog"

FOG_OBJECT_NAME = "SK_Fog"
FOG_MATERIAL_NAME = "SK_FogVolume"
HEIGHT_FALLOFF_GROUP_NAME = "SK_HeightFog"
VOLUME_NODE_NAME = "SK_PrincipledVolume"
GROUP_INSTANCE_NAME = "SK_HeightFogInstance"

DEFAULT_SIZE = (20.0, 20.0, 10.0)


def _build_height_falloff_group(tree):
    nodeutils.add_group_input(tree, "Fog Density", "NodeSocketFloat", default=0.3, min_value=0.0, max_value=1.0)
    nodeutils.add_group_input(tree, "Fog Height", "NodeSocketFloat", default=2.0, min_value=0.01, max_value=1000.0)
    nodeutils.add_group_output(tree, "Density", "NodeSocketFloat")

    b = nodeutils.NodeGraphBuilder(tree)
    group_in = b.add("NodeGroupInput", name="GroupInput")
    group_out = b.add("NodeGroupOutput", name="GroupOutput")

    geometry = b.add("ShaderNodeNewGeometry", name="Geometry")
    separate = b.add("ShaderNodeSeparateXYZ", name="SeparateZ")
    divide = b.add("ShaderNodeMath", name="DivideByHeight")
    divide.operation = "DIVIDE"
    clamp = b.add("ShaderNodeClamp", name="Clamp01")
    clamp.inputs["Min"].default_value = 0.0
    clamp.inputs["Max"].default_value = 1.0
    invert = b.add("ShaderNodeMath", name="Invert")
    invert.operation = "SUBTRACT"
    invert.inputs[0].default_value = 1.0
    multiply = b.add("ShaderNodeMath", name="MultiplyByDensity")
    multiply.operation = "MULTIPLY"

    b.link(geometry, "Position", separate, "Vector")
    b.link(separate, "Z", divide, 0)
    b.link(group_in, "Fog Height", divide, 1)
    b.link(divide, "Value", clamp, "Value")
    b.link(clamp, "Result", invert, 1)
    b.link(invert, "Value", multiply, 0)
    b.link(group_in, "Fog Density", multiply, 1)
    b.link(multiply, "Value", group_out, "Density")

    b.tag_all(ADDON_ID)
    b.auto_layout()


def _ensure_fog_material():
    mat = bpy.data.materials.get(FOG_MATERIAL_NAME)
    if mat is None:
        mat = bpy.data.materials.new(FOG_MATERIAL_NAME)
    if not mat.use_nodes:
        mat.use_nodes = True
    tree = mat.node_tree
    b = nodeutils.NodeGraphBuilder(tree)

    group_def = nodeutils.ensure_group(HEIGHT_FALLOFF_GROUP_NAME, _build_height_falloff_group, schema_version=1)

    group_instance = tree.nodes.get(GROUP_INSTANCE_NAME)
    if group_instance is None:
        group_instance = tree.nodes.new("ShaderNodeGroup")
        group_instance.name = group_instance.label = GROUP_INSTANCE_NAME
    group_instance.node_tree = group_def
    b.track(group_instance)

    volume = b.get_or_add("ShaderNodeVolumePrincipled", VOLUME_NODE_NAME)
    volume.inputs["Color"].default_value = (0.8, 0.82, 0.85, 1.0)

    output = next((n for n in tree.nodes if n.bl_idname == "ShaderNodeOutputMaterial"), None)
    if output is None:
        output = tree.nodes.new("ShaderNodeOutputMaterial")
    b.track(output)

    b.link(group_instance, "Density", volume, "Density")
    b.link(volume, "Volume", output, "Volume")
    # Deliberately leave Surface unlinked — this object contributes volume only.

    b.tag_all(ADDON_ID)
    b.auto_layout()

    mat[nodeutils.ADDON_PROP] = ADDON_ID
    return mat, group_instance


def _ensure_fog_object(context):
    obj = bpy.data.objects.get(FOG_OBJECT_NAME)
    if obj is None:
        mesh = bpy.data.meshes.new(FOG_OBJECT_NAME)
        obj = bpy.data.objects.new(FOG_OBJECT_NAME, mesh)
        context.scene.collection.objects.link(obj)
        bm_cube(mesh)
        obj.scale = DEFAULT_SIZE
        obj.location = (0.0, 0.0, DEFAULT_SIZE[2] / 2.0)
        obj.display_type = "WIRE"
    obj[nodeutils.ADDON_PROP] = ADDON_ID
    return obj


def bm_cube(mesh):
    """Build a unit cube (-0.5..0.5 per axis) directly via bmesh — avoids
    depending on bpy.ops.mesh.primitive_cube_add's active-object/context
    side effects, so this is safe to call from a background script."""
    import bmesh

    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(mesh)
    bm.free()


def eevee_volumetrics_hint(context):
    """Best-effort check for EEVEE volumetric support; returns True if a
    known volumetrics property is found, otherwise None ("couldn't
    verify on this Blender version — check manually"). Never raises."""
    eevee = getattr(context.scene, "eevee", None)
    if eevee is None:
        return None
    for attr in ("use_volumetric_lights", "use_volumetric_shadows", "volumetric_start", "volumetric_tile_size"):
        if hasattr(eevee, attr):
            return True
    return None


def _wire_drivers(context, group_instance):
    scene = context.scene
    for path in ("inputs[\"Fog Density\"].default_value", "inputs[\"Fog Height\"].default_value"):
        try:
            group_instance.driver_remove(path)
        except Exception:
            pass
    nodeutils.add_scene_driver(
        group_instance.inputs["Fog Density"], "default_value", "stormkit.fog_density", scene=scene
    )
    nodeutils.add_scene_driver(
        group_instance.inputs["Fog Height"], "default_value", "stormkit.fog_height", scene=scene
    )


def build(context):
    """Idempotent — safe to call repeatedly."""
    mat, group_instance = _ensure_fog_material()
    obj = _ensure_fog_object(context)
    if not obj.data.materials:
        obj.data.materials.append(mat)
    else:
        obj.data.materials[0] = mat
    _wire_drivers(context, group_instance)
    return obj, mat


def teardown(context):
    obj = bpy.data.objects.get(FOG_OBJECT_NAME)
    if obj is not None and obj.get(nodeutils.ADDON_PROP) == ADDON_ID:
        mesh = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if mesh is not None and mesh.users == 0:
            bpy.data.meshes.remove(mesh)

    mat = bpy.data.materials.get(FOG_MATERIAL_NAME)
    if mat is not None and mat.get(nodeutils.ADDON_PROP) == ADDON_ID and mat.users == 0:
        bpy.data.materials.remove(mat)

    group = bpy.data.node_groups.get(HEIGHT_FALLOFF_GROUP_NAME)
    if group is not None and group.users == 0:
        bpy.data.node_groups.remove(group)


def register():
    pass


def unregister():
    pass
