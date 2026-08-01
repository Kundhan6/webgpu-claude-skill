"""bl/probe.py — Stage 0 API probe (§6). Runs at add-on registration and
again at the start of the one-button pipeline (once that exists).

Every entry in §6's table gets checked here against the *running* build's
bl_rna, never assumed. Any failed entry should let the affected stage
disable itself with a readable message rather than fail mid-run — this
module only reports; deciding what to do about a failure is the calling
stage's job.

This module makes real bpy/bl_rna calls, so it is only meaningfully
exercised under real Blender (Tier C). Under the Tier B stub — which
deliberately implements no operators or RNA types at all — every check
reports "missing". That is the correct, honest behaviour of a stub with
no real API surface to probe, not a bug in this module.
"""
import bpy

from ..core.report import StageResult

SOFTBODY_NUMERIC_PROPS = (
    "goal_default", "goal_min", "goal_max", "goal_spring", "goal_friction",
    "plastic", "bend", "pull", "push", "damping", "mass",
)
SOFTBODY_BOOL_PROPS = ("use_goal", "use_edges")
SOFTBODY_OTHER_PROPS = ("vertex_group_goal",)

RIGIDBODY_CONSTRAINT_PROPS = (
    "use_breaking", "breaking_threshold", "disable_collisions",
    "enabled", "object1", "object2",
)

RIGIDBODY_WORLD_PROPS = (
    "collection", "constraints", "point_cache",
    "substeps_per_frame", "solver_iterations",
)


# --- bl_rna introspection helpers ---------------------------------------

def _rna_props(bl_type):
    rna = getattr(bl_type, "bl_rna", None)
    return rna.properties if rna is not None else None


def _has_prop(bl_type, name) -> bool:
    props = _rna_props(bl_type)
    return props is not None and name in props


def _enum_ids(bl_type, prop_name):
    props = _rna_props(bl_type)
    if props is None or prop_name not in props:
        return None
    items = getattr(props[prop_name], "enum_items", None)
    if items is None:
        return None
    return {item.identifier for item in items}


def _hard_range(bl_type, prop_name):
    props = _rna_props(bl_type)
    if props is None or prop_name not in props:
        return None
    prop = props[prop_name]
    lo = getattr(prop, "hard_min", None)
    hi = getattr(prop, "hard_max", None)
    if lo is None and hi is None:
        return None
    return (lo, hi)


def _op_exists(dotted_path):
    node = bpy.ops
    for part in dotted_path.split("."):
        node = getattr(node, part, None)
        if node is None:
            return None
    return node


def _op_param_names(op):
    try:
        rna_type = op.get_rna_type()
    except Exception:
        return None
    return {p.identifier for p in rna_type.properties if not p.is_readonly}


# --- individual probes ---------------------------------------------------

def _probe_rigidbody_object_add_poll(result: StageResult) -> None:
    """§6: which object types pass rigidbody.object_add.poll — MESH, EMPTY,
    CURVE. This is the exact check that would have caught v1's failure #1
    (an Empty rejected by the rigid body operator) before it ever ran."""
    scene = bpy.context.scene
    if scene is None:
        result.warn("rigidbody.object_add poll-by-type: no active scene, skipped")
        return

    mesh_data = bpy.data.meshes.new("CF_probe_tmp_mesh")
    curve_data = bpy.data.curves.new("CF_probe_tmp_curve_data", type='CURVE')
    type_makers = {
        "MESH": lambda: bpy.data.objects.new("CF_probe_tmp_mesh_obj", mesh_data),
        "EMPTY": lambda: bpy.data.objects.new("CF_probe_tmp_empty", None),
        "CURVE": lambda: bpy.data.objects.new("CF_probe_tmp_curve", curve_data),
    }

    poll_by_type = {}
    created = []
    try:
        for obj_type, make in type_makers.items():
            obj = make()
            scene.collection.objects.link(obj)
            created.append(obj)
            prev_active = bpy.context.view_layer.objects.active
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            try:
                poll_by_type[obj_type] = bool(bpy.ops.rigidbody.object_add.poll())
            except Exception as exc:
                poll_by_type[obj_type] = False
                result.warn(f"rigidbody.object_add.poll() raised for {obj_type}: {exc}")
            obj.select_set(False)
            bpy.context.view_layer.objects.active = prev_active
    finally:
        for obj in created:
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.meshes.remove(mesh_data)
        bpy.data.curves.remove(curve_data)

    result.data["rigidbody_object_add_poll_by_type"] = poll_by_type
    result.info(f"rigidbody.object_add poll by type: {poll_by_type}")


