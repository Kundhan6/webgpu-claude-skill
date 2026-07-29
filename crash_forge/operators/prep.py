"""Stage 1 — Prep: scene analysis, issue selection, material-based sort."""

import bmesh
import bpy
from bpy.props import CollectionProperty, EnumProperty, IntProperty, StringProperty
from bpy.types import Operator, PropertyGroup
from mathutils import Quaternion, Vector

from ..utils.register_utils import register_classes, unregister_classes

_ADDON_PACKAGE = __package__.split(".")[0]

DOUBLES_DISTANCE = 0.0001
DEGENERATE_AREA_EPSILON = 1e-8
NON_UNIFORM_SCALE_EPSILON = 1e-4
ROTATION_EPSILON = 1e-4


class CrashForgeIssueEntry(PropertyGroup):
    object_name: StringProperty()
    issue_type: StringProperty()
    element_type: EnumProperty(
        items=(
            ('VERT', "Vertex", ""),
            ('EDGE', "Edge", ""),
            ('FACE', "Face", ""),
            ('OBJECT', "Object", ""),
        ),
    )
    indices: StringProperty(description="Comma-separated bmesh element indices; empty for object-level issues")


def _add_issue(scene, obj, issue_type, element_type, indices):
    entry = scene.crashforge_issues.add()
    entry.object_name = obj.name
    entry.issue_type = issue_type
    entry.element_type = element_type
    entry.indices = ",".join(str(i) for i in indices)


