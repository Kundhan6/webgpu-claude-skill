"""bl/rig.py — core/rig.py's RigPlan -> real bpy state (§5, §8.2). Thin
bpy layer: every decision (which parts get a rigid body, what mass, which
wheel a caliper parents to, ...) was already made by
core.rig.build_rig_plan; this module only makes the mechanical bpy calls
to carry it out.
"""
import math

import bpy

from . import scene as bl_scene
from ..core.naming import CF_GENERATED_KEY, CF_STAGE_KEY, CF_UID_KEY, RBW_COLLECTION_NAME, RBWC_COLLECTION_NAME, new_cf_uid

RIG_STAGE = 2  # §7.1: obj["cf_stage"] = <int> — Rig is stage 2


def _tag_generated(obj) -> None:
    obj[CF_GENERATED_KEY] = True
    obj[CF_STAGE_KEY] = RIG_STAGE
    obj[CF_UID_KEY] = new_cf_uid()


def _run_as_active(context, obj, callback):
    """Make `obj` the real active/selected object (not just a
    temp_override target — confirmed necessary for operator .poll() on a
    real car, see bl/apply.py's _select_only), run `callback`, then
    restore whatever selection was active before. Shared by every
    bpy.ops.rigidbody.*_add call below, all of which need exactly this."""
    view_layer = context.view_layer
    prev_active = view_layer.objects.active
    prev_selected = [o for o in view_layer.objects if o.select_get()]
    for o in view_layer.objects:
        o.select_set(False)
    obj.select_set(True)
    view_layer.objects.active = obj
    try:
        with context.temp_override(object=obj, active_object=obj, selected_objects=[obj]):
            callback()
    finally:
        for o in view_layer.objects:
            o.select_set(o in prev_selected)
        view_layer.objects.active = prev_active


def add_rigid_body(context, obj, body_type: str, collision_shape: str, mass: float) -> None:
    """§8.2 steps 1–2. bpy.ops.rigidbody.object_add has no data-API
    equivalent (creating obj.rigid_body itself requires the operator;
    every property on it once created is a plain data-API assignment,
    §3 rule 6). Stage 0 probe confirmed this operator's poll() only
    passes MESH on this build — every object this is called on must
    already be a mesh (§1.1)."""
    _run_as_active(context, obj, lambda: bpy.ops.rigidbody.object_add())
    obj.rigid_body.type = body_type
    obj.rigid_body.collision_shape = collision_shape
    obj.rigid_body.mass = mass


def add_collision_modifier(obj) -> None:
    """§9.5: the barrier needs a Collision modifier *and* a passive rigid
    body — "the soft body solver cannot see rigid bodies" on its own."""
    if obj.modifiers.get("CF_Collision") is None:
        mod = obj.modifiers.new("CF_Collision", 'COLLISION')
        mod.settings.damping = 0.1
        mod.settings.thickness_outer = 0.02
        mod.settings.friction = 0.0


def _create_constraint_empty(context, name: str, location, axis: int):
    """One CF_ Empty per constraint (§7.1). HINGE/MOTOR constraints
    rotate around the empty's local Z by default — axis 2 (Z) needs no
    rotation; axis 0/1 (X/Y) are aligned by rotating the empty so its
    local Z points along that world axis. Not independently probed (§6's
    table covers that HINGE/MOTOR/FIXED exist as constraint types, not
    constraint-empty orientation) — standard, long-stable Blender
    behaviour; confirm on the real run. A wrong sign here shows up as a
    wheel wobbling sideways instead of rolling forward — visibly wrong,
    not a silent failure.
    """
    empty = bpy.data.objects.new(name, None)
    empty.location = location
    if axis == 0:
        empty.rotation_euler = (0.0, math.radians(90.0), 0.0)
    elif axis == 1:
        empty.rotation_euler = (math.radians(-90.0), 0.0, 0.0)
    context.scene.collection.objects.link(empty)
    _tag_generated(empty)
    return empty


