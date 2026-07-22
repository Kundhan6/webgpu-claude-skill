"""Stage 2 — Tag: auto-suggest roles, bulk role set, tag-color view, presets."""

import json

import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty
from bpy.types import Operator, UIList
from bpy_extras.io_utils import ExportHelper, ImportHelper

_ADDON_PACKAGE = __package__.split(".")[0]

# Bounding-box thinness ratio (min dimension / max dimension) below which an
# object is suggested as DEFORM (thin sheet-metal body panels).
THIN_RATIO_THRESHOLD = 0.15
# Bounding-box volume (m^3) below which an object is suggested as RIGID
# (small hardware: bolts, brackets, handles).
SMALL_BBOX_VOLUME_M3 = 0.01

ROLE_COLORS = {
    'RIGID': (0.6, 0.6, 0.6, 1.0),
    'DEFORM': (0.2, 0.4, 0.9, 1.0),
    'FRACTURE': (0.9, 0.2, 0.2, 1.0),
    'DETACH': (0.9, 0.6, 0.1, 1.0),
    'PASSIVE': (0.2, 0.8, 0.3, 1.0),
}


def _match_material_class(obj, keywords):
    if not obj.data.materials:
        return None
    for mat_slot in obj.data.materials:
        if mat_slot is None:
            continue
        name_lower = mat_slot.name.lower()
        for kw in keywords:
            if kw.keyword and kw.keyword.lower() in name_lower:
                return kw.material_class
    return None


class CRASHFORGE_UL_object_tags(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        split = layout.split(factor=0.4)
        split.label(text=item.name, icon='MESH_DATA' if item.type == 'MESH' else 'OBJECT_DATA')
        row = split.row(align=True)
        row.prop(item.crashforge, "role", text="")
        row.prop(item.crashforge, "material_class", text="")

    def filter_items(self, context, data, propname):
        objects = getattr(data, propname)
        flags = []
        for obj in objects:
            flag = self.bitflag_filter_item if obj.type == 'MESH' else 0
            flags.append(flag)
        order = bpy.types.UI_UL_list.sort_items_by_name(objects, "name")
        return flags, order


class CRASHFORGE_OT_auto_suggest_tags(Operator):
    bl_idname = "crashforge.auto_suggest_tags"
    bl_label = "Auto-Suggest Tags"
    bl_description = "Suggest role and material class per mesh object; does not lock anything, freely editable after"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        addon = context.preferences.addons.get(_ADDON_PACKAGE)
        keywords = addon.preferences.material_keywords if addon else []

        scene = context.scene
        touched = 0
        for obj in scene.objects:
            if obj.type != 'MESH':
                continue

            material_class = _match_material_class(obj, keywords)
            if material_class:
                obj.crashforge.material_class = material_class

            dims = obj.dimensions
            max_dim = max(dims.x, dims.y, dims.z)
            min_dim = min(dims.x, dims.y, dims.z)
            volume = dims.x * dims.y * dims.z

            suggested_role = None
            if max_dim > 0 and (min_dim / max_dim) < THIN_RATIO_THRESHOLD:
                suggested_role = 'DEFORM'
            elif volume < SMALL_BBOX_VOLUME_M3:
                suggested_role = 'RIGID'

            if material_class == 'GLASS':
                suggested_role = 'FRACTURE'

            if suggested_role:
                obj.crashforge.role = suggested_role
                touched += 1

        scene.crashforge_tags_touched = True
        self.report({'INFO'}, f"Crash Forge: suggested tags for {touched} object(s).")
        return {'FINISHED'}


class CRASHFORGE_OT_bulk_set_role(Operator):
    bl_idname = "crashforge.bulk_set_role"
    bl_label = "Set Role"
    bl_description = "Set the Crash Forge role on every selected object"
    bl_options = {'REGISTER', 'UNDO'}

    role: EnumProperty(
        items=(
            ('RIGID', "Rigid", ""),
            ('DEFORM', "Deform", ""),
            ('FRACTURE', "Fracture", ""),
            ('DETACH', "Detach", ""),
            ('PASSIVE', "Passive", ""),
        ),
    )

    def execute(self, context):
        selected = context.selected_objects
        if not selected:
            self.report({'WARNING'}, "Crash Forge: no objects selected.")
            return {'CANCELLED'}

        for obj in selected:
            obj.crashforge.role = self.role

        context.scene.crashforge_tags_touched = True
        self.report({'INFO'}, f"Crash Forge: set role '{self.role}' on {len(selected)} object(s).")
        return {'FINISHED'}


class CRASHFORGE_OT_toggle_tag_view(Operator):
    bl_idname = "crashforge.toggle_tag_view"
    bl_label = "Toggle Tag View"
    bl_description = "Color objects by role and switch viewport shading to Object Color; toggle again to restore Material Color"

    @classmethod
    def poll(cls, context):
        return context.space_data is not None and context.space_data.type == 'VIEW_3D'

    def execute(self, context):
        shading = context.space_data.shading

        if shading.color_type == 'OBJECT':
            shading.color_type = 'MATERIAL'
            self.report({'INFO'}, "Crash Forge: tag view off.")
            return {'FINISHED'}

        for obj in context.scene.objects:
            if obj.type != 'MESH':
                continue
            obj.color = ROLE_COLORS.get(obj.crashforge.role, (1.0, 1.0, 1.0, 1.0))

        shading.color_type = 'OBJECT'
        self.report({'INFO'}, "Crash Forge: tag view on.")
        return {'FINISHED'}


class CRASHFORGE_OT_save_tag_preset(Operator, ExportHelper):
    bl_idname = "crashforge.save_tag_preset"
    bl_label = "Save Tag Preset"
    bl_description = "Save every mesh object's role and material class to a JSON preset, keyed by object name"

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={'HIDDEN'})

    def execute(self, context):
        data = {}
        for obj in context.scene.objects:
            if obj.type != 'MESH':
                continue
            data[obj.name] = {
                "role": obj.crashforge.role,
                "material_class": obj.crashforge.material_class,
            }

        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError as exc:
            self.report({'ERROR'}, f"Crash Forge: could not write preset: {exc}")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Crash Forge: saved tag preset for {len(data)} object(s).")
        return {'FINISHED'}


