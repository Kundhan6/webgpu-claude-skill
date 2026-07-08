"""Precipitation subsystem — §4.2.3. Geometry Nodes, not legacy particles.

One tagged GN object per type (rain/snow), parented to the active camera so
falling instances only ever exist where the camera can see them. Both
share one builder (`_build_precip_group`) parameterized by `kind`.

NOTE — highest-risk module in this add-on for API drift (ground rule #2):
this Geometry Nodes graph was authored without a live Blender to
introspect against (no `blender` binary in this dev container). The node
types and socket names below (Bounding Box, Mesh Grid, Distribute Points
on Faces in RANDOM mode, Align Euler to Vector, Instance on Points, Scene
Time, Random Value) are long-standing, stable GN nodes that predate the
API breaks ground rule #3 calls out by name (Musgrave, Action API, Grease
Pencil, EEVEE identifiers, Principled BSDF renames) — none of THOSE apply
here. Still: run scripts/introspect.py on Blender 5.1.2 and visually
open the SK_RainGN/SK_SnowGN node groups before a first real shot, per
ground rule #2. Any socket-name mismatch will surface as a clear KeyError
from NodeGraphBuilder rather than silently building garbage.
"""

import math

import bpy

from kuro_core import nodeutils
from stormkit.properties import PRECIP_KIND_PROP

ADDON_ID = "stormkit:precipitation"

RAIN_GROUP_NAME = "SK_RainGN"
SNOW_GROUP_NAME = "SK_SnowGN"
RAIN_OBJECT_NAME = "SK_Rain"
SNOW_OBJECT_NAME = "SK_Snow"
RAIN_MATERIAL_NAME = "SK_RainDropMaterial"
SNOW_MATERIAL_NAME = "SK_SnowFlakeMaterial"

# Hard viewport point-count cap (§4.2.3 "hard viewport cap"). Render uses
# RENDER_DENSITY_MULTIPLIER on top of the same 0-1 slider via the
# render_pre/render_post handlers below — see module docstring rationale
# in DECISIONS.md for why this lives in Python rather than in the graph
# (Geometry Nodes has no reliable cross-version way to branch on
# viewport-vs-render evaluation from inside the tree).
MAX_VIEWPORT_POINTS = 4000
RENDER_DENSITY_MULTIPLIER = 3.0

_KIND_DEFAULTS = {
    "RAIN": dict(
        fall_speed=9.0, flutter=0.0, wind_scale=0.6,
        instance_radius=0.004, instance_length=0.22,
    ),
    "SNOW": dict(
        fall_speed=1.5, flutter=0.35, wind_scale=1.4,
        instance_radius=0.012, instance_length=0.012,
    ),
}


