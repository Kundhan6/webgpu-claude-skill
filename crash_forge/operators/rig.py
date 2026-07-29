"""Stage 4 — Rig: the master build_rig pipeline (World, Mass, Deform,
Crumple-then-Shatter, Fracture, Detach, Passive, Impact Target, Dust),
pick_fracture_origin, and rebuild_from_tags.

Every step that depends on Cell Fracture or Mantaflow is wrapped so a
missing/renamed dependency reports cleanly instead of crashing the whole
pipeline — those two are the addon's only leans on Blender's own code
rather than pure bpy, per the spec's Known Risks.
"""

import bmesh
import bpy
from bpy.props import IntProperty
from bpy.types import Operator
from bpy_extras import view3d_utils
from mathutils import Vector

from ..properties import (
    CRUMPLE_INTENSITY_PARAMS,
    MATERIAL_DENSITY_KG_M3,
    SLOWMO_SUBSTEPS_ITERATIONS,
)
from ..utils import env_check

# --- Placeholder tuning constants (flagged — confirm once tested in Blender) ---

BOOST_WINDOW_FRAMES = 15
BOOST_SUBSTEPS_MIN = 80
BOOST_ITERATIONS_MIN = 60

NAMED_PART_MASS_KG = {
    "chassis": 300.0,
    "hood": 15.0,
    "bumper": 8.0,
}

BREAKING_THRESHOLD_BY_MATERIAL = {
    'STEEL': 8000.0,
    'GLASS': 200.0,
    'RUBBER': 1500.0,
    'PLASTIC': 600.0,
    'TRIM_CHROME': 400.0,
    'CONCRETE': 12000.0,
    'INTERIOR_FABRIC': 150.0,
}

FRACTURE_INNER_SOURCE_LIMIT = 100
FRACTURE_MARGIN = 0.001

CLOTH_QUALITY_STEPS = 12
CLOTH_COLLISION_QUALITY = 5
CLOTH_DISTANCE_MIN = 0.0015

# Collider settings on everything cloth can hit — placeholders, tune once
# crumple is visible in Blender.
COLLIDER_THICKNESS_OUTER = 0.02
COLLIDER_DAMPING = 0.1

DUST_RESOLUTION_MAX = 96
DUST_NOISE_POS_SCALE = 2.0


def _mark_generated(obj):
    obj.crashforge.crashforge_generated = True


def _mark_modifier_generated(modifier):
    modifier["crashforge_generated"] = True


def _ensure_rigid_body(context, obj, body_type):
    if obj.rigid_body is None:
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        context.view_layer.objects.active = obj
        bpy.ops.rigidbody.object_add(type=body_type)
    else:
        obj.rigid_body.type = body_type
    return obj.rigid_body


# --- Step 1: World ---------------------------------------------------------

def _configure_world(context, scene):
    if scene.rigidbody_world is None:
        bpy.ops.rigidbody.world_add()
    world = scene.rigidbody_world
    if world.collection is None:
        world.collection = bpy.data.collections.new("CrashForgeRigidBodyWorld")

    substeps, iterations = SLOWMO_SUBSTEPS_ITERATIONS[scene.crashforge.slowmo_amount]
    world.substeps_per_frame = substeps
    world.solver_iterations = iterations

    impact_frame = scene.crashforge.impact_frame
    if not impact_frame:
        return

    boosted_substeps = max(substeps, BOOST_SUBSTEPS_MIN)
    boosted_iterations = max(iterations, BOOST_ITERATIONS_MIN)
    window = BOOST_WINDOW_FRAMES

    keys = (
        (max(scene.frame_start, impact_frame - window), substeps, iterations),
        (max(scene.frame_start, impact_frame - window + 1), boosted_substeps, boosted_iterations),
        (impact_frame + window - 1, boosted_substeps, boosted_iterations),
        (impact_frame + window, substeps, iterations),
    )
    for frame, sub_val, iter_val in keys:
        world.substeps_per_frame = sub_val
        world.keyframe_insert(data_path="substeps_per_frame", frame=frame)
        world.solver_iterations = iter_val
        world.keyframe_insert(data_path="solver_iterations", frame=frame)

    if scene.animation_data and scene.animation_data.action:
        from ..utils import fcurve_compat
        for data_path in ("rigidbody_world.substeps_per_frame", "rigidbody_world.solver_iterations"):
            fcurve = fcurve_compat.get_fcurve(scene.animation_data.action, data_path)
            if fcurve is not None:
                for kp in fcurve.keyframe_points:
                    kp.interpolation = 'CONSTANT'


