"""Stage 3 — Drive: modal drive recording, path cleanup, impact detection."""

import math

import blf
import bpy
from bpy.props import IntProperty
from bpy.types import Operator
from mathutils import Vector

from ..utils import fcurve_compat
from ..utils.register_utils import register_classes, unregister_classes

# Simple arcade-style kinematic bicycle model — speed integrates from W/S,
# yaw rate from A/D scaled by current speed (no turning at a standstill).
MAX_SPEED = 20.0  # m/s
REVERSE_SPEED_FRACTION = 0.4
ACCEL = 8.0  # m/s^2
BRAKE_DECEL = 12.0
FRICTION_DECEL = 3.0
MAX_YAW_RATE = 1.2  # rad/s, scaled by speed fraction
TIMER_HZ = 30.0


def _insert_kinematic_switch(operator, car, impact_frame):
    """Hold rigid_body.kinematic True up to impact_frame - 1, False from
    impact_frame on, so Bullet inherits the preceding animated velocity.
    Silently skipped (with a report) if Rig hasn't given the car a rigid
    body yet — Drive can run before Rig in the stage order.
    """
    if car.rigid_body is None:
        operator.report(
            {'WARNING'},
            "Crash Forge: car has no Rigid Body yet — impact frame/location recorded, "
            "but the kinematic release keyframe will be added once Rig has run.",
        )
        return

    car.rigid_body.kinematic = True
    car.rigid_body.keyframe_insert(data_path="kinematic", frame=impact_frame - 1)
    car.rigid_body.kinematic = False
    car.rigid_body.keyframe_insert(data_path="kinematic", frame=impact_frame)

    action = fcurve_compat.object_action(car)
    fcurve = fcurve_compat.get_fcurve(action, "rigid_body.kinematic")
    if fcurve is not None:
        for kp in fcurve.keyframe_points:
            kp.interpolation = 'CONSTANT'


def _compute_impact_speed(scene, car, impact_frame):
    action = fcurve_compat.object_action(car)
    if action is None:
        return
    loc_fcurves = sorted(fcurve_compat.get_fcurves(action, "location"), key=lambda fc: fc.array_index)
    if len(loc_fcurves) < 3:
        return

    f1 = impact_frame
    f0 = max(scene.frame_start, impact_frame - 2)
    if f1 == f0:
        return

    p1 = Vector([fc.evaluate(f1) for fc in loc_fcurves])
    p0 = Vector([fc.evaluate(f0) for fc in loc_fcurves])
    dt = (f1 - f0) / scene.render.fps
    if dt <= 0:
        return

    scene.crashforge.impact_speed = (p1 - p0).length / dt


