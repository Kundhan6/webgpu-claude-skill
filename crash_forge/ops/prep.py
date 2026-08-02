"""crashforge.prep — CF_Prep (§8.1, M4). The one stage that needs user
input (the car object) rather than running unattended.

Order follows §8.1 exactly: snapshot before anything touches a part,
validate before extracting a classification anyone could act on, classify
before the destructive geometry cleanup, geometry cleanup before origin
placement (auto-smooth needs real, un-recentred geometry under it).
"""
import json
import os
import tempfile
from collections import Counter

import bpy

from ..bl import apply as bl_apply
from ..bl import extract as bl_extract
from ..bl import scene as bl_scene
from ..core import validate as core_validate
from ..core.classify import PartRole, classify, detect_forward_axis
from ..core.descriptor_io import dump_part_descriptors

_BLENDER_REPORT_LEVELS = {'INFO', 'WARNING', 'ERROR'}

# §8.1 step 8: "expose a dropdown override" for any part below this
# confidence. The dropdown UI itself is not built in this pass (M4 is
# scoped to V1-V5 + extraction + classification + geometry cleanup); this
# threshold only drives which parts get named in the confirmation report
# so a human still sees exactly what needs a second look.
CONFIDENCE_CONFIRM_THRESHOLD = 0.5

_WHEEL_ROLES = (PartRole.WHEEL_FL, PartRole.WHEEL_FR, PartRole.WHEEL_RL, PartRole.WHEEL_RR)


def _relay(operator, result):
    """Surface every Notice a StageResult collected, same pattern as
    ops/reset.py — a partial or failed outcome must be visible in the
    UI/log, not only live in a return value nobody reads (§1.3)."""
    for notice in (*result.errors, *result.warnings):
        level = notice.severity.value if notice.severity.value in _BLENDER_REPORT_LEVELS else 'ERROR'
        operator.report({level}, notice.message)


def _classification_summary(classification: dict) -> str:
    """§8.1 step 8's one-line report: "Found 4 wheels, 2 doors, hood,
    bumper, 6 glass panels"."""
    counts = Counter(c.role for c in classification.values())
    wheel_count = sum(counts.get(r, 0) for r in _WHEEL_ROLES)
    door_count = counts.get(PartRole.DOOR_L, 0) + counts.get(PartRole.DOOR_R, 0)
    bumper_count = counts.get(PartRole.BUMPER_F, 0) + counts.get(PartRole.BUMPER_R, 0)
    glass_count = counts.get(PartRole.GLASS, 0)
    unknown_count = counts.get(PartRole.UNKNOWN, 0)

    pieces = []
    if wheel_count:
        pieces.append(f"{wheel_count} wheel" + ("s" if wheel_count != 1 else ""))
    if door_count:
        pieces.append(f"{door_count} door" + ("s" if door_count != 1 else ""))
    if counts.get(PartRole.HOOD, 0):
        pieces.append("hood")
    if counts.get(PartRole.BOOT, 0):
        pieces.append("boot")
    if bumper_count:
        pieces.append(f"{bumper_count} bumper" + ("s" if bumper_count != 1 else ""))
    if glass_count:
        pieces.append(f"{glass_count} glass panel" + ("s" if glass_count != 1 else ""))
    if unknown_count:
        pieces.append(f"{unknown_count} unclassified")

    return "Found " + (", ".join(pieces) if pieces else "no recognisable parts")