# --- Step 2: Mass ------------------------------------------------------------

def _apply_named_part_mass(obj):
    name_lower = obj.name.lower()
    for keyword, mass in NAMED_PART_MASS_KG.items():
        if keyword in name_lower:
            obj.rigid_body.mass = mass
            return True
    return False


def _apply_density_mass(context, obj, density):
    try:
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        context.view_layer.objects.active = obj
        bpy.ops.rigidbody.mass_calculate(material='Custom', density=density)
    except Exception:
        dims = obj.dimensions
        volume = max(dims.x * dims.y * dims.z, 1e-6)
        obj.rigid_body.mass = volume * density


def _configure_mass(context, objects):
    by_class = {}
    for obj in objects:
        if obj.rigid_body is None:
            continue
        if _apply_named_part_mass(obj):
            continue
        by_class.setdefault(obj.crashforge.material_class, []).append(obj)

    for material_class, group in by_class.items():
        density = MATERIAL_DENSITY_KG_M3.get(material_class, 1000)
        for obj in group:
            _apply_density_mass(context, obj, density)


# --- Step 3: Deform ----------------------------------------------------------

def _apply_deform(obj, crumple_intensity):
    mod = obj.modifiers.new(name="CrashForgeCloth", type='CLOTH')
    mod.settings.quality_steps = CLOTH_QUALITY_STEPS
    mod.collision_settings.collision_quality = CLOTH_COLLISION_QUALITY
    mod.collision_settings.distance_min = CLOTH_DISTANCE_MIN
    mod.collision_settings.use_self_collision = True
    if hasattr(mod.collision_settings, "self_distance_min"):
        mod.collision_settings.self_distance_min = CLOTH_DISTANCE_MIN

    tension, compression, bending = CRUMPLE_INTENSITY_PARAMS[crumple_intensity]
    mod.settings.tension_stiffness = tension
    mod.settings.compression_stiffness = compression
    mod.settings.bending_stiffness = bending

    if "Mounts" in obj.vertex_groups:
        mod.settings.vertex_group_mass = "Mounts"

    _mark_modifier_generated(mod)
    return mod


def _ensure_collider(obj):
    """Give obj a COLLISION modifier so cloth actually collides with it.

    Cloth and rigid bodies are two separate solvers: a PASSIVE rigid body
    does NOT stop cloth. Without this, a crumpling panel passes straight
    through the divider. Note the coupling is one-way — cloth reacts to the
    collider, but exerts no force back on it, so crumple is cosmetic and
    feeds no momentum into the rigid body sim.
    """
    for mod in obj.modifiers:
        if mod.type == 'COLLISION':
            return mod

    mod = obj.modifiers.new(name="CrashForgeCollision", type='COLLISION')
    settings = getattr(obj, "collision", None)
    if settings is not None:
        # Thickness_outer keeps fast cloth from punching through a thin wall.
        if hasattr(settings, "thickness_outer"):
            settings.thickness_outer = COLLIDER_THICKNESS_OUTER
        if hasattr(settings, "damping"):
            settings.damping = COLLIDER_DAMPING
    _mark_modifier_generated(mod)
    return mod


def _setup_cloth_colliders(scene, deform_objects):
    """Every mesh a DEFORM part could touch needs to be a cloth collider."""
    if not deform_objects:
        return 0

    deform_names = {o.name for o in deform_objects}
    count = 0
    for obj in scene.objects:
        if obj.type != 'MESH' or obj.name in deform_names:
            continue
        # Anything solid in the scene is a potential crumple surface: the
        # divider, the chassis, static props, and the car itself.
        _ensure_collider(obj)
        count += 1
    return count


# --- Step 4: Crumple-then-Shatter --------------------------------------------

