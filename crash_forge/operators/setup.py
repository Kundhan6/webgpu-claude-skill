"""One-click SETUP CAR: analyze, tag (local + Claude), and build the drive rig.

Parts stay separate objects, not joined — each keeps its own role. One real
mesh part (the "hub", e.g. the chassis) carries the driven rigid body; every
other solid part gets its own rigid body permanently welded to the hub with
a non-breaking FIXED constraint, so the whole car moves as one piece. This
is NOT Blender's parent-based "Compound Parent" collision shape — that only
works through actual object parenting with each child supplying a shape, and
more importantly a rigid body can only ever live on a MESH/CURVE/SURFACE/FONT
object, never an Empty, so there is no way to make a plain Empty the shared
physics root. Breakaway parts (DETACH/FRACTURE) get the same weld but with
use_breaking=True, so a hard hit snaps them free instead of holding forever.
"""

import threading

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy.types import Operator

from ..ai import heuristic, tagger
from ..properties import MATERIAL_DENSITY_KG_M3
from ..utils.register_utils import register_classes, unregister_classes

_ADDON_PACKAGE = __package__.split(".")[0]

# Parts welded rigidly to the hub — they move as one with the car.
SOLID_ROLES = {'RIGID', 'PASSIVE', 'DEFORM'}
# Parts welded with a breakable constraint instead.
BREAKAWAY_ROLES = {'DETACH', 'FRACTURE'}

BREAKING_THRESHOLD_BY_MATERIAL = {
    'STEEL': 8000.0,
    'GLASS': 200.0,
    'RUBBER': 1500.0,
    'PLASTIC': 600.0,
    'TRIM_CHROME': 400.0,
    'CONCRETE': 12000.0,
    'INTERIOR_FABRIC': 150.0,
}

COLLIDER_THICKNESS_OUTER = 0.02


def _prefs(context):
    addon = context.preferences.addons.get(_ADDON_PACKAGE)
    return addon.preferences if addon else None


def _car_objects(context):
    """Mesh objects the user selected, or the whole active collection."""
    selected = [o for o in context.selected_objects if o.type == 'MESH']
    if selected:
        return selected
    return [o for o in context.collection.objects if o.type == 'MESH']


def _local_tag_pass(context, objects):
    """Tag everything locally. Returns the list still worth asking Claude about."""
    prefs = _prefs(context)
    keywords = prefs.material_keywords if prefs else []

    uncertain = []
    for obj in objects:
        role, material_class, confident = heuristic.classify(obj, keywords)
        obj.crashforge.role = role
        obj.crashforge.material_class = material_class
        if not confident:
            uncertain.append(obj)
    return uncertain


def _apply_ai_tags(objects, tagged):
    applied = 0
    by_name = {o.name: o for o in objects}
    for name, (role, material_class) in tagged.items():
        obj = by_name.get(name)
        if obj is None:
            continue
        obj.crashforge.role = role
        obj.crashforge.material_class = material_class
        applied += 1
    return applied


# --- Rig construction --------------------------------------------------------

def _ensure_world(context, scene):
    if scene.rigidbody_world is None:
        bpy.ops.rigidbody.world_add()
    world = scene.rigidbody_world
    if world.collection is None:
        world.collection = bpy.data.collections.new("RigidBodyWorld")
    if world.constraints is None:
        world.constraints = bpy.data.collections.new("RigidBodyConstraints")
    return world


def _link_to_world(scene, obj):
    world = scene.rigidbody_world
    if world and world.collection and obj.name not in world.collection.objects:
        world.collection.objects.link(obj)