def _build_precip_group(tree, kind):
    d = _KIND_DEFAULTS[kind]

    nodeutils.add_group_input(tree, "Geometry", "NodeSocketGeometry")
    nodeutils.add_group_input(tree, "Viewport Density", "NodeSocketFloat", default=0.4, min_value=0.0, max_value=1.0)
    nodeutils.add_group_input(tree, "Fall Speed", "NodeSocketFloat", default=d["fall_speed"], min_value=0.0, max_value=100.0)
    nodeutils.add_group_input(tree, "Wind Speed", "NodeSocketFloat", default=0.0, min_value=0.0, max_value=50.0)
    nodeutils.add_group_input(tree, "Wind Direction", "NodeSocketFloat", default=0.0, min_value=-math.pi * 2, max_value=math.pi * 2)
    nodeutils.add_group_input(tree, "Turbulence", "NodeSocketFloat", default=0.0, min_value=0.0, max_value=1.0)
    nodeutils.add_group_input(tree, "Flutter", "NodeSocketFloat", default=d["flutter"], min_value=0.0, max_value=1.0)
    nodeutils.add_group_input(tree, "Seed", "NodeSocketInt", default=0)
    nodeutils.add_group_output(tree, "Geometry", "NodeSocketGeometry")

    b = nodeutils.NodeGraphBuilder(tree)
    group_in = b.add("NodeGroupInput", name="GroupInput")
    group_out = b.add("NodeGroupOutput", name="GroupOutput")

    # --- emitter box bounds (works regardless of the object's scale) -----
    bbox = b.add("GeometryNodeBoundBox", name="BBox")
    b.link(group_in, "Geometry", bbox, "Geometry")

    box_size = b.add("ShaderNodeVectorMath", name="BoxSize")
    box_size.operation = "SUBTRACT"
    b.link(bbox, "Max", box_size, 0)
    b.link(bbox, "Min", box_size, 1)

    size_xyz = b.add("ShaderNodeSeparateXYZ", name="BoxSizeXYZ")
    b.link(box_size, "Vector", size_xyz, "Vector")

    min_xyz = b.add("ShaderNodeSeparateXYZ", name="BoxMinXYZ")
    b.link(bbox, "Min", min_xyz, "Vector")

    # --- scatter points across a grid matching the box's XY footprint ----
    grid = b.add("GeometryNodeMeshGrid", name="EmitGrid", **{"Vertices X": 2, "Vertices Y": 2})
    b.link(size_xyz, "X", grid, "Size X")
    b.link(size_xyz, "Y", grid, "Size Y")

    density_clamp = b.add("ShaderNodeClamp", name="DensityClamp")
    density_clamp.inputs["Min"].default_value = 0.0
    density_clamp.inputs["Max"].default_value = 1.0
    b.link(group_in, "Viewport Density", density_clamp, "Value")

    density_scaled = b.add("ShaderNodeMath", name="DensityScaled")
    density_scaled.operation = "MULTIPLY"
    density_scaled.inputs[1].default_value = float(MAX_VIEWPORT_POINTS)
    b.link(density_clamp, "Result", density_scaled, 0)

    distribute = b.add("GeometryNodeDistributePointsOnFaces", name="Distribute")
    distribute.distribute_method = "RANDOM"
    b.link(grid, "Mesh", distribute, "Mesh")
    b.link(density_scaled, "Value", distribute, "Density")
    b.link(group_in, "Seed", distribute, "Seed")

    # --- per-point hash + time -> falling motion ---
    index = b.add("GeometryNodeInputIndex", name="Index")
    random_val = b.add("FunctionNodeRandomValue", name="Hash")
    random_val.data_type = "FLOAT"
    b.link(index, "Index", random_val, "ID")
    b.link(group_in, "Seed", random_val, "Seed")

    scene_time = b.add("GeometryNodeInputSceneTime", name="SceneTime")

    fall_distance = b.add("ShaderNodeMath", name="FallDistance")
    fall_distance.operation = "MULTIPLY"
    b.link(scene_time, "Seconds", fall_distance, 0)
    b.link(group_in, "Fall Speed", fall_distance, 1)

    hash_offset = b.add("ShaderNodeMath", name="HashOffset")
    hash_offset.operation = "MULTIPLY"
    b.link(random_val, "Value", hash_offset, 0)
    b.link(size_xyz, "Z", hash_offset, 1)

    fall_plus_hash = b.add("ShaderNodeMath", name="FallPlusHash")
    fall_plus_hash.operation = "ADD"
    b.link(fall_distance, "Value", fall_plus_hash, 0)
    b.link(hash_offset, "Value", fall_plus_hash, 1)

    fall_wrapped = b.add("ShaderNodeMath", name="FallWrapped")
    fall_wrapped.operation = "MODULO"
    b.link(fall_plus_hash, "Value", fall_wrapped, 0)
    b.link(size_xyz, "Z", fall_wrapped, 1)

    # newZ = top - fallWrapped
    bbox_max_xyz = b.add("ShaderNodeSeparateXYZ", name="BoxMaxXYZ")
    b.link(bbox, "Max", bbox_max_xyz, "Vector")

    new_z = b.add("ShaderNodeMath", name="NewZ")
    new_z.operation = "SUBTRACT"
    b.link(bbox_max_xyz, "Z", new_z, 0)
    b.link(fall_wrapped, "Value", new_z, 1)

    # fall progress 0 (top) .. 1 (bottom), used to shear XY by wind + flutter
    fall_progress = b.add("ShaderNodeMath", name="FallProgress")
    fall_progress.operation = "DIVIDE"
    b.link(fall_wrapped, "Value", fall_progress, 0)
    b.link(size_xyz, "Z", fall_progress, 1)

    wind_x = b.add("ShaderNodeMath", name="WindDirCos")
    wind_x.operation = "COSINE"
    b.link(group_in, "Wind Direction", wind_x, 0)
    wind_y = b.add("ShaderNodeMath", name="WindDirSin")
    wind_y.operation = "SINE"
    b.link(group_in, "Wind Direction", wind_y, 0)

    wind_shear = b.add("ShaderNodeMath", name="WindShear")
    wind_shear.operation = "MULTIPLY"
    wind_shear.inputs[1].default_value = d["wind_scale"]
    b.link(group_in, "Wind Speed", wind_shear, 0)

    wind_shear_progress = b.add("ShaderNodeMath", name="WindShearByProgress")
    wind_shear_progress.operation = "MULTIPLY"
    b.link(wind_shear, "Value", wind_shear_progress, 0)
    b.link(fall_progress, "Value", wind_shear_progress, 1)

    drift_x = b.add("ShaderNodeMath", name="DriftX")
    drift_x.operation = "MULTIPLY"
    b.link(wind_shear_progress, "Value", drift_x, 0)
    b.link(wind_x, "Value", drift_x, 1)

    drift_y = b.add("ShaderNodeMath", name="DriftY")
    drift_y.operation = "MULTIPLY"
    b.link(wind_shear_progress, "Value", drift_y, 0)
    b.link(wind_y, "Value", drift_y, 1)

    # flutter: gentle sine sway for snow (Flutter=0 disables it for rain)
    flutter_phase = b.add("ShaderNodeMath", name="FlutterPhase")
    flutter_phase.operation = "MULTIPLY_ADD"
    flutter_phase.inputs[1].default_value = 3.0
    b.link(scene_time, "Seconds", flutter_phase, 0)
    b.link(random_val, "Value", flutter_phase, 2)

    flutter_sine = b.add("ShaderNodeMath", name="FlutterSine")
    flutter_sine.operation = "SINE"
    b.link(flutter_phase, "Value", flutter_sine, 0)

    flutter_amount = b.add("ShaderNodeMath", name="FlutterAmount")
    flutter_amount.operation = "MULTIPLY"
    b.link(flutter_sine, "Value", flutter_amount, 0)
    b.link(group_in, "Flutter", flutter_amount, 1)

    drift_x_total = b.add("ShaderNodeMath", name="DriftXTotal")
    drift_x_total.operation = "ADD"
    b.link(drift_x, "Value", drift_x_total, 0)
    b.link(flutter_amount, "Value", drift_x_total, 1)

    # --- combine into an absolute new position -----------------------
    orig_xyz = b.add("ShaderNodeSeparateXYZ", name="OrigXYZ")
    position_input = b.add("GeometryNodeInputPosition", name="OrigPosition")
    b.link(position_input, "Position", orig_xyz, "Vector")

    new_x = b.add("ShaderNodeMath", name="NewX")
    new_x.operation = "ADD"
    b.link(orig_xyz, "X", new_x, 0)
    b.link(drift_x_total, "Value", new_x, 1)

    new_y = b.add("ShaderNodeMath", name="NewY")
    new_y.operation = "ADD"
    b.link(orig_xyz, "Y", new_y, 0)
    b.link(drift_y, "Value", new_y, 1)

    new_position = b.add("ShaderNodeCombineXYZ", name="NewPosition")
    b.link(new_x, "Value", new_position, "X")
    b.link(new_y, "Value", new_position, "Y")
    b.link(new_z, "Value", new_position, "Z")

    set_position = b.add("GeometryNodeSetPosition", name="SetPosition")
    b.link(distribute, "Points", set_position, "Geometry")
    b.link(new_position, "Vector", set_position, "Position")

    # --- velocity direction for streak alignment -----------------------
    velocity = b.add("ShaderNodeCombineXYZ", name="Velocity")
    b.link(drift_x_total, "Value", velocity, "X")
    b.link(drift_y, "Value", velocity, "Y")
    fall_speed_negated = b.add("ShaderNodeMath", name="FallSpeedNegated")
    fall_speed_negated.operation = "MULTIPLY"
    fall_speed_negated.inputs[1].default_value = -1.0
    b.link(group_in, "Fall Speed", fall_speed_negated, 0)
    b.link(fall_speed_negated, "Value", velocity, "Z")

    align = b.add("FunctionNodeAlignEulerToVector", name="AlignToVelocity")
    align.axis = "Z"
    b.link(velocity, "Vector", align, "Vector")

    # --- instance geometry (kind-specific primitive) --------------------
    if kind == "RAIN":
        instance_mesh = b.add(
            "GeometryNodeMeshCylinder", name="DropMesh",
            **{"Radius": d["instance_radius"], "Depth": d["instance_length"], "Vertices": 6},
        )
        instance_output_socket = "Mesh"
    else:
        instance_mesh = b.add("GeometryNodeMeshIcoSphere", name="FlakeMesh", **{"Radius": d["instance_radius"]})
        instance_output_socket = "Mesh"

    instance_on_points = b.add("GeometryNodeInstanceOnPoints", name="InstanceOnPoints")
    b.link(set_position, "Geometry", instance_on_points, "Points")
    b.link(instance_mesh, instance_output_socket, instance_on_points, "Instance")
    b.link(align, "Rotation", instance_on_points, "Rotation")

    set_material = b.add("GeometryNodeSetMaterial", name="SetMaterial")
    b.link(instance_on_points, "Instances", set_material, "Geometry")

    b.link(set_material, "Geometry", group_out, "Geometry")

    b.tag_all(ADDON_ID)
    b.auto_layout()
    return set_material  # caller assigns .inputs["Material"].default_value