def _find_peak_crush_frame(context, obj, frame_start, frame_end):
    rest_coords = [v.co.copy() for v in obj.data.vertices]
    scene = context.scene
    original_frame = scene.frame_current
    best_frame = frame_start
    best_displacement = -1.0

    for frame in range(frame_start, frame_end + 1):
        scene.frame_set(frame)
        depsgraph = context.evaluated_depsgraph_get()
        eval_obj = obj.evaluated_get(depsgraph)
        eval_mesh = eval_obj.to_mesh()
        if len(eval_mesh.vertices) == len(rest_coords):
            displacement = sum((v.co - rest_coords[i]).length for i, v in enumerate(eval_mesh.vertices))
            if displacement > best_displacement:
                best_displacement = displacement
                best_frame = frame
        eval_obj.to_mesh_clear()

    scene.frame_set(original_frame)
    return best_frame


def _bake_crumple_to_shape_key(context, obj, frame):
    scene = context.scene
    original_frame = scene.frame_current
    scene.frame_set(frame)

    depsgraph = context.evaluated_depsgraph_get()
    eval_obj = obj.evaluated_get(depsgraph)
    eval_mesh = eval_obj.to_mesh()

    if obj.data.shape_keys is None:
        obj.shape_key_add(name="Basis", from_mix=False)
    key = obj.shape_key_add(name="CrashForgeCrumpled", from_mix=False)
    for i, v in enumerate(eval_mesh.vertices):
        if i < len(key.data):
            key.data[i].co = v.co.copy()

    # Bake the crumpled shape into the base mesh too, so Fracture (step 5)
    # operates on real geometry rather than depending on shape-key evaluation.
    for i, v in enumerate(obj.data.vertices):
        if i < len(eval_mesh.vertices):
            v.co = eval_mesh.vertices[i].co.copy()

    eval_obj.to_mesh_clear()
    scene.frame_set(original_frame)
    key.value = 1.0

    for mod in list(obj.modifiers):
        if mod.get("crashforge_generated") and mod.type == 'CLOTH':
            obj.modifiers.remove(mod)

    return key


def _apply_crumple_then_shatter(context, obj, scene):
    frame_start = scene.frame_start
    frame_end = scene.crashforge.impact_frame or scene.crashforge.drive_end_frame or scene.frame_end
    if frame_end <= frame_start:
        return
    peak_frame = _find_peak_crush_frame(context, obj, frame_start, frame_end)
    _bake_crumple_to_shape_key(context, obj, peak_frame)


# --- Step 5: Fracture ---------------------------------------------------------

def _run_cell_fracture(obj, source_limit, use_remove_original=True):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    kwargs = dict(
        source={'VERT_OWN'},
        source_limit=source_limit,
        source_noise=0.1,
        cell_scale=(1.0, 1.0, 1.0),
        recursion=0,
        use_smooth_faces=False,
        use_sharp_edges=True,
        use_sharp_edges_apply=True,
        margin=FRACTURE_MARGIN,
        material_index=0,
        use_interior_vgroup=False,
        mass_mode='VOLUME',
        use_recenter=True,
        use_remove_original=use_remove_original,
    )
    try:
        bpy.ops.object.add_fracture_cell_objects(**kwargs)
    except TypeError:
        # Parameter names have shifted across Cell Fracture/Blender versions
        # (e.g. group_name -> collection_name) — retry with defaults only.
        bpy.ops.object.add_fracture_cell_objects()

    fragments = [o for o in bpy.context.selected_objects if o is not obj]
    for frag in fragments:
        _mark_generated(frag)
    return fragments


def _delete_verts_by_distance(obj, origin_local, radius, keep_inside):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    to_delete = [v for v in bm.verts if ((v.co - origin_local).length <= radius) != keep_inside]
    bmesh.ops.delete(bm, geom=to_delete, context='VERTS')
    bm.to_mesh(obj.data)
    bm.free()


def _split_by_distance(context, obj, origin_local, radius):
    inner = obj.copy()
    inner.data = obj.data.copy()
    inner.name = f"{obj.name}_FractureInner"
    context.collection.objects.link(inner)

    outer = obj.copy()
    outer.data = obj.data.copy()
    outer.name = f"{obj.name}_FractureOuter"
    context.collection.objects.link(outer)

    _delete_verts_by_distance(inner, origin_local, radius, keep_inside=True)
    _delete_verts_by_distance(outer, origin_local, radius, keep_inside=False)
    return inner, outer


