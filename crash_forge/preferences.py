"""Crash Forge Add-on Preferences: material-keyword mapping and the
Verify Environment check (Cell Fracture, Mantaflow, Action API shape).
"""

import bpy
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, IntProperty, StringProperty
from bpy.types import AddonPreferences, Operator, PropertyGroup, UIList

from .properties import MATERIAL_CLASS_ITEMS
from .utils import env_check


# keyword -> material_class, seeded once so Sort into Collections (Prep
# stage) has sensible defaults to match against out of the box.
DEFAULT_MATERIAL_KEYWORDS = (
    ("steel", 'STEEL'), ("metal", 'STEEL'), ("iron", 'STEEL'), ("body", 'STEEL'),
    ("glass", 'GLASS'), ("window", 'GLASS'), ("windshield", 'GLASS'),
    ("rubber", 'RUBBER'), ("tire", 'RUBBER'), ("tyre", 'RUBBER'),
    ("plastic", 'PLASTIC'), ("bumper", 'PLASTIC'),
    ("chrome", 'TRIM_CHROME'), ("trim", 'TRIM_CHROME'), ("grille", 'TRIM_CHROME'),
    ("concrete", 'CONCRETE'), ("asphalt", 'CONCRETE'), ("road", 'CONCRETE'),
    ("fabric", 'INTERIOR_FABRIC'), ("cloth", 'INTERIOR_FABRIC'),
    ("leather", 'INTERIOR_FABRIC'), ("seat", 'INTERIOR_FABRIC'),
)


class CrashForgeMaterialKeywordItem(PropertyGroup):
    keyword: StringProperty(name="Keyword", default="")
    material_class: EnumProperty(name="Material Class", items=MATERIAL_CLASS_ITEMS, default='STEEL')


class CRASHFORGE_UL_material_keywords(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        split = layout.split(factor=0.5)
        split.prop(item, "keyword", text="", emboss=False, icon='COPY_ID')
        split.prop(item, "material_class", text="")


class CRASHFORGE_OT_add_keyword(Operator):
    bl_idname = "crashforge.add_material_keyword"
    bl_label = "Add Keyword"
    bl_description = "Add a new material keyword mapping"

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences
        item = prefs.material_keywords.add()
        item.keyword = ""
        item.material_class = 'STEEL'
        prefs.material_keywords_index = len(prefs.material_keywords) - 1
        return {'FINISHED'}


class CRASHFORGE_OT_remove_keyword(Operator):
    bl_idname = "crashforge.remove_material_keyword"
    bl_label = "Remove Keyword"
    bl_description = "Remove the selected material keyword mapping"

    @classmethod
    def poll(cls, context):
        prefs = context.preferences.addons[__package__].preferences
        return len(prefs.material_keywords) > 0

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences
        index = prefs.material_keywords_index
        prefs.material_keywords.remove(index)
        prefs.material_keywords_index = max(0, min(index, len(prefs.material_keywords) - 1))
        return {'FINISHED'}


class CRASHFORGE_OT_verify_environment(Operator):
    bl_idname = "crashforge.verify_environment"
    bl_label = "Verify Environment"
    bl_description = "Check Blender version, Cell Fracture, Mantaflow, and Action API compatibility"

    def execute(self, context):
        prefs = context.preferences.addons[__package__].preferences

        prefs.blender_version_str = ".".join(str(v) for v in bpy.app.version)

        cell_fracture_ok, cell_fracture_msg = env_check.check_cell_fracture()
        prefs.cell_fracture_available = cell_fracture_ok
        prefs.cell_fracture_message = cell_fracture_msg

        mantaflow_ok, mantaflow_msg = env_check.check_mantaflow()
        prefs.mantaflow_available = mantaflow_ok
        prefs.mantaflow_message = mantaflow_msg

        action_shape, action_msg = env_check.check_action_api_shape()
        prefs.action_api_shape = action_shape
        prefs.action_api_message = action_msg

        prefs.verify_ran = True

        if cell_fracture_ok and mantaflow_ok and action_shape == 'LAYERED':
            self.report({'INFO'}, "Crash Forge: environment looks good.")
        else:
            self.report({'WARNING'}, "Crash Forge: one or more dependencies need attention — see Preferences.")

        return {'FINISHED'}


class CrashForgeAddonPreferences(AddonPreferences):
    bl_idname = __package__

    material_keywords: CollectionProperty(type=CrashForgeMaterialKeywordItem)
    material_keywords_index: IntProperty(default=0)

    verify_ran: BoolProperty(default=False)
    blender_version_str: StringProperty(default="")
    cell_fracture_available: BoolProperty(default=False)
    cell_fracture_message: StringProperty(default="")
    mantaflow_available: BoolProperty(default=False)
    mantaflow_message: StringProperty(default="")
    action_api_shape: StringProperty(default="")
    action_api_message: StringProperty(default="")

    def draw(self, context):
        layout = self.layout

        box = layout.box()
        box.label(text="Material Keyword Mapping", icon='MATERIAL')
        row = box.row()
        row.template_list(
            "CRASHFORGE_UL_material_keywords", "",
            self, "material_keywords",
            self, "material_keywords_index",
            rows=6,
        )
        col = row.column(align=True)
        col.operator("crashforge.add_material_keyword", text="", icon='ADD')
        col.operator("crashforge.remove_material_keyword", text="", icon='REMOVE')

        box = layout.box()
        box.label(text="Environment", icon='CHECKMARK')
        box.operator("crashforge.verify_environment", icon='CHECKMARK')

        if self.verify_ran:
            col = box.column(align=True)
            col.label(text=f"Blender version: {self.blender_version_str}")

            row = col.row()
            row.label(text=self.cell_fracture_message, icon='CHECKMARK' if self.cell_fracture_available else 'ERROR')

            row = col.row()
            row.label(text=self.mantaflow_message, icon='CHECKMARK' if self.mantaflow_available else 'ERROR')

            row = col.row()
            row.label(
                text=f"[{self.action_api_shape}] {self.action_api_message}",
                icon='CHECKMARK' if self.action_api_shape == 'LAYERED' else 'ERROR',
            )


classes = (
    CrashForgeMaterialKeywordItem,
    CRASHFORGE_UL_material_keywords,
    CRASHFORGE_OT_add_keyword,
    CRASHFORGE_OT_remove_keyword,
    CRASHFORGE_OT_verify_environment,
    CrashForgeAddonPreferences,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    prefs = bpy.context.preferences.addons[__package__].preferences
    if len(prefs.material_keywords) == 0:
        for keyword, material_class in DEFAULT_MATERIAL_KEYWORDS:
            item = prefs.material_keywords.add()
            item.keyword = keyword
            item.material_class = material_class


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