class CRASHFORGE_OT_load_tag_preset(Operator, ImportHelper):
    bl_idname = "crashforge.load_tag_preset"
    bl_label = "Load Tag Preset"
    bl_description = "Load a JSON tag preset, matching entries to current scene objects by name"

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={'HIDDEN'})

    def execute(self, context):
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            self.report({'ERROR'}, f"Crash Forge: could not read preset: {exc}")
            return {'CANCELLED'}

        applied = 0
        for obj_name, entry in data.items():
            obj = context.scene.objects.get(obj_name)
            if obj is None or obj.type != 'MESH':
                continue
            role = entry.get("role")
            material_class = entry.get("material_class")
            if role:
                obj.crashforge.role = role
            if material_class:
                obj.crashforge.material_class = material_class
            applied += 1

        context.scene.crashforge_tags_touched = True
        self.report({'INFO'}, f"Crash Forge: applied preset to {applied} of {len(data)} entrie(s).")
        return {'FINISHED'}


classes = (
    CRASHFORGE_UL_object_tags,
    CRASHFORGE_OT_auto_suggest_tags,
    CRASHFORGE_OT_bulk_set_role,
    CRASHFORGE_OT_toggle_tag_view,
    CRASHFORGE_OT_save_tag_preset,
    CRASHFORGE_OT_load_tag_preset,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.crashforge_tag_index = IntProperty(default=0)
    bpy.types.Scene.crashforge_tags_touched = BoolProperty(default=False)


def unregister():
    try:
        del bpy.types.Scene.crashforge_tags_touched
    except AttributeError:
        pass
    try:
        del bpy.types.Scene.crashforge_tag_index
    except AttributeError:
        pass
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