def _ensure_material(kind):
    name = RAIN_MATERIAL_NAME if kind == "RAIN" else SNOW_MATERIAL_NAME
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        if kind == "RAIN":
            bsdf.inputs["Base Color"].default_value = (0.75, 0.82, 0.9, 1.0)
            bsdf.inputs["Roughness"].default_value = 0.05
            bsdf.inputs["Transmission Weight"].default_value = 0.95
            bsdf.inputs["IOR"].default_value = 1.33
        else:
            bsdf.inputs["Base Color"].default_value = (0.95, 0.96, 1.0, 1.0)
            bsdf.inputs["Roughness"].default_value = 0.4
            bsdf.inputs["Subsurface Weight"].default_value = 0.3
    mat[nodeutils.ADDON_PROP] = ADDON_ID
    return mat


def _ensure_emitter_object(context, kind):
    name = RAIN_OBJECT_NAME if kind == "RAIN" else SNOW_OBJECT_NAME
    obj = bpy.data.objects.get(name)
    if obj is None:
        mesh = bpy.data.meshes.new(name)
        obj = bpy.data.objects.new(name, mesh)
        context.scene.collection.objects.link(obj)
        from stormkit.fog import bm_cube

        bm_cube(mesh)
        obj.scale = (10.0, 10.0, 6.0)
        obj.display_type = "WIRE"
        camera = context.scene.camera
        if camera is not None:
            obj.parent = camera
            obj.matrix_parent_inverse = camera.matrix_world.inverted()
            obj.location = (0.0, 0.0, -10.0)
    obj[nodeutils.ADDON_PROP] = ADDON_ID
    obj[PRECIP_KIND_PROP] = kind
    return obj


