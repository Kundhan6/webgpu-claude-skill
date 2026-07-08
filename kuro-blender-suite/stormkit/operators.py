"""Operators — Apply/Remove/Bake/Preset, wired to the KURO > StormKit
panel (ui.py). Every operator declares REGISTER+UNDO (ground rule #7) and
wraps its body so no raw exception reaches the user (ground rule #6).
"""

import bpy
from bpy.props import BoolProperty, IntProperty, StringProperty
from bpy.types import Operator

from kuro_core import cleanup, log, uiutils
from stormkit import fog, lightning, precipitation, presets as sk_presets, sky, wetness, wind

_logger = log.get_logger("stormkit")

_TEARDOWN_ADDON_IDS = (
    "stormkit:wetness", "stormkit:snowcover", "stormkit:snowgeometry",
)


class STORMKIT_OT_apply_to_scene(Operator):
    bl_idname = "stormkit.apply_to_scene"
    bl_label = "Apply to Scene"
    bl_description = "Build/refresh every StormKit subsystem from the current sliders"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            sky.build(context)
            fog.build(context)
            wind.build(context)
            lightning.build(context)

            state = context.scene.stormkit
            if state.precipitation_type == "RAIN":
                precipitation.build(context, "RAIN")
                precipitation.teardown(context, "SNOW")
            elif state.precipitation_type == "SNOW":
                precipitation.build(context, "SNOW")
                precipitation.teardown(context, "RAIN")
            else:
                precipitation.teardown(context)

            _applied, skipped = wetness.apply_wetness_to_scene()
            _applied_snow, skipped_snow = wetness.apply_snowcover_to_scene()

            all_skipped = skipped + skipped_snow
            context.scene["kuro_stormkit_last_skipped"] = [name for name, _reason in all_skipped]
            for name, reason in all_skipped:
                _logger.info(f"Skipped material '{name}': {reason}")

            if all_skipped:
                self.report({"WARNING"}, f"Applied; {len(all_skipped)} material(s) skipped — see report panel")
            else:
                self.report({"INFO"}, "StormKit applied to scene")
            return {"FINISHED"}
        except Exception:
            return uiutils.report_exception(self, _logger, "stormkit", "Failed to apply StormKit — see log for details")


class STORMKIT_OT_remove_all(Operator):
    bl_idname = "stormkit.remove_all"
    bl_label = "Remove StormKit"
    bl_description = "Remove every object, injected node, modifier, and handler StormKit added to this file"
    bl_options = {"REGISTER", "UNDO"}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        try:
            wetness.remove_snowcover_from_scene()
            wetness.remove_wetness_from_scene()
            sky.teardown(context)
            fog.teardown(context)
            precipitation.teardown(context)
            wind.teardown(context)
            lightning.teardown(context)
            for obj in context.scene.objects:
                wetness.remove_snow_geometry(obj)
            for addon_id in _TEARDOWN_ADDON_IDS:
                cleanup.full_removal(addon_id, _logger)
            self.report({"INFO"}, "StormKit fully removed")
            return {"FINISHED"}
        except Exception:
            return uiutils.report_exception(self, _logger, "stormkit", "Failed to fully remove StormKit — see log for details")


class STORMKIT_OT_bake_lightning(Operator):
    bl_idname = "stormkit.bake_lightning"
    bl_label = "Bake Lightning"
    bl_description = "Convert the lightning schedule to real keyframes so a render farm doesn't need the live handler"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        try:
            count = lightning.bake_lightning(context)
            self.report({"INFO"}, f"Baked lightning across {count} frame(s)")
            return {"FINISHED"}
        except Exception:
            return uiutils.report_exception(self, _logger, "stormkit", "Failed to bake lightning — see log for details")


class STORMKIT_OT_apply_preset(Operator):
    bl_idname = "stormkit.apply_preset"
    bl_label = "Apply Weather Preset"
    bl_description = "Load a preset and apply its values to the scene's weather state"
    bl_options = {"REGISTER", "UNDO"}

    preset_name: StringProperty()
    transition_frames: IntProperty(name="Transition Frames", default=0, min=0, max=1000)

    def execute(self, context):
        try:
            data = sk_presets.load(self.preset_name, _logger)
            if data is None:
                self.report({"ERROR"}, f"Preset '{self.preset_name}' could not be loaded — see log")
                return {"CANCELLED"}
            sk_presets.apply_to_scene(context, data, self.transition_frames)
            bpy.ops.stormkit.apply_to_scene()
            self.report({"INFO"}, f"Applied preset '{data.get('name', self.preset_name)}'")
            return {"FINISHED"}
        except Exception:
            return uiutils.report_exception(self, _logger, "stormkit", "Failed to apply preset — see log for details")


class STORMKIT_OT_toggle_snow_geometry(Operator):
    bl_idname = "stormkit.toggle_snow_geometry"
    bl_label = "Toggle Snow Geometry"
    bl_description = "Add/remove the (off-by-default, perf-costly) visible snow-thickness modifier on selected meshes"
    bl_options = {"REGISTER", "UNDO"}

    enable: BoolProperty(default=True)

    def execute(self, context):
        try:
            targets = [o for o in context.selected_objects if o.type == "MESH"]
            if not targets:
                targets = [o for o in context.scene.objects if o.type == "MESH"]
            for obj in targets:
                if self.enable:
                    wetness.add_snow_geometry(obj)
                else:
                    wetness.remove_snow_geometry(obj)
            return {"FINISHED"}
        except Exception:
            return uiutils.report_exception(self, _logger, "stormkit", "Failed to toggle snow geometry — see log for details")


classes = (
    STORMKIT_OT_apply_to_scene,
    STORMKIT_OT_remove_all,
    STORMKIT_OT_bake_lightning,
    STORMKIT_OT_apply_preset,
    STORMKIT_OT_toggle_snow_geometry,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