def _add_rigid_body(context, obj, body_type):
    """bpy.ops.rigidbody.object_add only accepts MESH/CURVE/SURFACE/FONT —
    never an Empty. Every caller here passes a real mesh part, but this
    stays defensive so a bad call reports cleanly instead of crashing the
    whole setup.
    """
    if obj.type not in {'MESH', 'CURVE', 'SURFACE', 'FONT'}:
        raise RuntimeError(f"'{obj.name}' is a {obj.type}, not a mesh — it can't carry a rigid body.")
    if obj.rigid_body is None:
        with context.temp_override(object=obj, active_object=obj, selected_objects=[obj]):
            bpy.ops.rigidbody.object_add(type=body_type)
    if obj.rigid_body is not None:
        obj.rigid_body.type = body_type
    return obj.rigid_body


def _estimate_mass(obj, material_class):
    """Surface-area x sheet thickness for thin parts, volume otherwise.

    Volume-based mass is unreliable on car panels — an open shell has no
    enclosed volume and comes out near zero.
    """
    density = MATERIAL_DENSITY_KG_M3.get(material_class, 1000)
    dims = sorted(float(d) for d in obj.dimensions)
    smallest, mid, largest = dims

    if largest > 0 and (smallest / largest) < heuristic.THIN_RATIO:
        area = mid * largest
        thickness = max(smallest, 0.0008)
        return max(area * thickness * density, 0.05)

    volume = dims[0] * dims[1] * dims[2]
    return max(volume * density, 0.05)


def _pick_hub(objects):
    """Choose a real mesh part to drive and to weld everything else to.

    Prefers a PASSIVE-tagged part (chassis/frame — least likely to get
    re-tagged later); otherwise the largest solid part by bounding volume.
    Returns None if there's nothing solid to anchor on.
    """
    solids = [o for o in objects if o.crashforge.role in SOLID_ROLES]
    if not solids:
        return None

    passive = [o for o in solids if o.crashforge.role == 'PASSIVE']
    pool = passive or solids

    def volume(obj):
        d = obj.dimensions
        return d.x * d.y * d.z

    return max(pool, key=volume)


def _add_weld_constraint(context, scene, hub, obj, use_breaking, breaking_threshold, name_prefix):
    """FIXED rigid-body constraint on a small marker Empty. Constraints (unlike
    rigid bodies) are fine on Empty objects — only rigid bodies require a mesh.
    """
    empty = bpy.data.objects.new(f"{name_prefix}_{obj.name}", None)
    empty.empty_display_size = 0.08
    empty.location = obj.matrix_world.translation
    scene.collection.objects.link(empty)
    empty.crashforge.crashforge_generated = True

    with context.temp_override(object=empty, active_object=empty, selected_objects=[empty]):
        bpy.ops.rigidbody.constraint_add(type='FIXED')

    constraint = empty.rigid_body_constraint
    if constraint is None:
        return False

    constraint.object1 = hub
    constraint.object2 = obj
    constraint.use_breaking = use_breaking
    if use_breaking:
        constraint.breaking_threshold = breaking_threshold

    world = scene.rigidbody_world
    if world and world.constraints and empty.name not in world.constraints.objects:
        world.constraints.objects.link(empty)
    return True


def _weld_solid_parts(context, scene, hub, solid_parts):
    """Give every solid part its own rigid body, permanently welded to the
    hub — the car drives and hits as one piece without ever being joined.
    """
    hub_body = _add_rigid_body(context, hub, 'ACTIVE')
    if hub_body is None:
        raise RuntimeError(f"Could not add a rigid body to '{hub.name}'.")

    hub_body.collision_shape = 'CONVEX_HULL'
    hub_body.mass = _estimate_mass(hub, hub.crashforge.material_class)
    hub_body.kinematic = True
    hub_body.use_margin = True
    hub_body.collision_margin = 0.02
    _link_to_world(scene, hub)

    welded = 0
    for obj in solid_parts:
        if obj is hub:
            continue
        body = _add_rigid_body(context, obj, 'ACTIVE')
        if body is None:
            continue
        body.collision_shape = 'CONVEX_HULL'
        body.mass = _estimate_mass(obj, obj.crashforge.material_class)
        _link_to_world(scene, obj)

        if _add_weld_constraint(context, scene, hub, obj, use_breaking=False,
                                 breaking_threshold=0.0, name_prefix="CF_Weld"):
            welded += 1

    return hub_body, welded


