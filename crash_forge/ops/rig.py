"""crashforge.rig — CF_Rig (§8.2, M5). Builds the full constraint graph
(§9) from parts CF_Prep already classified, then runs the 3-frame
explosion test (§8.2 step 5 / V8) before declaring success — a rig that
explodes at rest is exactly v1's failure #2 (§1.2: "the constraint solver
and the collision solver fought on frame 1 and the car detonated"), and
this is the automated check that would have caught it.

This embedded check is a cheap, best-effort pipeline gate — it uses
`bl_rig.prepare_for_rest_test()` (zero gravity, free the point cache,
reset to frame_start) so it isn't fooled by Stage 2's missing ground
plane or a stale bake, but it prints no table and only asserts at 3
frames. `tests/blender/test_rig_at_rest.py` is the deliberate, more
rigorous, committed re-check for a manual Blender run: the same 3-frame
assert plus a 30-frame drift report, with a full per-part table. Run
that whenever this operator's own pass/fail needs a second look.
"""
import bpy

from ..bl import extract as bl_extract
from ..bl import probe as bl_probe
from ..bl import rig as bl_rig
from ..bl import scene as bl_scene
from ..core import rig as core_rig
from ..core.classify import PartRole

_EXPLOSION_STEP_FRAMES = 3


def _cleanup_failed_rig(context) -> None:
    """§3 rule 10: a stage that can't guarantee a correct result never
    leaves a half-built rig behind. Reuses CF_Reset's own teardown
    helpers (bl/scene.py) rather than inventing a second cleanup path —
    every object this stage creates is cf_generated, exactly what those
    helpers already know how to remove. Original car parts that got
    parented (weld_to_chassis / wheel hardware) are left as-is: clearing
    a `.parent` isn't part of what "half-built rig" means here, and
    CF_Reset already restores parenting from original_state on a full
    Reset regardless."""
    bl_scene.remove_cf_generated_objects(context)
    bl_scene.purge_orphaned_constraint_empties(context)