def _apply_fracture(context, obj, scene, outer_multiplier):
    origin_world = Vector(obj.crashforge.fracture_origin)
    if origin_world.length == 0 and scene.crashforge.impact_frame:
        origin_world = Vector(scene.crashforge.impact_location)
    origin_local = obj.matrix_world.inverted() @ origin_world

    radius = scene.crashforge.fracture_falloff_radius
    inner, outer = _split_by_distance(context, obj, origin_local, radius)

    fragments = []
    outer_limit = max(1, int(FRACTURE_INNER_SOURCE_LIMIT * outer_multiplier))

    if len(inner.data.vertices) > 0:
        fragments += _run_cell_fracture(inner, FRACTURE_INNER_SOURCE_LIMIT)
    else:
        bpy.data.objects.remove(inner, do_unlink=True)

    if len(outer.data.vertices) > 0:
        fragments += _run_cell_fracture(outer, outer_limit)
    else:
        bpy.data.objects.remove(outer, do_unlink=True)

    collection = bpy.data.collections.get(f"CrashForge_Fragments_{obj.name}")
    if collection is None:
        collection = bpy.data.collections.new(f"CrashForge_Fragments_{obj.name}")
        scene.collection.children.link(collection)
    density = MATERIAL_DENSITY_KG_M3.get(obj.crashforge.material_class, 1000)
    for frag in fragments:
        for coll in list(frag.users_collection):
            coll.objects.unlink(frag)
        collection.objects.link(frag)
        frag.crashforge.material_class = obj.crashforge.material_class
        _ensure_rigid_body(context, frag, 'ACTIVE')
        _apply_density_mass(context, frag, density)

    if obj.name in bpy.data.objects:
        bpy.data.objects.remove(obj, do_unlink=True)

    return fragments


# --- Step 6: Detach ------------------------------------------------------------

def _nearest_passive(scene, obj):
    candidates = [o for o in scene.objects if o.type == 'MESH' and o.crashforge.role == 'PASSIVE']
    if not candidates:
        return None
    return min(candidates, key=lambda o: (o.matrix_world.translation - obj.matrix_world.translation).length)


def _apply_detach(context, obj, scene):
    anchor = obj.parent if (obj.parent and obj.parent.crashforge.role == 'PASSIVE') else _nearest_passive(scene, obj)
    if anchor is None:
        return None

    empty = bpy.data.objects.new(f"CrashForgeDetach_{obj.name}", None)
    empty.location = obj.matrix_world.translation
    scene.collection.objects.link(empty)
    _mark_generated(empty)

    bpy.ops.object.select_all(action='DESELECT')
    empty.select_set(True)
    context.view_layer.objects.active = empty
    bpy.ops.rigidbody.constraint_add(type='FIXED')
    constraint = empty.rigid_body_constraint
    constraint.object1 = obj
    constraint.object2 = anchor
    constraint.breaking_threshold = BREAKING_THRESHOLD_BY_MATERIAL.get(obj.crashforge.material_class, 1000.0)
    constraint.use_breaking = True

    return empty


# --- Step 7: Passive -----------------------------------------------------------

def _apply_passive_and_driven(context, scene, objects):
    car = scene.crashforge.car_object
    for obj in objects:
        if obj is car:
            continue
        if obj.crashforge.role == 'PASSIVE':
            _ensure_rigid_body(context, obj, 'PASSIVE')

    if car is not None:
        _ensure_rigid_body(context, car, 'ACTIVE')


# --- Step 8: Impact Target ------------------------------------------------------

def _apply_impact_target(context, scene, outer_multiplier):
    target = scene.crashforge.impact_target
    if target is None:
        return
    target.crashforge.material_class = 'CONCRETE'
    target_name = target.name
    _apply_fracture(context, target, scene, outer_multiplier)

    # Fragments are already ACTIVE rigid bodies from _apply_fracture — kept
    # dynamic (not PASSIVE) so Bullet's bidirectional impulse with the car
    # actually moves them, per spec.
    world = scene.rigidbody_world
    if world is not None and world.collection is not None:
        fragments_coll = bpy.data.collections.get(f"CrashForge_Fragments_{target_name}")
        if fragments_coll is not None:
            for frag in fragments_coll.objects:
                if frag.name not in world.collection.objects:
                    world.collection.objects.link(frag)


