"""Wind subsystem — §4.2.5.

A tagged Wind force field (affects any cloth/particles the user already
has in the scene) plus a shared "SK_WindShader" node group that
precipitation and optional foliage materials can read for a consistent
vector wobble. `turbulence` additionally arms a Turbulence force field.

NOTE on API confidence: `Object.field` always exists (defaulting to
type='NONE') and is activated in place by setting `.type` — this avoids
needing the `effector_add` operator (which depends on view-layer/cursor
context we don't want this module to assume). Written without a live
Blender to confirm against — see DECISIONS.md and ground rule #2.
"""

import math

import bpy

from kuro_core import nodeutils

ADDON_ID = "stormkit:wind"

WIND_OBJECT_NAME = "SK_Wind"
TURBULENCE_OBJECT_NAME = "SK_Turbulence"
WIND_SHADER_GROUP_NAME = "SK_WindShader"


def _ensure_field_object(context, name, field_type):
    obj = bpy.data.objects.get(name)
    if obj is None:
        obj = bpy.data.objects.new(name, None)
        obj.empty_display_type = "SINGLE_ARROW" if field_type == "WIND" else "SPHERE"
        obj.empty_display_size = 1.5
        context.scene.collection.objects.link(obj)
    if obj.field is None or obj.field.type != field_type:
        obj.field.type = field_type
    obj[nodeutils.ADDON_PROP] = ADDON_ID
    return obj


def _clear_drivers(datablock, *data_paths):
    for path in data_paths:
        try:
            datablock.driver_remove(path)
        except Exception:
            pass


def _wire_wind_drivers(context, wind_obj, turbulence_obj):
    scene = context.scene

    _clear_drivers(wind_obj.field, "strength")
    nodeutils.add_scene_driver(wind_obj.field, "strength", "stormkit.wind_speed", scene=scene)

    # Wind blows along the object's local Z axis; tip it horizontal, then
    # sweep the compass heading with a Z-rotation driver (same convention
    # as sky.py's sun object).
    wind_obj.rotation_euler[0] = math.pi / 2.0
    _clear_drivers(wind_obj, "rotation_euler")
    fcurve = wind_obj.driver_add("rotation_euler", 2)
    driver = fcurve.driver
    driver.type = "AVERAGE"
    var = driver.variables.new()
    var.name = "v"
    var.type = "SINGLE_PROP"
    var.targets[0].id_type = "SCENE"
    var.targets[0].id = scene
    var.targets[0].data_path = "stormkit.wind_direction"

    _clear_drivers(turbulence_obj.field, "strength")
    nodeutils.add_scene_driver(turbulence_obj.field, "strength", "stormkit.turbulence", scene=scene)