def _probe_mesh_attributes(result: StageResult) -> None:
    """§6: sharp_face / custom_normal present/removable."""
    mesh = None
    try:
        mesh = bpy.data.meshes.new("CF_probe_tmp_attr_mesh")
        mesh.from_pydata(
            [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)],
            [],
            [(0, 1, 2, 3)],
        )
        mesh.update()
        attrs = {}
        for attr_name in ("sharp_face", "custom_normal"):
            attrs[attr_name] = mesh.attributes.get(attr_name) is not None
        result.data["mesh_attributes_on_fresh_mesh"] = attrs
    except Exception as exc:
        result.warn(f"mesh attribute probe failed: {exc}")
    finally:
        if mesh is not None:
            bpy.data.meshes.remove(mesh)


def run_probe() -> StageResult:
    result = StageResult()

    # bpy.ops.rigidbody.object_add — §1.1's failure, probed directly.
    if _op_exists("rigidbody.object_add") is None:
        result.error("bpy.ops.rigidbody.object_add: MISSING")
    else:
        result.data["operators.rigidbody.object_add"] = True
        _probe_rigidbody_object_add_poll(result)

    if _op_exists("rigidbody.constraint_add") is None:
        result.error("bpy.ops.rigidbody.constraint_add: MISSING")
    else:
        result.data["operators.rigidbody.constraint_add"] = True

    # RigidBodyConstraint
    rbc_type = getattr(bpy.types, "RigidBodyConstraint", None)
    if rbc_type is None:
        result.error("bpy.types.RigidBodyConstraint: MISSING")
    else:
        enum_ids = _enum_ids(rbc_type, "type") or set()
        missing = {"FIXED", "HINGE", "MOTOR", "GENERIC"} - enum_ids
        if missing:
            result.error(f"RigidBodyConstraint.type missing enum values: {sorted(missing)}")
        else:
            result.data["rigidbody_constraint_type_enum"] = sorted(enum_ids)

        for prop_name in RIGIDBODY_CONSTRAINT_PROPS:
            if not _has_prop(rbc_type, prop_name):
                result.error(f"RigidBodyConstraint.{prop_name}: MISSING")

        props = _rna_props(rbc_type) or {}
        motor_props = sorted(p.identifier for p in props.values() if "motor" in p.identifier)
        if not motor_props:
            result.error(
                "RigidBodyConstraint: no motor-related properties found at all "
                "(expected something like use_motor_ang, motor_ang_target_velocity, motor_ang_max_impulse)"
            )
        else:
            result.data["rigidbody_constraint_motor_props"] = motor_props
            for expected in ("use_motor_ang", "motor_ang_target_velocity", "motor_ang_max_impulse"):
                if expected not in motor_props:
                    result.warn(
                        f"RigidBodyConstraint: expected motor prop {expected!r} not found; "
                        f"actual motor props are {motor_props}"
                    )

    # RigidBodyObject.collision_shape
    rbo_type = getattr(bpy.types, "RigidBodyObject", None)
    if rbo_type is None:
        result.error("bpy.types.RigidBodyObject: MISSING")
    else:
        enum_ids = _enum_ids(rbo_type, "collision_shape") or set()
        missing = {"COMPOUND", "CONVEX_HULL", "MESH"} - enum_ids
        if missing:
            result.error(f"RigidBodyObject.collision_shape missing enum values: {sorted(missing)}")
        else:
            result.data["rigidbody_object_collision_shape_enum"] = sorted(enum_ids)

    # scene.rigidbody_world
    rbw_type = getattr(bpy.types, "RigidBodyWorld", None)
    if rbw_type is None:
        result.error("bpy.types.RigidBodyWorld: MISSING")
    else:
        for prop_name in RIGIDBODY_WORLD_PROPS:
            if not _has_prop(rbw_type, prop_name):
                result.error(f"RigidBodyWorld.{prop_name}: MISSING")

    # SoftBodySettings — record every hard_min/hard_max per §6.
    sb_type = getattr(bpy.types, "SoftBodySettings", None)
    if sb_type is None:
        result.error("bpy.types.SoftBodySettings: MISSING")
    else:
        ranges = {}
        for prop_name in SOFTBODY_NUMERIC_PROPS:
            if not _has_prop(sb_type, prop_name):
                result.error(f"SoftBodySettings.{prop_name}: MISSING")
                continue
            rng = _hard_range(sb_type, prop_name)
            ranges[prop_name] = rng
            if rng is None:
                result.warn(f"SoftBodySettings.{prop_name}: exists but has no hard_min/hard_max")
        for prop_name in SOFTBODY_BOOL_PROPS + SOFTBODY_OTHER_PROPS:
            if not _has_prop(sb_type, prop_name):
                result.error(f"SoftBodySettings.{prop_name}: MISSING")
        result.data["softbody_ranges"] = ranges

    # Surface Deform
    op = _op_exists("object.surfacedeform_bind")
    if op is None:
        result.error("bpy.ops.object.surfacedeform_bind: MISSING")
    else:
        params = _op_param_names(op)
        if params is not None and "modifier" not in params:
            result.error(f"object.surfacedeform_bind: 'modifier' param not found, actual params: {sorted(params)}")
        else:
            result.data["surfacedeform_bind_params"] = sorted(params) if params else []

    sdm_type = getattr(bpy.types, "SurfaceDeformModifier", None)
    if sdm_type is None:
        result.error("bpy.types.SurfaceDeformModifier: MISSING")
    else:
        for prop_name in ("target", "is_bound"):
            if not _has_prop(sdm_type, prop_name):
                result.error(f"SurfaceDeformModifier.{prop_name}: MISSING")

    # Remesh
    remesh_type = getattr(bpy.types, "RemeshModifier", None)
    if remesh_type is None:
        result.error("bpy.types.RemeshModifier: MISSING")
    else:
        enum_ids = _enum_ids(remesh_type, "mode") or set()
        if "VOXEL" not in enum_ids:
            result.error(f"RemeshModifier.mode missing VOXEL, got {sorted(enum_ids)}")
        if not _has_prop(remesh_type, "voxel_size"):
            result.error("RemeshModifier.voxel_size: MISSING")

    # shade_auto_smooth — §4/§15: what it adds can only be confirmed live.
    if _op_exists("object.shade_auto_smooth") is None:
        result.error("bpy.ops.object.shade_auto_smooth: MISSING")
    else:
        result.data["operators.object.shade_auto_smooth"] = True
        result.info(
            "bpy.ops.object.shade_auto_smooth is present; which modifier it adds and its "
            "index in the stack must be confirmed live (Tier C) before Bind (§8.7/V16) relies on it"
        )

    # nla.bake
    op = _op_exists("nla.bake")
    if op is None:
        result.error("bpy.ops.nla.bake: MISSING")
    else:
        params = _op_param_names(op)
        required = {"bake_types", "visual_keying", "clear_constraints"}
        missing = required - (params or set())
        if missing:
            result.error(f"nla.bake missing expected params: {sorted(missing)}, actual: {sorted(params) if params else []}")
        else:
            result.data["nla_bake_params"] = sorted(params)

    # quick_explode
    op = _op_exists("object.quick_explode")
    if op is None:
        result.error("bpy.ops.object.quick_explode: MISSING")
    else:
        params = _op_param_names(op)
        result.data["quick_explode_params"] = sorted(params) if params else []

    # ptcache
    for name in ("ptcache.bake", "ptcache.free_bake_all"):
        if _op_exists(name) is None:
            result.error(f"bpy.ops.{name}: MISSING")
        else:
            result.data[f"operators.{name}"] = True

    # mesh attributes
    _probe_mesh_attributes(result)

    return result


def format_report(result: StageResult) -> str:
    lines = ["=== Crash Forge — Stage 0 API Probe ===", ""]
    version = getattr(getattr(bpy, "app", None), "version_string", "unknown")
    lines.append(f"Blender: {version}")
    lines.append(f"OK: {result.ok}")
    lines.append("")
    if result.errors:
        lines.append(f"-- {len(result.errors)} ERROR(S) --")
        lines += [str(e) for e in result.errors]
        lines.append("")
    if result.warnings:
        lines.append(f"-- {len(result.warnings)} WARNING/INFO --")
        lines += [str(w) for w in result.warnings]
        lines.append("")
    if result.data:
        lines.append("-- Data --")
        for key, value in result.data.items():
            lines.append(f"{key}: {value}")
    return "\n".join(lines)