# --- Step 9: Dust ----------------------------------------------------------------

def _add_dust(context, scene):
    if not scene.crashforge.impact_frame:
        return

    cell_fracture_ok, _ = env_check.check_cell_fracture()  # noqa: F841 (dust doesn't need this; kept for symmetry)
    mantaflow_ok, mantaflow_msg = env_check.check_mantaflow()
    if not mantaflow_ok:
        raise RuntimeError(mantaflow_msg)

    bpy.ops.mesh.primitive_ico_sphere_add(radius=0.25, location=scene.crashforge.impact_location)
    flow_obj = context.active_object
    flow_obj.name = "CrashForgeDustFlow"
    _mark_generated(flow_obj)

    bpy.ops.object.quick_smoke(style='SMOKE')

    domain = None
    for obj in context.selected_objects:
        if obj is not flow_obj and any(m.type == 'FLUID' for m in obj.modifiers):
            domain = obj
            break
    if domain is None:
        raise RuntimeError("quick_smoke did not produce a domain object as expected.")

    domain.name = "CrashForgeDustDomain"
    _mark_generated(domain)

    domain_settings = next(m for m in domain.modifiers if m.type == 'FLUID').domain_settings
    if hasattr(domain_settings, "use_adaptive_domain"):
        domain_settings.use_adaptive_domain = True
    if hasattr(domain_settings, "resolution_max"):
        domain_settings.resolution_max = DUST_RESOLUTION_MAX
    if hasattr(domain_settings, "use_noise"):
        domain_settings.use_noise = True
    if hasattr(domain_settings, "noise_pos_scale"):
        domain_settings.noise_pos_scale = DUST_NOISE_POS_SCALE

    flow_settings = next(m for m in flow_obj.modifiers if m.type == 'FLUID').flow_settings
    if hasattr(flow_settings, "density"):
        speed = scene.crashforge.impact_speed
        flow_settings.density = max(0.1, min(1.0, speed / 20.0))


# --- Master pipeline -----------------------------------------------------------

class CRASHFORGE_OT_build_rig(Operator):
    bl_idname = "crashforge.build_rig"
    bl_label = "Build Rig"
    bl_description = "Run the full Rig pipeline: World, Mass, Deform, Crumple-then-Shatter, Fracture, Detach, Passive, Impact Target, Dust"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        mesh_objects = [obj for obj in scene.objects if obj.type == 'MESH']
        warnings = []

        try:
            _configure_world(context, scene)
        except Exception as exc:
            self.report({'ERROR'}, f"Crash Forge: World setup failed: {exc}")
            return {'CANCELLED'}

        for obj in mesh_objects:
            if obj.crashforge.role in {'RIGID', 'DEFORM', 'DETACH'}:
                _ensure_rigid_body(context, obj, 'ACTIVE')

        _configure_mass(context, mesh_objects)

        deform_objects = [obj for obj in mesh_objects if obj.crashforge.role == 'DEFORM']

        # Colliders must exist before the cloth bake in Crumple-then-Shatter,
        # or the peak-crush scan measures a panel falling through the divider.
        try:
            collider_count = _setup_cloth_colliders(scene, deform_objects)
            if deform_objects and collider_count == 0:
                warnings.append("No collider surfaces found for DEFORM parts — crumple will not hit anything.")
        except Exception as exc:
            warnings.append(f"Cloth collider setup failed: {exc}")

        for obj in list(deform_objects):
            _apply_deform(obj, scene.crashforge.crumple_intensity)
            if obj.crashforge.crumple_then_shatter:
                try:
                    _apply_crumple_then_shatter(context, obj, scene)
                except Exception as exc:
                    warnings.append(f"Crumple-then-Shatter failed on '{obj.name}': {exc}")

        cell_fracture_ok, cell_fracture_msg = env_check.check_cell_fracture()
        fracture_targets = [obj for obj in mesh_objects if obj.crashforge.role == 'FRACTURE' and obj.name in scene.objects]
        if fracture_targets and not cell_fracture_ok:
            warnings.append(f"Skipped Fracture: {cell_fracture_msg}")
        elif fracture_targets:
            for obj in fracture_targets:
                try:
                    _apply_fracture(context, obj, scene, scene.crashforge.fracture_outer_multiplier)
                except Exception as exc:
                    warnings.append(f"Fracture failed on '{obj.name}': {exc}")

        for obj in mesh_objects:
            if obj.crashforge.role == 'DETACH' and obj.name in scene.objects:
                try:
                    _apply_detach(context, obj, scene)
                except Exception as exc:
                    warnings.append(f"Detach failed on '{obj.name}': {exc}")

        remaining = [obj for obj in scene.objects if obj.type == 'MESH']
        _apply_passive_and_driven(context, scene, remaining)

        if scene.crashforge.impact_target is not None:
            if not cell_fracture_ok:
                warnings.append(f"Skipped Impact Target fracture: {cell_fracture_msg}")
            else:
                try:
                    _apply_impact_target(context, scene, scene.crashforge.fracture_outer_multiplier)
                except Exception as exc:
                    warnings.append(f"Impact Target setup failed: {exc}")

        try:
            _add_dust(context, scene)
        except Exception as exc:
            warnings.append(f"Dust setup skipped: {exc}")

        if warnings:
            self.report({'WARNING'}, "Crash Forge: build_rig finished with warnings — " + " | ".join(warnings))
        else:
            self.report({'INFO'}, "Crash Forge: build_rig finished.")
        return {'FINISHED'}


