"""Stage 5 — Bake: cost estimate, bake-all with progress, cache versioning."""

import os

import bpy
from bpy.props import FloatProperty
from bpy.types import Operator

from ..utils.register_utils import register_classes, unregister_classes

# Advisory-only estimate constants (placeholders — tune once real bakes are measured).
FLUID_BYTES_PER_VOXEL = 4 * 6  # ~6 float channels (density/heat/velocity xyz) per voxel
CLOTH_BYTES_PER_VERTEX_FRAME = 4 * 6  # position + velocity per vertex per frame
RBD_BYTES_PER_OBJECT_FRAME = 4 * 13  # transform + velocity per object per frame


def _simulated_objects(scene):
    for obj in scene.objects:
        has_cloth = any(m.type == 'CLOTH' for m in obj.modifiers)
        has_fluid_domain = any(
            m.type == 'FLUID' and getattr(m, "fluid_type", None) == 'DOMAIN' for m in obj.modifiers
        )
        has_rigid_body = obj.rigid_body is not None
        if has_cloth or has_fluid_domain or has_rigid_body:
            yield obj, has_cloth, has_fluid_domain, has_rigid_body


class CRASHFORGE_OT_estimate_bake_cost(Operator):
    bl_idname = "crashforge.estimate_bake_cost"
    bl_label = "Estimate Bake Cost"
    bl_description = "Advisory estimate of bake size — frames x domain resolution^3 for fluids, plus point-cache size for cloth/rigid body"

    def execute(self, context):
        scene = context.scene
        frame_count = max(1, scene.frame_end - scene.frame_start + 1)
        total_bytes = 0

        for obj, has_cloth, has_fluid_domain, has_rigid_body in _simulated_objects(scene):
            if has_fluid_domain:
                for mod in obj.modifiers:
                    if mod.type == 'FLUID' and getattr(mod, "fluid_type", None) == 'DOMAIN':
                        res = getattr(mod.domain_settings, "resolution_max", 64)
                        total_bytes += frame_count * (res ** 3) * FLUID_BYTES_PER_VOXEL
            if has_cloth:
                total_bytes += frame_count * len(obj.data.vertices) * CLOTH_BYTES_PER_VERTEX_FRAME
            if has_rigid_body:
                total_bytes += frame_count * RBD_BYTES_PER_OBJECT_FRAME

        scene.crashforge_bake_estimate_mb = total_bytes / (1024 * 1024)
        self.report(
            {'INFO'},
            f"Crash Forge: estimated bake size ~{scene.crashforge_bake_estimate_mb:.1f} MB "
            f"over {frame_count} frame(s) (advisory only).",
        )
        return {'FINISHED'}


class CRASHFORGE_OT_bake_all(Operator):
    bl_idname = "crashforge.bake_all"
    bl_label = "Bake All Sims"
    bl_description = "Bake every point cache (cloth, rigid body, fluid) in the scene"
    bl_options = {'REGISTER'}

    _timer = None
    _state = 'START'

    def invoke(self, context, event):
        wm = context.window_manager
        wm.progress_begin(0, 100)
        self._state = 'START'
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'RUNNING_MODAL'}

        wm = context.window_manager

        if self._state == 'START':
            wm.progress_update(10)
            self._state = 'BAKING'
            return {'RUNNING_MODAL'}

        if self._state == 'BAKING':
            # bpy.ops calls run to completion synchronously on this thread —
            # there's no Python hook into ptcache.bake_all's internal
            # per-frame progress, so this reports start/done rather than a
            # smooth ramp; the bar still gives a busy indicator either way.
            try:
                bpy.ops.ptcache.bake_all(bake=True)
            except Exception as exc:
                self._cleanup(wm)
                self.report({'ERROR'}, f"Crash Forge: bake failed: {exc}")
                return {'CANCELLED'}

            wm.progress_update(100)
            self._cleanup(wm)
            self.report({'INFO'}, "Crash Forge: bake complete.")
            return {'FINISHED'}

        return {'RUNNING_MODAL'}

    def _cleanup(self, wm):
        wm.event_timer_remove(self._timer)
        wm.progress_end()


class CRASHFORGE_OT_version_cache_path(Operator):
    bl_idname = "crashforge.version_cache_path"
    bl_label = "Version Cache Path"
    bl_description = "Advance to the next unused //cache/{shot_name}_v###/ folder; never overwrites an existing version"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        shot_name = scene.crashforge.shot_name or "shot"

        base_dir = bpy.path.abspath("//cache/")
        try:
            os.makedirs(base_dir, exist_ok=True)
        except OSError as exc:
            self.report({'ERROR'}, f"Crash Forge: could not create cache directory: {exc}")
            return {'CANCELLED'}

        version = 1
        while os.path.exists(os.path.join(base_dir, f"{shot_name}_v{version:03d}")):
            version += 1

        candidate = os.path.join(base_dir, f"{shot_name}_v{version:03d}")
        try:
            os.makedirs(candidate, exist_ok=False)
        except OSError as exc:
            self.report({'ERROR'}, f"Crash Forge: could not create version folder: {exc}")
            return {'CANCELLED'}

        scene.crashforge.cache_version = version

        # Ensures each sim writes to blend-relative disk cache; Blender does
        # not expose a simple per-PointCache "write to this custom folder"
        # property without switching to External mode (meant for read-only
        # shared caches), so this stops short of repointing each cache's
        # exact directory — confirm the intended folder layout before
        # relying on this for parallel-version disk isolation.
        count = 0
        for obj in scene.objects:
            for mod in obj.modifiers:
                point_cache = getattr(mod, "point_cache", None)
                if point_cache is not None:
                    point_cache.use_disk_cache = True
                    count += 1
        if scene.rigidbody_world is not None and scene.rigidbody_world.point_cache is not None:
            scene.rigidbody_world.point_cache.use_disk_cache = True
            count += 1

        self.report(
            {'INFO'},
            f"Crash Forge: cache version set to v{version:03d} ({candidate}), {count} cache(s) using disk cache.",
        )
        return {'FINISHED'}


classes = (
    CRASHFORGE_OT_estimate_bake_cost,
    CRASHFORGE_OT_bake_all,
    CRASHFORGE_OT_version_cache_path,
)


def register():
    register_classes(classes)
    bpy.types.Scene.crashforge_bake_estimate_mb = FloatProperty(default=0.0)


def unregister():
    try:
        del bpy.types.Scene.crashforge_bake_estimate_mb
    except AttributeError:
        pass
    unregister_classes(classes)
