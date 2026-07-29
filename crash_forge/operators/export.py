"""Stage 6 — Export: route by role — Alembic (fracture/deform), OpenVDB
(dust domain), FBX (untouched rigid) — one click for Unreal Engine.
"""

import datetime
import os

import bpy
from bpy.props import StringProperty
from bpy.types import Operator

from ..utils.register_utils import register_classes, unregister_classes

ALEMBIC_ROLES = {'FRACTURE', 'DEFORM'}


def _export_dir():
    path = bpy.path.abspath("//export/")
    os.makedirs(path, exist_ok=True)
    return path


def _select_only(context, objects):
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects:
        obj.select_set(True)
    if objects:
        context.view_layer.objects.active = objects[0]


class CRASHFORGE_OT_export_for_ue(Operator):
    bl_idname = "crashforge.export_for_ue"
    bl_label = "Export for UE"
    bl_description = "Export fracture/deform meshes to Alembic, dust to OpenVDB, and untouched rigid meshes to FBX"
    bl_options = {'REGISTER'}

    def execute(self, context):
        scene = context.scene
        shot_name = scene.crashforge.shot_name or "shot"

        try:
            export_dir = _export_dir()
        except OSError as exc:
            self.report({'ERROR'}, f"Crash Forge: could not create export directory: {exc}")
            return {'CANCELLED'}

        mesh_objects = [obj for obj in scene.objects if obj.type == 'MESH']
        results = []

        alembic_objects = [obj for obj in mesh_objects if obj.crashforge.role in ALEMBIC_ROLES]
        if alembic_objects:
            result = self._export_alembic(context, scene, export_dir, shot_name, alembic_objects)
            if result:
                results.append(result)

        dust_domains = [
            obj for obj in mesh_objects
            if any(m.type == 'FLUID' and getattr(m, "fluid_type", None) == 'DOMAIN' for m in obj.modifiers)
        ]
        for domain in dust_domains:
            result = self._export_dust(domain)
            if result:
                results.append(result)

        rigid_objects = [
            obj for obj in mesh_objects
            if obj.crashforge.role == 'RIGID' and not obj.crashforge.crashforge_generated
        ]
        if rigid_objects:
            result = self._export_fbx(context, export_dir, shot_name, rigid_objects)
            if result:
                results.append(result)

        if not results:
            self.report({'WARNING'}, "Crash Forge: nothing matched an export role.")
            return {'CANCELLED'}

        scene.crashforge_last_export_timestamp = datetime.datetime.now().isoformat(timespec='seconds')
        self.report({'INFO'}, "Crash Forge: export done — " + " | ".join(results))
        return {'FINISHED'}

    def _export_alembic(self, context, scene, export_dir, shot_name, objects):
        _select_only(context, objects)
        filepath = os.path.join(export_dir, f"{shot_name}_fracture_deform.abc")
        kwargs = dict(
            filepath=filepath,
            selected=True,
            start=scene.frame_start,
            end=scene.frame_end,
            global_scale=1.0,
        )
        try:
            bpy.ops.wm.alembic_export(**kwargs)
        except TypeError:
            # 'selected' kwarg name has moved before across Blender versions —
            # retry with just the path rather than fail the whole export.
            try:
                bpy.ops.wm.alembic_export(filepath=filepath)
            except Exception as exc:
                self.report({'ERROR'}, f"Crash Forge: Alembic export failed: {exc}")
                return None
        except Exception as exc:
            self.report({'ERROR'}, f"Crash Forge: Alembic export failed: {exc}")
            return None

        return (
            f"Alembic -> {filepath} ({len(objects)} object(s); "
            "set UE Geometry Cache import scale to 100 / -100 / 100, rotation 0)"
        )

    def _export_dust(self, domain):
        fluid_mod = next((m for m in domain.modifiers if m.type == 'FLUID'), None)
        if fluid_mod is None:
            return None
        domain_settings = fluid_mod.domain_settings
        if not hasattr(domain_settings, "cache_data_format"):
            self.report({'WARNING'}, f"Crash Forge: cannot confirm OpenVDB cache format on '{domain.name}'.")
            return None

        if domain_settings.cache_data_format != 'OPENVDB':
            domain_settings.cache_data_format = 'OPENVDB'
            self.report(
                {'WARNING'},
                f"Crash Forge: '{domain.name}' cache format switched to OpenVDB — re-bake before importing to UE.",
            )
            return f"Dust '{domain.name}': format set to OpenVDB (re-bake needed)"

        return f"Dust '{domain.name}': already OpenVDB, cache on disk imports as a UE Sparse Volume Texture"

    def _export_fbx(self, context, export_dir, shot_name, objects):
        _select_only(context, objects)
        filepath = os.path.join(export_dir, f"{shot_name}_rigid.fbx")
        try:
            bpy.ops.export_scene.fbx(filepath=filepath, use_selection=True)
        except Exception as exc:
            self.report({'ERROR'}, f"Crash Forge: FBX export failed: {exc}")
            return None
        return f"FBX -> {filepath} ({len(objects)} object(s))"


classes = (
    CRASHFORGE_OT_export_for_ue,
)


def register():
    register_classes(classes)
    bpy.types.Scene.crashforge_last_export_timestamp = StringProperty(default="")


def unregister():
    try:
        del bpy.types.Scene.crashforge_last_export_timestamp
    except AttributeError:
        pass
    unregister_classes(classes)