class CRASHFORGE_OT_analyze_scene(Operator):
    bl_idname = "crashforge.analyze_scene"
    bl_label = "Analyze Scene"
    bl_description = (
        "Scan mesh objects for doubles, non-manifold edges, degenerate/interior "
        "faces, non-uniform scale, and unapplied rotation"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        scene.crashforge_issues.clear()

        mesh_objects = [obj for obj in scene.objects if obj.type == 'MESH']
        if not mesh_objects:
            self.report({'WARNING'}, "Crash Forge: no mesh objects in the scene to analyze.")
            return {'CANCELLED'}

        errors = 0
        for obj in mesh_objects:
            try:
                self._analyze_object(scene, obj)
            except Exception as exc:
                errors += 1
                self.report({'ERROR'}, f"Crash Forge: failed to analyze '{obj.name}': {exc}")

        count = len(scene.crashforge_issues)
        if errors:
            self.report({'WARNING'}, f"Crash Forge: analysis finished with {errors} object(s) skipped due to errors.")
        elif count == 0:
            self.report({'INFO'}, "Crash Forge: scene analysis clean, no issues found.")
        else:
            self.report({'WARNING'}, f"Crash Forge: found {count} issue(s). See the Prep report list.")
        return {'FINISHED'}

    def _analyze_object(self, scene, obj):
        sx, sy, sz = obj.scale
        if abs(sx - sy) > NON_UNIFORM_SCALE_EPSILON or abs(sy - sz) > NON_UNIFORM_SCALE_EPSILON:
            _add_issue(scene, obj, "Non-uniform scale", 'OBJECT', [])

        _, rot, _ = obj.matrix_world.decompose()
        identity_quat = Quaternion((1.0, 0.0, 0.0, 0.0))
        if rot.rotation_difference(identity_quat).angle > ROTATION_EPSILON:
            _add_issue(scene, obj, "Unapplied rotation", 'OBJECT', [])

        bm = bmesh.new()
        try:
            bm.from_mesh(obj.data)
            bm.verts.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
            bm.faces.ensure_lookup_table()

            if bm.verts:
                result = bmesh.ops.find_doubles(bm, verts=bm.verts, dist=DOUBLES_DISTANCE)
                dup_indices = sorted({v.index for v in result['targetmap'].keys()})
                if dup_indices:
                    _add_issue(scene, obj, "Duplicate vertices", 'VERT', dup_indices)

            nonmanifold = [e.index for e in bm.edges if not e.is_manifold]
            if nonmanifold:
                _add_issue(scene, obj, "Non-manifold edges", 'EDGE', nonmanifold)

            degenerate = [f.index for f in bm.faces if f.calc_area() < DEGENERATE_AREA_EPSILON]
            if degenerate:
                _add_issue(scene, obj, "Degenerate faces", 'FACE', degenerate)

            if bm.verts:
                centroid = sum((v.co for v in bm.verts), Vector()) / len(bm.verts)
                interior = []
                for f in bm.faces:
                    to_face = f.calc_center_median() - centroid
                    if to_face.length_squared > 0 and f.normal.dot(to_face) < 0:
                        interior.append(f.index)
                if interior:
                    _add_issue(scene, obj, "Possible interior/flipped faces", 'FACE', interior)
        finally:
            bm.free()


class CRASHFORGE_OT_select_issue(Operator):
    bl_idname = "crashforge.select_issue"
    bl_label = "Select Issue"
    bl_description = "Select the reported elements in Edit Mode"
    bl_options = {'REGISTER', 'UNDO'}

    report_index: IntProperty()

    def execute(self, context):
        scene = context.scene
        if self.report_index < 0 or self.report_index >= len(scene.crashforge_issues):
            self.report({'ERROR'}, "Crash Forge: invalid issue index.")
            return {'CANCELLED'}

        entry = scene.crashforge_issues[self.report_index]
        obj = scene.objects.get(entry.object_name)
        if obj is None or obj.type != 'MESH':
            self.report({'ERROR'}, f"Crash Forge: object '{entry.object_name}' no longer exists.")
            return {'CANCELLED'}

        if context.object and context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        context.view_layer.objects.active = obj

        if entry.element_type == 'OBJECT':
            self.report({'INFO'}, f"Crash Forge: selected object '{obj.name}' ({entry.issue_type}).")
            return {'FINISHED'}

        bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(obj.data)
        for elem_seq in (bm.verts, bm.edges, bm.faces):
            for elem in elem_seq:
                elem.select = False

        try:
            indices = [int(i) for i in entry.indices.split(",") if i != ""]
        except ValueError:
            indices = []

        lookup = {'VERT': bm.verts, 'EDGE': bm.edges, 'FACE': bm.faces}[entry.element_type]
        lookup.ensure_lookup_table()
        for i in indices:
            if 0 <= i < len(lookup):
                lookup[i].select = True

        bmesh.update_edit_mesh(obj.data)
        self.report(
            {'INFO'},
            f"Crash Forge: selected {len(indices)} {entry.element_type.lower()}(s) on '{obj.name}'.",
        )
        return {'FINISHED'}


class CRASHFORGE_OT_sort_collections(Operator):
    bl_idname = "crashforge.sort_collections"
    bl_label = "Sort into Collections"
    bl_description = "Move mesh objects into per-material-class collections based on material name keywords"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        addon = context.preferences.addons.get(_ADDON_PACKAGE)
        if addon is None:
            self.report({'ERROR'}, "Crash Forge: add-on preferences not found.")
            return {'CANCELLED'}

        keywords = addon.preferences.material_keywords
        if len(keywords) == 0:
            self.report({'WARNING'}, "Crash Forge: no material keywords configured in Preferences.")
            return {'CANCELLED'}

        scene = context.scene
        moved = 0
        for obj in list(scene.objects):
            if obj.type != 'MESH' or not obj.data.materials:
                continue
            material_class = self._match_material_class(obj, keywords)
            if material_class is None:
                continue
            target = self._get_or_create_collection(scene, material_class)
            for coll in list(obj.users_collection):
                coll.objects.unlink(obj)
            target.objects.link(obj)
            moved += 1

        self.report({'INFO'}, f"Crash Forge: sorted {moved} object(s) into material collections.")
        return {'FINISHED'}

    @staticmethod
    def _match_material_class(obj, keywords):
        for mat_slot in obj.data.materials:
            if mat_slot is None:
                continue
            name_lower = mat_slot.name.lower()
            for kw in keywords:
                if kw.keyword and kw.keyword.lower() in name_lower:
                    return kw.material_class
        return None

    @staticmethod
    def _get_or_create_collection(scene, material_class):
        name = f"CrashForge_{material_class.title()}"
        coll = bpy.data.collections.get(name)
        if coll is None:
            coll = bpy.data.collections.new(name)
            scene.collection.children.link(coll)
        return coll


classes = (
    CrashForgeIssueEntry,
    CRASHFORGE_OT_analyze_scene,
    CRASHFORGE_OT_select_issue,
    CRASHFORGE_OT_sort_collections,
)


def register():
    register_classes(classes)
    bpy.types.Scene.crashforge_issues = CollectionProperty(type=CrashForgeIssueEntry)
    bpy.types.Scene.crashforge_issues_index = IntProperty(default=0)


def unregister():
    try:
        del bpy.types.Scene.crashforge_issues_index
    except AttributeError:
        pass
    try:
        del bpy.types.Scene.crashforge_issues
    except AttributeError:
        pass
    unregister_classes(classes)
