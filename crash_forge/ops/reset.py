"""crashforge.reset — CF_Reset (§8.0). Built first, before any stage that
creates state, or every retest is contaminated (§1.3, §3 rule 5) exactly
the way it was in v1.
"""
import bpy

from ..bl import probe as bl_probe
from ..bl import scene as bl_scene

_BLENDER_REPORT_LEVELS = {'INFO', 'WARNING', 'ERROR'}


def _relay(operator, result):
    """Surface every Notice a StageResult collected via self.report(), so a
    partial restore (or any other stage outcome) is visible in the UI/log
    instead of only living in a return value nobody reads (§1.3)."""
    for notice in (*result.errors, *result.warnings):
        level = notice.severity.value if notice.severity.value in _BLENDER_REPORT_LEVELS else 'ERROR'
        operator.report({level}, notice.message)


class CF_OT_reset(bpy.types.Operator):
    bl_idname = "crashforge.reset"
    bl_label = "Crash Forge: Reset"
    bl_description = "Fully undo everything Crash Forge has created in this scene"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene

        # Stage 0 probe, run lazily here (not at registration — see
        # bl/probe.py's module docstring for why) and never swallowed:
        # an unexpected exception is a genuine failure, reported and
        # cancelled, not printed-and-continued; a structured failure
        # (probe_result.ok == False) refuses to run at all rather than
        # proceeding on unverified API assumptions (§3 rule 1).
        try:
            probe_result = bl_probe.ensure_probed()
        except Exception as exc:
            self.report({'ERROR'}, f"CF_Reset: Stage 0 probe failed unexpectedly: {exc}")
            return {'CANCELLED'}
        bl_probe.write_probe_report(scene, probe_result)
        if not probe_result.ok:
            for notice in probe_result.errors:
                self.report({'ERROR'}, str(notice))
            self.report(
                {'ERROR'},
                "CF_Reset: Stage 0 probe reported failures — refusing to run on unverified API assumptions",
            )
            return {'CANCELLED'}

        # 1. Free all point caches.
        if not bl_scene.free_all_point_caches(context):
            self.report({'WARNING'}, "ptcache.free_bake_all did not report FINISHED — some baked caches may remain")

        # 2. Remove every cf_generated object: rigidbody world, then scene, then data.
        bl_scene.remove_cf_generated_objects(context)

        # 3. Purge orphaned constraint empties.
        bl_scene.purge_orphaned_constraint_empties(context)

        # 4. Undo Crash Forge's marks on every original car part it touched.
        for obj in bl_scene.touched_car_parts(scene):
            bl_scene.clean_original_part(context, obj)

        # 5. Restore transforms/parenting from the original_state snapshot.
        # Never silent: every record is either restored or named as missing.
        restore_result = bl_scene.restore_original_state(scene)
        _relay(self, restore_result)

        # Self-check (§8.0): assert both post-conditions before declaring success.
        problems = bl_scene.reset_self_check(scene)
        if problems:
            for p in problems:
                self.report({'ERROR'}, p)
            return {'CANCELLED'}

        # 6. Reset stage_completed = 0.
        scene.crash_forge.stage_completed = 0
        self.report({'INFO'}, "Crash Forge: scene reset")
        return {'FINISHED'}


CLASSES = (CF_OT_reset,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