def _build_breakaways(context, scene, hub, parts):
    """Own rigid body plus a breakable FIXED constraint back to the hub."""
    made = 0
    for obj in parts:
        body = _add_rigid_body(context, obj, 'ACTIVE')
        if body is None:
            continue
        body.collision_shape = 'CONVEX_HULL'
        body.mass = _estimate_mass(obj, obj.crashforge.material_class)
        _link_to_world(scene, obj)

        threshold = BREAKING_THRESHOLD_BY_MATERIAL.get(obj.crashforge.material_class, 1000.0)
        if _add_weld_constraint(context, scene, hub, obj, use_breaking=True,
                                 breaking_threshold=threshold, name_prefix="CF_Break"):
            made += 1
    return made


def _add_collider(obj):
    """COLLISION modifier so cloth actually hits this object."""
    for mod in obj.modifiers:
        if mod.type == 'COLLISION':
            return
    mod = obj.modifiers.new(name="CrashForgeCollision", type='COLLISION')
    settings = getattr(obj, "collision", None)
    if settings is not None and hasattr(settings, "thickness_outer"):
        settings.thickness_outer = COLLIDER_THICKNESS_OUTER
    mod["crashforge_generated"] = True


def _prepare_scene_obstacles(context, scene, car_names):
    """Every other mesh in the scene becomes something the car can hit."""
    count = 0
    for obj in scene.objects:
        if obj.type != 'MESH' or obj.name in car_names:
            continue
        if obj.crashforge.crashforge_generated:
            continue
        if obj.rigid_body is None:
            _add_rigid_body(context, obj, 'PASSIVE')
            _link_to_world(scene, obj)
        _add_collider(obj)
        count += 1
    return count