class CRASHFORGE_OT_drive_modal(Operator):
    bl_idname = "crashforge.drive_modal"
    bl_label = "Enter Drive Mode"
    bl_description = "W/S throttle, A/D steer. Esc or right-click to finish and record the drive."
    bl_options = {'REGISTER'}

    _timer = None
    _draw_handler = None

    @classmethod
    def poll(cls, context):
        return context.scene.crashforge.car_object is not None

    def invoke(self, context, event):
        scene = context.scene
        car = scene.crashforge.car_object
        if car is None:
            self.report({'ERROR'}, "Crash Forge: set a Car Object in the Drive panel first.")
            return {'CANCELLED'}

        self.car = car
        self.speed = 0.0
        self.keys = {'W': False, 'S': False, 'A': False, 'D': False}

        wm = context.window_manager
        self._timer = wm.event_timer_add(1.0 / TIMER_HZ, window=context.window)
        wm.modal_handler_add(self)

        self._draw_handler = bpy.types.SpaceView3D.draw_handler_add(
            self._draw_hint, (), 'WINDOW', 'POST_PIXEL'
        )

        scene.frame_set(scene.frame_start)
        self.report({'INFO'}, "Crash Forge: Drive Mode — W/S throttle, A/D steer, Esc/RMB to finish.")
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            self._finish(context)
            return {'FINISHED'}

        if event.type in self.keys and event.value in {'PRESS', 'RELEASE'}:
            self.keys[event.type] = event.value == 'PRESS'
            return {'RUNNING_MODAL'}

        if event.type == 'TIMER':
            self._step(context)

        return {'RUNNING_MODAL'}

    def _step(self, context):
        scene = context.scene
        dt = 1.0 / TIMER_HZ
        car = self.car

        if self.keys['W']:
            self.speed += ACCEL * dt
        elif self.keys['S']:
            self.speed -= BRAKE_DECEL * dt
        elif self.speed > 0:
            self.speed = max(0.0, self.speed - FRICTION_DECEL * dt)
        elif self.speed < 0:
            self.speed = min(0.0, self.speed + FRICTION_DECEL * dt)

        self.speed = max(-MAX_SPEED * REVERSE_SPEED_FRACTION, min(MAX_SPEED, self.speed))

        yaw_rate = 0.0
        if self.keys['A']:
            yaw_rate += MAX_YAW_RATE
        if self.keys['D']:
            yaw_rate -= MAX_YAW_RATE
        speed_factor = max(-1.0, min(1.0, self.speed / MAX_SPEED))
        yaw_rate *= abs(speed_factor)

        car.rotation_euler.z += yaw_rate * dt
        heading = car.rotation_euler.z
        car.location.x += self.speed * dt * math.cos(heading)
        car.location.y += self.speed * dt * math.sin(heading)

        frame = scene.frame_current
        car.keyframe_insert(data_path="location", frame=frame)
        car.keyframe_insert(data_path="rotation_euler", frame=frame)

        scene.frame_set(frame + 1)

    def _draw_hint(self):
        blf.position(0, 20, 40, 0)
        blf.size(0, 16)
        blf.draw(0, "Crash Forge — Drive Mode: W/S throttle, A/D steer, Esc/RMB finish")

    def _finish(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        bpy.types.SpaceView3D.draw_handler_remove(self._draw_handler, 'WINDOW')

        scene = context.scene
        scene.crashforge.drive_end_frame = scene.frame_current
        scene.frame_set(scene.frame_start)

        bpy.ops.crashforge.clean_drive_path()
        if scene.crashforge.auto_launch_on_impact:
            bpy.ops.crashforge.detect_impact()

        self.report({'INFO'}, "Crash Forge: Drive Mode finished.")


class CRASHFORGE_OT_clean_drive_path(Operator):
    bl_idname = "crashforge.clean_drive_path"
    bl_label = "Clean Drive Path"
    bl_description = "Smooth the recorded drive keyframes"
    bl_options = {'REGISTER', 'UNDO'}

    SMOOTH_WINDOW = 2

    def execute(self, context):
        car = context.scene.crashforge.car_object
        if car is None:
            self.report({'ERROR'}, "Crash Forge: no Car Object set.")
            return {'CANCELLED'}

        action = fcurve_compat.object_action(car)
        if action is None:
            self.report({'WARNING'}, "Crash Forge: car object has no animation to clean.")
            return {'CANCELLED'}

        cleaned = 0
        for fcurve in fcurve_compat.iter_fcurves(action):
            if fcurve.data_path not in ("location", "rotation_euler"):
                continue
            self._smooth_fcurve(fcurve)
            cleaned += 1

        self.report({'INFO'}, f"Crash Forge: smoothed {cleaned} drive channel(s).")
        return {'FINISHED'}

    def _smooth_fcurve(self, fcurve):
        points = fcurve.keyframe_points
        n = len(points)
        if n < 3:
            return
        original = [kp.co[1] for kp in points]
        for i, kp in enumerate(points):
            lo = max(0, i - self.SMOOTH_WINDOW)
            hi = min(n, i + self.SMOOTH_WINDOW + 1)
            window = original[lo:hi]
            kp.co[1] = sum(window) / len(window)
            kp.handle_left_type = 'AUTO_CLAMPED'
            kp.handle_right_type = 'AUTO_CLAMPED'
        fcurve.update()


class CRASHFORGE_OT_detect_impact(Operator):
    bl_idname = "crashforge.detect_impact"
    bl_label = "Detect Impact"
    bl_description = "Step the drive range and find the first frame the car overlaps the impact target"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        car = scene.crashforge.car_object
        target = scene.crashforge.impact_target

        if car is None or target is None:
            self.report({'ERROR'}, "Crash Forge: set both Car Object and Impact Target first.")
            return {'CANCELLED'}

        try:
            from mathutils.bvhtree import BVHTree
        except ImportError as exc:
            self.report({'ERROR'}, f"Crash Forge: BVHTree unavailable: {exc}")
            return {'CANCELLED'}

        frame_start = scene.frame_start
        frame_end = scene.crashforge.drive_end_frame or scene.frame_end
        if frame_end < frame_start:
            frame_end = scene.frame_end

        original_frame = scene.frame_current
        hit_frame = None
        hit_location = None

        try:
            for frame in range(frame_start, frame_end + 1):
                scene.frame_set(frame)
                depsgraph = context.evaluated_depsgraph_get()

                car_eval = car.evaluated_get(depsgraph)
                target_eval = target.evaluated_get(depsgraph)

                car_bvh = BVHTree.FromObject(car_eval, depsgraph)
                target_bvh = BVHTree.FromObject(target_eval, depsgraph)

                overlap = car_bvh.overlap(target_bvh)
                if overlap:
                    hit_frame = frame
                    car_mesh = car_eval.to_mesh()
                    acc = Vector((0.0, 0.0, 0.0))
                    for tri_a, _tri_b in overlap:
                        poly = car_mesh.polygons[tri_a]
                        acc += car.matrix_world @ poly.center
                    hit_location = acc / len(overlap)
                    car_eval.to_mesh_clear()
                    break
        except RuntimeError as exc:
            self.report({'ERROR'}, f"Crash Forge: impact detection failed: {exc}")
            scene.frame_set(original_frame)
            return {'CANCELLED'}

        scene.frame_set(original_frame)

        if hit_frame is None:
            self.report({'WARNING'}, "Crash Forge: no overlap detected in the drive range.")
            return {'CANCELLED'}

        scene.crashforge.impact_frame = hit_frame
        scene.crashforge.impact_location = hit_location

        _insert_kinematic_switch(self, car, hit_frame)
        _compute_impact_speed(scene, car, hit_frame)

        self.report({'INFO'}, f"Crash Forge: impact detected at frame {hit_frame}.")
        return {'FINISHED'}


class CRASHFORGE_OT_set_manual_impact_frame(Operator):
    bl_idname = "crashforge.set_manual_impact_frame"
    bl_label = "Set Manual Impact Frame"
    bl_description = "Bypass BVH detection and set the impact frame directly"
    bl_options = {'REGISTER', 'UNDO'}

    frame: IntProperty(name="Impact Frame", min=0, default=0)

    def execute(self, context):
        scene = context.scene
        car = scene.crashforge.car_object
        if car is None:
            self.report({'ERROR'}, "Crash Forge: no Car Object set.")
            return {'CANCELLED'}

        scene.crashforge.impact_frame = self.frame
        _insert_kinematic_switch(self, car, self.frame)
        _compute_impact_speed(scene, car, self.frame)

        self.report({'INFO'}, f"Crash Forge: impact frame manually set to {self.frame}.")
        return {'FINISHED'}

    def invoke(self, context, event):
        self.frame = context.scene.frame_current
        return context.window_manager.invoke_props_dialog(self)


classes = (
    CRASHFORGE_OT_drive_modal,
    CRASHFORGE_OT_clean_drive_path,
    CRASHFORGE_OT_detect_impact,
    CRASHFORGE_OT_set_manual_impact_frame,
)


def register():
    register_classes(classes)


def unregister():
    unregister_classes(classes)