def _add_constraint(context, empty, constraint_type: str, obj1, obj2, disable_collisions: bool):
    _run_as_active(context, empty, lambda: bpy.ops.rigidbody.constraint_add(type=constraint_type))
    rbc = empty.rigid_body_constraint
    rbc.object1 = obj1
    rbc.object2 = obj2
    rbc.disable_collisions = disable_collisions
    return rbc


def add_hinge(context, spec, objects_by_name):
    """§9.1."""
    empty = _create_constraint_empty(context, spec.name, spec.pivot, spec.axis)
    _add_constraint(context, empty, 'HINGE', objects_by_name[spec.chassis], objects_by_name[spec.wheel], True)
    return empty


def add_motor(context, spec, objects_by_name):
    """§9.2. Target velocity is left at 0.0 — deriving it from speed_kmh
    and wheel radius is §8.4 CF_Drive's job (not built this session);
    0.0 is the physically correct value for a car at rest, which is
    exactly what M5's 3-frame explosion test needs."""
    empty = _create_constraint_empty(context, spec.name, spec.pivot, spec.axis)
    rbc = _add_constraint(context, empty, 'MOTOR', objects_by_name[spec.chassis], objects_by_name[spec.wheel], True)
    rbc.use_motor_ang = True
    rbc.motor_ang_target_velocity = 0.0
    return empty


def add_break(context, spec, objects_by_name):
    """§9.3, plus glass's non-breaking variant (core/rig.py::BreakSpec's
    docstring — glass needs the same FIXED chassis<->panel attachment to
    stay structurally connected, just never allowed to break through it).
    `use_breaking` stays at its RNA default (False) whenever
    `spec.breakable` is False -- never set True and then left with a
    meaningless `breaking_threshold=0.0`, which would make glass panels
    detach on the very first frame of any nonzero impulse."""
    location = tuple(objects_by_name[spec.panel].matrix_world.translation)
    empty = _create_constraint_empty(context, spec.name, location, 2)
    rbc = _add_constraint(context, empty, 'FIXED', objects_by_name[spec.chassis], objects_by_name[spec.panel], True)
    if spec.breakable:
        rbc.use_breaking = True
        rbc.breaking_threshold = spec.breaking_threshold
    return empty


def add_nocol(context, spec, objects_by_name):
    """§9.4 — the constraint v1 was missing. `enabled=False`: it must
    hold nothing, `disable_collisions=True` is its entire purpose."""
    a_loc = objects_by_name[spec.a].matrix_world.translation
    b_loc = objects_by_name[spec.b].matrix_world.translation
    midpoint = tuple((a_loc[i] + b_loc[i]) / 2.0 for i in range(3))
    empty = _create_constraint_empty(context, spec.name, midpoint, 2)
    rbc = _add_constraint(context, empty, 'FIXED', objects_by_name[spec.a], objects_by_name[spec.b], True)
    rbc.enabled = False
    return empty


def parent_to(obj, parent_obj) -> None:
    """M5 rigging requirement / §12.1 step 4: object-level parenting, not
    a rigid body FIXED constraint — keeps a part rigidly "welded" to its
    parent's motion without adding to the rigid body budget (§3 rule 7)
    or the no-collide pair count. matrix_parent_inverse keeps the part
    from jumping to a new world position on reparenting (standard
    Blender parenting behaviour)."""
    obj.parent = parent_obj
    obj.matrix_parent_inverse = parent_obj.matrix_world.inverted()


def _ensure_named_world_collections(scene) -> None:
    """§7.1: CF_RBW / CF_RBWC are fixed names for the rigidbody world's
    collection/constraints. bpy.ops.rigidbody.object_add() auto-creates
    scene.rigidbody_world (and its two collections, under Blender's own
    default names) the first time it succeeds on an object with none yet
    — renamed here to match the spec's naming table. Purely cosmetic:
    bl/scene.py's Reset helpers already operate on rbw.collection/
    .constraints structurally, never by name, so this isn't required for
    correctness."""
    world = getattr(scene, "rigidbody_world", None)
    if world is None:
        return
    if world.collection is not None:
        world.collection.name = RBW_COLLECTION_NAME
    if world.constraints is not None:
        world.constraints.name = RBWC_COLLECTION_NAME