def _write_descriptor_dump(descriptors) -> str:
    """§8.1 step 3 write-out: the same schema tools/dump_car.py uses
    (core/descriptor_io.py), so Krish can diff CF_Prep's own extraction
    against a real dump_car.py run on the same car."""
    data = dump_part_descriptors(descriptors)
    directory = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else tempfile.gettempdir()
    path = os.path.join(directory, "crash_forge_prep_dump.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    return path


class CF_OT_prep(bpy.types.Operator):
    bl_idname = "crashforge.prep"
    bl_label = "Crash Forge: Prep"
    bl_description = "Validate the scene, classify car parts, and prepare geometry for rigging"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return getattr(context.scene, "crash_forge", None) is not None and context.scene.crash_forge.car_object is not None

    def execute(self, context):
        scene = context.scene
        cf = scene.crash_forge
        car_object = cf.car_object

        parts = bl_extract.collect_car_parts(car_object)
        if not parts:
            self.report({'ERROR'}, "CF_Prep: no mesh objects found under the selected car object")
            return {'CANCELLED'}

        descriptors = bl_extract.extract_part_descriptors(parts)
        meta = bl_extract.extract_scene_meta(scene, parts)

        # §11 V1, V2, V3, V5, V21 — all in one pass, every hard-stop
        # collected before this operator gives up (§3 rule 10).
        validation = core_validate.run_prep_validations(meta, descriptors)
        _relay(self, validation)
        if not validation.ok:
            self.report({'ERROR'}, "CF_Prep: validation failed, stopping (see messages above)")
            return {'CANCELLED'}

        scene.frame_end = validation.data["frame_end"]

        # Step 1: snapshot original_state before anything below touches a part.
        snapshot = bl_scene.snapshot_car_parts(parts)
        cf.original_state = json.dumps(snapshot)

        # Step 4/5: forward axis + classification (M3's core, untouched here).
        forward_axis = detect_forward_axis(descriptors)
        classification = classify(descriptors, forward_axis)
        by_name = {obj.name: obj for obj in parts}
        for name, result_c in classification.items():
            obj = by_name.get(name)
            if obj is not None:
                obj["cf_role"] = result_c.role.value

        # Step 6: clean geometry (V4), then re-apply auto-smooth — order
        # matters, the stale attributes must be gone before auto-smooth
        # regenerates shading from scratch. apply_shade_auto_smooth can
        # fail (confirmed on a real car: shade_auto_smooth.poll() rejects
        # an unexpected context) — never a silent partial result (§3
        # rule 10), so a failure here stops Prep and names every
        # offending part rather than leaving some parts cleaned and
        # others not with no indication which.
        auto_smooth_failures = []
        for obj in parts:
            bl_apply.clean_mesh_shading_attributes(obj)
            if not bl_apply.apply_shade_auto_smooth(context, obj):
                auto_smooth_failures.append(obj.name)

        if auto_smooth_failures:
            self.report(
                {'ERROR'},
                f"CF_Prep: shade-auto-smooth failed on {len(auto_smooth_failures)} "
                f"part(s), stopping: {auto_smooth_failures}",
            )
            return {'CANCELLED'}

        # Step 7: origin to each part's own centre of mass. Same
        # fail-loud treatment as step 6, for the same reason.
        origin_failures = []
        for obj in parts:
            if not bl_apply.set_origin_to_center_of_mass(context, obj):
                origin_failures.append(obj.name)

        if origin_failures:
            self.report(
                {'ERROR'},
                f"CF_Prep: origin-to-center-of-mass failed on {len(origin_failures)} "
                f"part(s), stopping: {origin_failures}",
            )
            return {'CANCELLED'}

        # Step 3 (write-out) + step 8 (one-line report).
        dump_path = _write_descriptor_dump(descriptors)
        summary = _classification_summary(classification)
        low_confidence = sorted(
            name for name, c in classification.items() if c.confidence < CONFIDENCE_CONFIRM_THRESHOLD
        )

        self.report({'INFO'}, f"CF_Prep: {summary}. Descriptor dump written to {dump_path}")
        if low_confidence:
            self.report(
                {'WARNING'},
                f"CF_Prep: low confidence on {len(low_confidence)} part(s), please confirm manually: {low_confidence}",
            )

        cf.stage_completed = 1
        return {'FINISHED'}


CLASSES = (CF_OT_prep,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
