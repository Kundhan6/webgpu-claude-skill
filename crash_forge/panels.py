"""CRASHFORGE_PT_main + stage panels. Only Prep exists so far; the other
five stage panels arrive with their own stages.
"""

import bpy
from bpy.types import Panel

STATUS_LABELS = ("Prep", "Tag", "Drive", "Rig", "Bake", "Export")


class CRASHFORGE_PT_main(Panel):
    bl_label = "Crash Forge"
    bl_idname = "CRASHFORGE_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Crash Forge"

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        for label, ok in self._status_dots(context):
            sub = row.row(align=True)
            sub.label(text="", icon='RADIOBUT_ON' if ok else 'RADIOBUT_OFF')
            sub.label(text=label)

        layout.separator()
        layout.operator("crashforge.rebuild_from_tags", icon='FILE_REFRESH')

    def _status_dots(self, context):
        scene = context.scene
        prep_clean = len(getattr(scene, "crashforge_issues", [])) == 0
        tags_touched = getattr(scene, "crashforge_tags_touched", False)
        car = scene.crashforge.car_object
        drive_keyed = bool(car and car.animation_data and car.animation_data.action)
        rig_built = any(obj.crashforge.crashforge_generated for obj in scene.objects)
        baked = any(
            (obj.rigid_body and obj.rigid_body.type == 'ACTIVE')
            or any(m.type in {'CLOTH', 'FLUID'} for m in obj.modifiers)
            for obj in scene.objects
        ) and any(
            getattr(getattr(m, "point_cache", None), "is_baked", False)
            for obj in scene.objects
            for m in obj.modifiers
        )
        # Export dot lights up once that stage is built.
        return [
            (STATUS_LABELS[0], prep_clean),
            (STATUS_LABELS[1], tags_touched),
            (STATUS_LABELS[2], drive_keyed),
            (STATUS_LABELS[3], rig_built),
            (STATUS_LABELS[4], baked),
            (STATUS_LABELS[5], False),
        ]


class CRASHFORGE_PT_prep(Panel):
    bl_label = "Prep"
    bl_idname = "CRASHFORGE_PT_prep"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Crash Forge"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.operator("crashforge.analyze_scene", icon='VIEWZOOM')

        issues = scene.crashforge_issues
        if len(issues) == 0:
            layout.label(text="No issues found yet — click Analyze Scene.", icon='INFO')
        else:
            box = layout.box()
            box.label(text=f"{len(issues)} issue(s) found:")
            col = box.column(align=True)
            for i, entry in enumerate(issues):
                op = col.operator(
                    "crashforge.select_issue",
                    text=f"{entry.object_name}: {entry.issue_type}",
                    icon='ERROR',
                )
                op.report_index = i

        layout.separator()
        layout.operator("crashforge.sort_collections", icon='OUTLINER_COLLECTION')


class CRASHFORGE_PT_tag(Panel):
    bl_label = "Tag"
    bl_idname = "CRASHFORGE_PT_tag"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Crash Forge"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.operator("crashforge.auto_suggest_tags", icon='SHADERFX')

        layout.template_list(
            "CRASHFORGE_UL_object_tags", "",
            scene, "objects",
            scene, "crashforge_tag_index",
            rows=6,
        )

        col = layout.column(align=True)
        col.label(text="Set Role on Selected:")
        row = col.grid_flow(row_major=True, columns=3, even_columns=True, even_rows=True)
        for role_id, role_label in (
            ('RIGID', "Rigid"), ('DEFORM', "Deform"), ('FRACTURE', "Fracture"),
            ('DETACH', "Detach"), ('PASSIVE', "Passive"),
        ):
            row.operator("crashforge.bulk_set_role", text=role_label).role = role_id

        layout.separator()
        layout.operator("crashforge.toggle_tag_view", icon='SHADING_TEXTURE')

        layout.separator()
        row = layout.row(align=True)
        row.operator("crashforge.save_tag_preset", text="Save Preset", icon='EXPORT')
        row.operator("crashforge.load_tag_preset", text="Load Preset", icon='IMPORT')


class CRASHFORGE_PT_drive(Panel):
    bl_label = "Drive"
    bl_idname = "CRASHFORGE_PT_drive"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Crash Forge"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        cf = context.scene.crashforge

        col = layout.column()
        col.prop(cf, "car_object")
        col.prop(cf, "impact_target")
        col.prop(cf, "auto_launch_on_impact")

        layout.separator()
        layout.operator("crashforge.drive_modal", icon='AUTO')

        layout.separator()
        row = layout.row()
        row.enabled = cf.car_object is not None
        row.operator("crashforge.set_manual_impact_frame", icon='KEYFRAME_HLT')

        if cf.impact_frame:
            box = layout.box()
            box.label(text=f"Impact Frame: {cf.impact_frame}")
            box.label(text=f"Impact Speed: {cf.impact_speed:.2f} m/s")

        layout.separator()
        layout.prop(cf, "boost_collision_margins")


class CRASHFORGE_PT_rig(Panel):
    bl_label = "Rig"
    bl_idname = "CRASHFORGE_PT_rig"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Crash Forge"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        obj = context.active_object

        if obj is not None and obj.type == 'MESH':
            box = layout.box()
            box.label(text=f"Active: {obj.name}", icon='OBJECT_DATA')
            box.prop(obj.crashforge, "crumple_then_shatter")
            box.prop(obj.crashforge, "fracture_origin")
            box.operator("crashforge.pick_fracture_origin", icon='EYEDROPPER')
        else:
            layout.label(text="Select a mesh to edit its fracture origin.", icon='INFO')

        layout.separator()
        layout.operator("crashforge.build_rig", icon='PHYSICS')


class CRASHFORGE_PT_bake(Panel):
    bl_label = "Bake"
    bl_idname = "CRASHFORGE_PT_bake"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Crash Forge"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        row = layout.row(align=True)
        row.prop(scene.crashforge, "shot_name")
        row.prop(scene.crashforge, "cache_version")

        layout.operator("crashforge.estimate_bake_cost", icon='INFO')
        if scene.crashforge_bake_estimate_mb:
            layout.label(text=f"Estimated: ~{scene.crashforge_bake_estimate_mb:.1f} MB")

        layout.separator()
        layout.operator("crashforge.version_cache_path", icon='FILE_FOLDER')
        layout.operator("crashforge.bake_all", icon='PLAY')

        sim_objects = [
            obj for obj in scene.objects
            if obj.type == 'MESH' and (obj.rigid_body or any(m.type in {'CLOTH', 'FLUID'} for m in obj.modifiers))
        ]
        if sim_objects:
            layout.separator()
            box = layout.box()
            box.label(text="Locks:")
            for obj in sim_objects:
                row = box.row()
                row.label(text=obj.name)
                row.prop(obj.crashforge, "baked_locked", text="", icon='LOCKED' if obj.crashforge.baked_locked else 'UNLOCKED')


classes = (
    CRASHFORGE_PT_main,
    CRASHFORGE_PT_prep,
    CRASHFORGE_PT_tag,
    CRASHFORGE_PT_drive,
    CRASHFORGE_PT_rig,
    CRASHFORGE_PT_bake,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