def apply_rig_plan(context, plan, objects_by_name) -> list:
    """Walk core.rig.RigPlan and build the real rig. Returns every object
    this created (constraint empties) — rigid bodies are added to
    *existing* car parts, not new objects, so they don't need separate
    tracking here (cf_generated is never stamped on an original car
    part; Reset's touched_car_parts() path already handles those via
    cf_role/cf_* props, same as Prep)."""
    for rb in plan.rigid_bodies:
        obj = objects_by_name[rb.part_name]
        add_rigid_body(context, obj, rb.body_type, rb.collision_shape, rb.mass)
        if rb.body_type == "PASSIVE":
            add_collision_modifier(obj)

    _ensure_named_world_collections(context.scene)

    world = context.scene.rigidbody_world
    if world is not None:
        # §8.2 step 4: substeps >= 60, solver_iterations >= 20 — Blender
        # exposes no CCD, substeps are the only defence against tunneling.
        world.substeps_per_frame = max(world.substeps_per_frame, 60)
        world.solver_iterations = max(world.solver_iterations, 20)

    created = []
    for spec in plan.hinges:
        created.append(add_hinge(context, spec, objects_by_name))
    for spec in plan.motors:
        created.append(add_motor(context, spec, objects_by_name))
    for spec in plan.breaks:
        created.append(add_break(context, spec, objects_by_name))
    for spec in plan.nocols:
        created.append(add_nocol(context, spec, objects_by_name))

    for name in plan.weld_to_chassis:
        parent_to(objects_by_name[name], objects_by_name[plan.chassis])
    for name, wheel_name in plan.wheel_hardware_parent.items():
        parent_to(objects_by_name[name], objects_by_name[wheel_name])

    return created


def zero_gravity(scene) -> tuple:
    """§8.2 step 5, tightened per reviewer correction: Stage 2 has no
    ground plane yet, so with real gravity on, the whole (ungrounded)
    car free-falls during the rest test and contaminates the signal the
    check exists to isolate — constraint/collision behaviour, not "did
    the car fall". Returns the previous `scene.gravity` so the caller
    can restore it afterward."""
    prev = tuple(scene.gravity)
    scene.gravity = (0.0, 0.0, 0.0)
    return prev


def prepare_for_rest_test(context) -> tuple:
    """Zero gravity, free any stale point cache, and reset to
    frame_start — all three, every time, before a rest test steps a
    single frame. A stale bake (this scene's own earlier Rig attempt, or
    a leftover cache from outside Crash Forge entirely) would replay old
    keyframed motion instead of actually re-simulating anything, giving
    a false pass regardless of what the constraint graph does. Returns
    the previous gravity vector for restore_after_rest_test()."""
    scene = context.scene
    prev_gravity = zero_gravity(scene)
    bl_scene.free_all_point_caches(context)
    scene.frame_set(scene.frame_start)
    return prev_gravity


def restore_after_rest_test(scene, prev_gravity) -> None:
    scene.gravity = prev_gravity


def gather_positions(objects_by_name: dict) -> dict:
    """World-space translation of every object, keyed by name — the
    before/after samples core.rig.check_explosion() compares (§8.2
    step 5)."""
    return {name: tuple(obj.matrix_world.translation) for name, obj in objects_by_name.items()}


def step_frames(context, count: int) -> None:
    """§8.2 step 5: "step the scene 3 frames" — advances the live
    (unbaked) rigid body simulation by re-evaluating the depsgraph at
    each new frame. Not independently probed (frame_set is core scene
    API, not one of §6's table rows); confirm the sim actually advances
    on the real run, same caveat as every other bl/ behaviour Tier B
    can't reach."""
    scene = context.scene
    for _ in range(count):
        scene.frame_set(scene.frame_current + 1)