class CRASHFORGE_OT_pick_fracture_origin(Operator):
    bl_idname = "crashforge.pick_fracture_origin"
    bl_label = "Pick Fracture Origin"
    bl_description = "Click a point on the active object to set its fracture origin"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'

    def invoke(self, context, event):
        if context.space_data is None or context.space_data.type != 'VIEW_3D':
            self.report({'ERROR'}, "Crash Forge: run this from the 3D Viewport.")
            return {'CANCELLED'}
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            region = context.region
            rv3d = context.region_data
            coord = (event.mouse_region_x, event.mouse_region_y)
            ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)
            ray_direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)

            depsgraph = context.evaluated_depsgraph_get()
            success, location, _normal, _index, _obj, _matrix = context.scene.ray_cast(
                depsgraph, ray_origin, ray_direction
            )
            if success:
                obj = context.active_object
                obj.crashforge.fracture_origin = obj.matrix_world.inverted() @ location
                self.report({'INFO'}, f"Crash Forge: fracture origin set on '{obj.name}'.")
                return {'FINISHED'}
            self.report({'WARNING'}, "Crash Forge: no surface under the click.")
            return {'RUNNING_MODAL'}

        if event.type in {'RIGHTMOUSE', 'ESC'}:
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}


class CRASHFORGE_OT_rebuild_from_tags(Operator):
    bl_idname = "crashforge.rebuild_from_tags"
    bl_label = "Rebuild from Tags"
    bl_description = "Delete every Crash Forge generated object/modifier that isn't baked-locked, then re-run Build Rig"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene

        for obj in list(scene.objects):
            if obj.type != 'MESH':
                continue
            if obj.crashforge.crashforge_generated and not obj.crashforge.baked_locked:
                bpy.data.objects.remove(obj, do_unlink=True)
                continue
            for mod in list(obj.modifiers):
                if mod.get("crashforge_generated") and not obj.crashforge.baked_locked:
                    obj.modifiers.remove(mod)

        for obj in list(scene.objects):
            if obj.crashforge.crashforge_generated and not obj.crashforge.baked_locked and obj.type != 'MESH':
                bpy.data.objects.remove(obj, do_unlink=True)

        bpy.ops.crashforge.build_rig()
        return {'FINISHED'}


classes = (
    CRASHFORGE_OT_build_rig,
    CRASHFORGE_OT_pick_fracture_origin,
    CRASHFORGE_OT_rebuild_from_tags,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