def _build_wind_shader_group(tree):
    nodeutils.add_group_input(tree, "Wind Speed", "NodeSocketFloat", default=0.0, min_value=0.0, max_value=50.0)
    nodeutils.add_group_input(tree, "Wind Direction", "NodeSocketFloat", default=0.0, min_value=-math.pi * 2, max_value=math.pi * 2)
    nodeutils.add_group_input(tree, "Turbulence", "NodeSocketFloat", default=0.0, min_value=0.0, max_value=1.0)
    nodeutils.add_group_input(tree, "Scale", "NodeSocketFloat", default=1.0, min_value=0.01, max_value=100.0)
    nodeutils.add_group_output(tree, "Wobble", "NodeSocketVector")

    b = nodeutils.NodeGraphBuilder(tree)
    gi = b.add("NodeGroupInput", name="GroupInput")
    go = b.add("NodeGroupOutput", name="GroupOutput")

    position = b.add("ShaderNodeNewGeometry", name="Position")
    time = b.add("ShaderNodeValue", name="Time")  # driven by scene frame via add_scene_driver at apply time

    scaled_pos = b.add("ShaderNodeVectorMath", name="ScaledPosition")
    scaled_pos.operation = "SCALE"
    b.link(position, "Position", scaled_pos, "Vector")
    b.link(gi, "Scale", scaled_pos, "Scale")

    noise = b.add("ShaderNodeTexNoise", name="WobbleNoise", Detail=2.0)
    noise.noise_dimensions = "4D"
    b.link(scaled_pos, "Vector", noise, "Vector")
    b.link(time, "Value", noise, "W")

    remap = b.add("ShaderNodeVectorMath", name="RemapToSigned")
    remap.operation = "SUBTRACT"
    remap.inputs[1].default_value = (0.5, 0.5, 0.5)
    b.link(noise, "Color", remap, 0)

    wind_x = b.add("ShaderNodeMath", name="WindDirCos")
    wind_x.operation = "COSINE"
    b.link(gi, "Wind Direction", wind_x, 0)
    wind_y = b.add("ShaderNodeMath", name="WindDirSin")
    wind_y.operation = "SINE"
    b.link(gi, "Wind Direction", wind_y, 0)

    directional = b.add("ShaderNodeCombineXYZ", name="DirectionalWobble")
    speed_x = b.add("ShaderNodeMath", name="SpeedX")
    speed_x.operation = "MULTIPLY"
    b.link(gi, "Wind Speed", speed_x, 0)
    b.link(wind_x, "Value", speed_x, 1)
    speed_y = b.add("ShaderNodeMath", name="SpeedY")
    speed_y.operation = "MULTIPLY"
    b.link(gi, "Wind Speed", speed_y, 0)
    b.link(wind_y, "Value", speed_y, 1)
    b.link(speed_x, "Value", directional, "X")
    b.link(speed_y, "Value", directional, "Y")

    turbulence_scaled = b.add("ShaderNodeVectorMath", name="TurbulenceScaled")
    turbulence_scaled.operation = "SCALE"
    b.link(remap, "Vector", turbulence_scaled, "Vector")
    b.link(gi, "Turbulence", turbulence_scaled, "Scale")

    total = b.add("ShaderNodeVectorMath", name="TotalWobble")
    total.operation = "ADD"
    b.link(directional, "Vector", total, 0)
    b.link(turbulence_scaled, "Vector", total, 1)

    b.link(total, "Vector", go, "Wobble")

    b.tag_all(ADDON_ID)
    b.auto_layout()
    return time


def _wire_time_driver(time_node, scene):
    _clear_drivers(time_node.outputs[0], "default_value")
    nodeutils.add_scene_driver(time_node.outputs[0], "default_value", "frame_current", scene=scene)


def build(context):
    """Idempotent — safe to call repeatedly."""
    wind_obj = _ensure_field_object(context, WIND_OBJECT_NAME, "WIND")
    turbulence_obj = _ensure_field_object(context, TURBULENCE_OBJECT_NAME, "TURBULENCE")
    _wire_wind_drivers(context, wind_obj, turbulence_obj)

    time_node_holder = {}

    def builder(tree):
        time_node_holder["node"] = _build_wind_shader_group(tree)

    group = nodeutils.ensure_group(WIND_SHADER_GROUP_NAME, builder, schema_version=1)
    if "node" in time_node_holder:
        _wire_time_driver(time_node_holder["node"], context.scene)
    else:
        time_node = group.nodes.get("Time")
        if time_node is not None:
            _wire_time_driver(time_node, context.scene)
    return wind_obj, turbulence_obj, group


def teardown(context):
    for name in (WIND_OBJECT_NAME, TURBULENCE_OBJECT_NAME):
        obj = bpy.data.objects.get(name)
        if obj is not None and obj.get(nodeutils.ADDON_PROP) == ADDON_ID:
            bpy.data.objects.remove(obj, do_unlink=True)
    group = bpy.data.node_groups.get(WIND_SHADER_GROUP_NAME)
    if group is not None and group.users == 0:
        bpy.data.node_groups.remove(group)


def register():
    pass


def unregister():
    pass