class CRASHFORGE_OT_setup_car(Operator):
    bl_idname = "crashforge.setup_car"
    bl_label = "Setup Car"
    bl_description = (
        "Tag every part, build the drive rig, and make the rest of the scene crashable. "
        "Select the car's parts first, or leave nothing selected to use the active collection"
    )
    bl_options = {'REGISTER'}

    use_ai: BoolProperty(default=True)

    _timer = None
    _thread = None
    _ai_result = None
    _ai_error = None

    def invoke(self, context, event):
        scene = context.scene
        objects = _car_objects(context)
        if not objects:
            self.report({'ERROR'}, "Crash Forge: no mesh objects found. Select the car's parts first.")
            return {'CANCELLED'}

        self.objects = objects
        self.uncertain = _local_tag_pass(context, objects)
        scene.crashforge_tags_touched = True

        prefs = _prefs(context)
        api_key = (prefs.claude_api_key.strip() if prefs else "")

        if self.use_ai and api_key and self.uncertain:
            parts = tagger.build_part_payload(self.uncertain)
            self._ai_result = None
            self._ai_error = None

            def worker():
                try:
                    self._ai_result = tagger.tag_parts(api_key, parts)
                except Exception as exc:
                    self._ai_error = str(exc)

            self._thread = threading.Thread(target=worker, daemon=True)
            self._thread.start()

            wm = context.window_manager
            self._timer = wm.event_timer_add(0.2, window=context.window)
            wm.modal_handler_add(self)
            self.report({'INFO'}, f"Crash Forge: asking Claude about {len(self.uncertain)} part(s)...")
            return {'RUNNING_MODAL'}

        return self._finish(context, ai_applied=0, ai_note=self._skip_note(api_key))

    def _skip_note(self, api_key):
        if not self.use_ai:
            return "AI tagging off"
        if not api_key:
            return "no API key, local tagging only"
        if not self.uncertain:
            return "local tagging covered everything"
        return ""

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'RUNNING_MODAL'}
        if self._thread is not None and self._thread.is_alive():
            return {'RUNNING_MODAL'}

        wm = context.window_manager
        if self._timer is not None:
            wm.event_timer_remove(self._timer)
            self._timer = None

        if self._ai_error:
            self.report({'WARNING'}, f"Crash Forge: Claude tagging skipped — {self._ai_error}")
            return self._finish(context, ai_applied=0, ai_note="Claude unavailable")

        applied = _apply_ai_tags(self.uncertain, self._ai_result or {})
        return self._finish(context, ai_applied=applied, ai_note="")

    def _finish(self, context, ai_applied, ai_note):
        scene = context.scene
        objects = [o for o in self.objects if o.name in scene.objects]

        try:
            _ensure_world(context, scene)

            solid = [o for o in objects if o.crashforge.role in SOLID_ROLES]
            breakaway = [o for o in objects if o.crashforge.role in BREAKAWAY_ROLES]

            hub = _pick_hub(objects)
            if hub is None:
                raise RuntimeError(
                    "No Rigid/Deform/Passive parts found to build the car around — "
                    "everything is tagged Detach or Fracture."
                )

            hub_body, welded = _weld_solid_parts(context, scene, hub, solid)
            broken = _build_breakaways(context, scene, hub, breakaway)

            car_names = {o.name for o in objects}
            obstacles = _prepare_scene_obstacles(context, scene, car_names)
        except Exception as exc:
            self.report({'ERROR'}, f"Crash Forge: rig build failed: {exc}")
            return {'CANCELLED'}

        scene.crashforge.car_object = hub
        scene.crashforge_setup_done = True

        counts = {}
        for obj in objects:
            counts[obj.crashforge.role] = counts.get(obj.crashforge.role, 0) + 1
        summary = ", ".join(f"{n} {role.lower()}" for role, n in sorted(counts.items()))
        scene.crashforge_setup_summary = (
            f"Hub: {hub.name}. {len(objects)} parts: {summary}. "
            f"{welded} welded, {broken} breakaway, {obstacles} obstacle(s)."
        )

        detail = f" ({ai_applied} tagged by Claude)" if ai_applied else (f" ({ai_note})" if ai_note else "")
        self.report({'INFO'}, f"Crash Forge: car ready{detail}. {scene.crashforge_setup_summary}")
        return {'FINISHED'}


class CRASHFORGE_OT_install_sdk(Operator):
    bl_idname = "crashforge.install_claude_sdk"
    bl_label = "Install Claude SDK"
    bl_description = (
        "pip-install the anthropic package into Blender's own Python. "
        "Optional — AI tagging already works without it"
    )
    bl_options = {'REGISTER'}

    def execute(self, context):
        import subprocess
        import sys

        try:
            subprocess.run([sys.executable, "-m", "ensurepip", "--upgrade"], check=False, capture_output=True)
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--upgrade", "anthropic"],
                capture_output=True,
                text=True,
                timeout=300,
            )
        except Exception as exc:
            self.report({'ERROR'}, f"Crash Forge: SDK install failed: {exc}")
            return {'CANCELLED'}

        if result.returncode != 0:
            tail = (result.stderr or result.stdout or "").strip().splitlines()
            message = tail[-1] if tail else "unknown pip error"
            self.report({'ERROR'}, f"Crash Forge: pip failed: {message}")
            return {'CANCELLED'}

        self.report({'INFO'}, "Crash Forge: Claude SDK installed. Restart Blender to use it.")
        return {'FINISHED'}


classes = (
    CRASHFORGE_OT_setup_car,
    CRASHFORGE_OT_install_sdk,
)


def register():
    register_classes(classes)
    bpy.types.Scene.crashforge_setup_done = BoolProperty(default=False)
    bpy.types.Scene.crashforge_setup_summary = StringProperty(default="")


def unregister():
    for attr in ("crashforge_setup_summary", "crashforge_setup_done"):
        try:
            delattr(bpy.types.Scene, attr)
        except AttributeError:
            pass
    unregister_classes(classes)
