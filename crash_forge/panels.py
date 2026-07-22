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

        # "Rebuild from Tags" is pinned here once build_rig exists (Rig stage).

    def _status_dots(self, context):
        scene = context.scene
        prep_clean = len(getattr(scene, "crashforge_issues", [])) == 0
        tags_touched = getattr(scene, "crashforge_tags_touched", False)
        # Drive/Rig/Bake/Export dots light up once their stages are built.
        return [
            (STATUS_LABELS[0], prep_clean),
            (STATUS_LABELS[1], tags_touched),
            (STATUS_LABELS[2], False),
            (STATUS_LABELS[3], False),
            (STATUS_LABELS[4], False),
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


classes = (
    CRASHFORGE_PT_main,
    CRASHFORGE_PT_prep,
    CRASHFORGE_PT_tag,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