class CF_OT_rig(bpy.types.Operator):
    bl_idname = "crashforge.rig"
    bl_label = "Crash Forge: Rig"
    bl_description = "Build the rigid body constraint graph and verify the car doesn't explode at rest"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        """`stage_completed == 1` exactly, not `>= 1`: Rig is the first
        stage that creates brand-new objects (constraint empties), and
        this operator does not yet clean up a *previous* Rig run's own
        artifacts before building a new one (§3 rule 4's idempotency is
        not fully guaranteed here — see CLAUDE.md's M5 section). Gating
        on `== 1` blocks the most common accident (clicking Rig twice in
        a row) by requiring Reset (which sets stage_completed back to 0)
        in between. It does not close every path — re-running Prep after
        Rig also resets stage_completed to 1 without cleaning up Rig's
        prior artifacts, since Prep has no reason today to know Rig
        exists — flagged, not fixed, this session."""
        cf = getattr(context.scene, "crash_forge", None)
        return cf is not None and cf.car_object is not None and cf.stage_completed == 1

    def execute(self, context):
        scene = context.scene
        cf = scene.crash_forge
        car_object = cf.car_object

        # Stage 0 probe, run lazily here (not at registration — see
        # bl/probe.py's module docstring for why) and never swallowed:
        # an unexpected exception is a genuine failure, reported and
        # cancelled, not printed-and-continued; a structured failure
        # (probe_result.ok == False) refuses to run at all rather than
        # proceeding on unverified API assumptions (§3 rule 1) -- and
        # Rig in particular depends on the rigidbody/constraint/motor
        # surface this probe exists to confirm.
        try:
            probe_result = bl_probe.ensure_probed()
        except Exception as exc:
            self.report({'ERROR'}, f"CF_Rig: Stage 0 probe failed unexpectedly: {exc}")
            return {'CANCELLED'}
        bl_probe.write_probe_report(scene, probe_result)
        if not probe_result.ok:
            for notice in probe_result.errors:
                self.report({'ERROR'}, str(notice))
            self.report(
                {'ERROR'},
                "CF_Rig: Stage 0 probe reported failures — refusing to run on unverified API assumptions",
            )
            return {'CANCELLED'}

        parts = bl_extract.collect_car_parts(car_object)
        if not parts:
            self.report({'ERROR'}, "CF_Rig: no mesh objects found under the selected car object")
            return {'CANCELLED'}

        roles = {}
        for obj in parts:
            raw_role = obj.get("cf_role")
            if raw_role is None:
                self.report({'ERROR'}, f"CF_Rig: {obj.name!r} has no cf_role — run CF_Prep first")
                return {'CANCELLED'}
            try:
                roles[obj.name] = PartRole(raw_role)
            except ValueError:
                self.report({'ERROR'}, f"CF_Rig: {obj.name!r} has an unrecognised cf_role {raw_role!r}")
                return {'CANCELLED'}

        descriptors = bl_extract.extract_part_descriptors(parts)

        barrier_obj = cf.target_object
        barrier_name = barrier_obj.name if barrier_obj is not None else None
        if barrier_obj is not None:
            descriptors = list(descriptors) + [bl_extract.extract_part_descriptor(barrier_obj)]

        try:
            plan = core_rig.build_rig_plan(
                descriptors, roles,
                speed_kmh=cf.speed_kmh, panel_toughness=cf.panel_toughness,
                barrier_name=barrier_name,
            )
        except core_rig.RigPlanError as exc:
            self.report({'ERROR'}, f"CF_Rig: {exc}")
            return {'CANCELLED'}

        objects_by_name = {obj.name: obj for obj in parts}
        if barrier_obj is not None:
            objects_by_name[barrier_obj.name] = barrier_obj

        bl_rig.apply_rig_plan(context, plan, objects_by_name)

        # §8.2 step 5 / V8: step 3 frames with nothing driving the car,
        # measure the worst rigid part's displacement relative to the
        # chassis. Zero gravity first -- Stage 2 has no ground plane yet,
        # so real gravity free-falls the whole car and contaminates this
        # check with an unrelated, expected effect (reviewer correction:
        # this embedded gate had the exact same flaw the standalone
        # tests/blender/test_rig_at_rest.py script was written to avoid).
        # Frame position and gravity are both restored afterward either
        # way -- this check must not leave the user's timeline or scene
        # gravity mutated as a side effect.
        rigid_objects_by_name = {name: objects_by_name[name] for name in plan.rigid_part_names}
        original_frame = scene.frame_current
        prev_gravity = bl_rig.prepare_for_rest_test(context)
        try:
            before = bl_rig.gather_positions(rigid_objects_by_name)
            bl_rig.step_frames(context, _EXPLOSION_STEP_FRAMES)
            after = bl_rig.gather_positions(rigid_objects_by_name)
        finally:
            scene.frame_set(original_frame)
            bl_rig.restore_after_rest_test(scene, prev_gravity)

        check = core_rig.check_explosion(before, after, plan.chassis, plan.car_length)
        if not check.ok:
            self.report(
                {'ERROR'},
                f"CF_Rig: exploded on the {_EXPLOSION_STEP_FRAMES}-frame rest test — "
                f"{check.offending!r} moved {check.max_displacement:.4f} relative to the chassis "
                f"(threshold {check.threshold:.4f}, {core_rig.EXPLOSION_THRESHOLD_FRACTION:.0%} of car "
                f"length). Rig removed — check the no-collide pairs and collision shapes before re-running.",
            )
            _cleanup_failed_rig(context)
            return {'CANCELLED'}

        cf.stage_completed = 2
        breakable_count = sum(1 for b in plan.breaks if b.breakable)
        glass_attach_count = len(plan.breaks) - breakable_count
        parented_count = len(plan.weld_to_chassis) + len(plan.wheel_hardware_parent)
        self.report(
            {'INFO'},
            f"CF_Rig: {len(plan.rigid_bodies)} rigid part(s) SIMULATED, {parented_count} part(s) "
            f"PARENTED (not simulated), {len(plan.hinges)} hinge(s), {len(plan.motors)} motor(s), "
            f"{breakable_count} breakable panel(s), {glass_attach_count} glass attachment(s), "
            f"{len(plan.nocols)} no-collide pair(s), connectivity: 1 component — rest test passed "
            f"(worst displacement {check.max_displacement:.4f} / {check.threshold:.4f} threshold)",
        )
        return {'FINISHED'}


CLASSES = (CF_OT_rig,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