def _wire_drivers(context, modifier):
    scene = context.scene
    pairs = [
        ("Fall Speed", None),  # kind-tuned default; not scene-driven
        ("Wind Speed", "stormkit.wind_speed"),
        ("Wind Direction", "stormkit.wind_direction"),
        ("Turbulence", "stormkit.turbulence"),
    ]
    identifiers = _input_identifiers(modifier)
    density_id = identifiers.get("Viewport Density")
    if density_id:
        try:
            modifier.driver_remove(f'["{density_id}"]')
        except Exception:
            pass
        nodeutils.add_scene_driver(modifier, f'["{density_id}"]', "stormkit.precipitation_amount", scene=scene)

    for socket_name, scene_path in pairs:
        if scene_path is None:
            continue
        socket_id = identifiers.get(socket_name)
        if not socket_id:
            continue
        try:
            modifier.driver_remove(f'["{socket_id}"]')
        except Exception:
            pass
        nodeutils.add_scene_driver(modifier, f'["{socket_id}"]', scene_path, scene=scene)


_input_identifiers = nodeutils.gn_input_identifiers


def _ensure_modifier(obj, group, kind):
    mod = None
    for m in obj.modifiers:
        if m.type == "NODES" and m.node_group == group:
            mod = m
            break
    if mod is None:
        mod = obj.modifiers.new(name=f"StormKit {kind.title()}", type="NODES")
        mod.node_group = group
    mod[nodeutils.ADDON_PROP] = ADDON_ID
    return mod


