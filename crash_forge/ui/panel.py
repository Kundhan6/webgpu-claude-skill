"""ui/panel.py — View3D > Sidebar > Crash Forge (§16).

Only the inputs, Reset, Prep, and Rig are wired up at this stage (M0–M5).
The rest of §16's layout (CRASH IT, Tuning, remaining per-stage buttons,
Report) lands with the stages that back it — a button for a stage that
doesn't exist yet would violate §3 rule 10 (never produce a half-built
result).
"""
import bpy


class CF_PT_main(bpy.types.Panel):
    bl_label = "Crash Forge"
    bl_idname = "CF_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Crash Forge"

    def draw(self, context):
        layout = self.layout
        cf = context.scene.crash_forge

        layout.prop(cf, "car_object")
        layout.prop(cf, "forward_sign_override")
        layout.prop(cf, "target_object")
        layout.prop(cf, "speed_kmh")

        layout.separator()
        layout.operator("crashforge.prep", icon='MESH_DATA')
        layout.operator("crashforge.rig", icon='PHYSICS')
        layout.operator("crashforge.reset", icon='LOOP_BACK')

        box = layout.box()
        box.label(text="Probe report", icon='INFO')
        if cf.probe_report:
            box.label(text="See console for full Stage 0 probe output")
        else:
            box.label(text="Not yet run")


CLASSES = (CF_PT_main,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