def build(context, kind):
    """Idempotent — safe to call repeatedly. `kind` is 'RAIN' or 'SNOW'."""
    assert kind in ("RAIN", "SNOW")
    group_name = RAIN_GROUP_NAME if kind == "RAIN" else SNOW_GROUP_NAME

    def builder(tree):
        set_material_node = _build_precip_group(tree, kind)
        set_material_node.inputs["Material"].default_value = _ensure_material(kind)

    group = nodeutils.ensure_group(group_name, builder, schema_version=1, tree_type="GeometryNodeTree")
    obj = _ensure_emitter_object(context, kind)
    modifier = _ensure_modifier(obj, group, kind)
    _wire_drivers(context, modifier)
    return obj, modifier


def teardown(context, kind=None):
    kinds = ("RAIN", "SNOW") if kind is None else (kind,)
    for k in kinds:
        obj_name = RAIN_OBJECT_NAME if k == "RAIN" else SNOW_OBJECT_NAME
        obj = bpy.data.objects.get(obj_name)
        if obj is not None and obj.get(nodeutils.ADDON_PROP) == ADDON_ID:
            mesh = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh is not None and mesh.users == 0:
                bpy.data.meshes.remove(mesh)

        group_name = RAIN_GROUP_NAME if k == "RAIN" else SNOW_GROUP_NAME
        group = bpy.data.node_groups.get(group_name)
        if group is not None and group.users == 0:
            bpy.data.node_groups.remove(group)

        mat_name = RAIN_MATERIAL_NAME if k == "RAIN" else SNOW_MATERIAL_NAME
        mat = bpy.data.materials.get(mat_name)
        if mat is not None and mat.users == 0:
            bpy.data.materials.remove(mat)


# ---------------------------------------------------------------------------
# Render-time density boost (§4.2.3 "separate render multiplier") — an
# O(1) render_pre/render_post pair, not a per-frame handler.
# ---------------------------------------------------------------------------

_render_cache = {}


def _all_precip_modifiers():
    for obj in bpy.data.objects:
        for mod in obj.modifiers:
            if mod.type == "NODES" and mod.get(nodeutils.ADDON_PROP) == ADDON_ID:
                yield mod


def _on_render_pre(_scene, _depsgraph=None):
    for mod in _all_precip_modifiers():
        ids = _input_identifiers(mod)
        density_id = ids.get("Viewport Density")
        if not density_id:
            continue
        current = mod[density_id]
        _render_cache[mod.name] = current
        mod[density_id] = min(1.0, current * RENDER_DENSITY_MULTIPLIER)


def _on_render_post(_scene, _depsgraph=None):
    for mod in _all_precip_modifiers():
        if mod.name in _render_cache:
            ids = _input_identifiers(mod)
            density_id = ids.get("Viewport Density")
            if density_id:
                mod[density_id] = _render_cache.pop(mod.name)


def register():
    if _on_render_pre not in bpy.app.handlers.render_pre:
        bpy.app.handlers.render_pre.append(_on_render_pre)
    if _on_render_post not in bpy.app.handlers.render_post:
        bpy.app.handlers.render_post.append(_on_render_post)
    if _on_render_post not in bpy.app.handlers.render_cancel:
        bpy.app.handlers.render_cancel.append(_on_render_post)


def unregister():
    for handler_list in (bpy.app.handlers.render_pre, bpy.app.handlers.render_post, bpy.app.handlers.render_cancel):
        for fn in (_on_render_pre, _on_render_post):
            if fn in handler_list:
                handler_list.remove(fn)
