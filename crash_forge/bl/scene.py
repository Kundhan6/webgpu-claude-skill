"""bl/scene.py — collection/rigidbody-world plumbing + the Scene-level Crash
Forge state (§7.2). Thin bpy layer: no decisions are made here — core/
decides what should happen, this module is just the mechanical bpy calls
to make it happen. All access to bpy.props/bpy.types/bpy.ops goes through
attribute access (`bpy.props.X`, not `from bpy.props import X`) so this
also works against the Tier B stub, which does not implement bpy as a
real multi-file package.
"""
import json

import bpy

from ..core.naming import CF_GENERATED_KEY


class CF_PG_scene_state(bpy.types.PropertyGroup):
    """Scene.crash_forge — §7.2."""

    car_object: bpy.props.PointerProperty(type=bpy.types.Object, name="Car")
    target_object: bpy.props.PointerProperty(type=bpy.types.Object, name="Target")
    speed_kmh: bpy.props.FloatProperty(name="Speed (km/h)", default=60.0, min=0.0)
    crumple_detail: bpy.props.IntProperty(name="Crumple Detail", default=5, min=1, max=10)
    panel_toughness: bpy.props.FloatProperty(name="Panel Toughness", default=0.5, min=0.0, max=1.0)
    shard_density: bpy.props.IntProperty(name="Shard Density", default=5, min=1, max=10)
    enable_debris: bpy.props.BoolProperty(name="Enable Debris", default=False)

    # derived / written by stages — never edited by the user
    stage_completed: bpy.props.IntProperty(default=0)
    impact_frame: bpy.props.IntProperty(default=-1)
    impact_vector: bpy.props.FloatVectorProperty(size=3)
    original_state: bpy.props.StringProperty()
    probe_report: bpy.props.StringProperty()


CLASSES = (CF_PG_scene_state,)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.crash_forge = bpy.props.PointerProperty(type=CF_PG_scene_state)


def unregister():
    del bpy.types.Scene.crash_forge
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


# --- rigidbody-world plumbing ------------------------------------------


def get_rigidbody_world(scene):
    return getattr(scene, "rigidbody_world", None)


def is_cf_generated(obj) -> bool:
    return bool(obj.get(CF_GENERATED_KEY, False))


def unlink_from_rigidbody_world(scene, obj) -> None:
    """Remove obj from both rigidbody_world.collection and .constraints.

    §1.3 / §8.0 step 2: these are separate collections from the scene —
    deleting an object from the scene does not remove it from the rigid
    body world. This is the exact leak v1 missed. Safe to call even if obj
    is a member of neither.
    """
    rbw = get_rigidbody_world(scene)
    if rbw is None:
        return
    if rbw.collection is not None and obj.name in rbw.collection.objects:
        rbw.collection.objects.unlink(obj)
    if rbw.constraints is not None and obj.name in rbw.constraints.objects:
        rbw.constraints.objects.unlink(obj)


def unlink_from_all_scene_collections(obj) -> None:
    for collection in list(obj.users_collection):
        collection.objects.unlink(obj)


def free_all_point_caches(context) -> bool:
    """bpy.ops.ptcache.free_bake_all, overridden and return-checked (§8.0 step 1).

    §15 flags point-cache bakes/frees as a background-mode risk. This
    fails soft (returns False on any RuntimeError) so CF_Reset can report
    a warning and keep going rather than aborting the whole reset over a
    cache-free hiccup; confirm the real behaviour via Tier C.
    """
    try:
        with context.temp_override(scene=context.scene):
            result = bpy.ops.ptcache.free_bake_all()
    except RuntimeError:
        return False
    return 'FINISHED' in result


def cf_generated_objects():
    return [obj for obj in bpy.data.objects if is_cf_generated(obj)]


def remove_cf_generated_objects(context) -> None:
    """§8.0 step 2, in the spec's exact order: rigidbody world first, then
    scene collections, then the datablock itself."""
    scene = context.scene
    for obj in cf_generated_objects():
        unlink_from_rigidbody_world(scene, obj)
        unlink_from_all_scene_collections(obj)
        bpy.data.objects.remove(obj, do_unlink=True)


def purge_orphaned_constraint_empties(context) -> None:
    """§8.0 step 3: constraint empties whose object1/object2 are None."""
    scene = context.scene
    rbw = get_rigidbody_world(scene)
    if rbw is None or rbw.constraints is None:
        return
    for obj in list(rbw.constraints.objects):
        rbc = getattr(obj, "rigid_body_constraint", None)
        if rbc is not None and rbc.object1 is None and rbc.object2 is None:
            unlink_from_rigidbody_world(scene, obj)
            unlink_from_all_scene_collections(obj)
            bpy.data.objects.remove(obj, do_unlink=True)


def touched_car_parts(scene):
    """Original car parts Crash Forge has touched: anything carrying a
    cf_* custom property, or named in the original_state snapshot — as
    opposed to cf_generated objects, which are Crash Forge's own."""
    raw = scene.crash_forge.original_state
    snapshot_names = set(json.loads(raw).keys()) if raw else set()
    touched = []
    for obj in bpy.data.objects:
        if is_cf_generated(obj):
            continue
        has_cf_prop = any(k.startswith("cf_") for k in obj.keys())
        if obj.name in snapshot_names or has_cf_prop:
            touched.append(obj)
    return touched


def clean_original_part(context, obj) -> None:
    """§8.0 step 4: undo everything Crash Forge did to one original part."""
    obj.animation_data_clear()

    for vg in list(obj.vertex_groups):
        if vg.name.startswith("CF_"):
            obj.vertex_groups.remove(vg)

    for mod in list(obj.modifiers):
        if mod.name.startswith("CF_") or mod.type == 'SURFACE_DEFORM':
            obj.modifiers.remove(mod)

    if getattr(obj, "rigid_body", None) is not None:
        with context.temp_override(object=obj, active_object=obj, selected_objects=[obj]):
            bpy.ops.rigidbody.object_remove()

    for key in list(obj.keys()):
        if key.startswith("cf_"):
            del obj[key]


def restore_original_state(scene) -> None:
    """§8.0 step 5. No-op if CF_Prep (M4) never ran, so Reset stays safe to
    call on a scene Crash Forge has never touched."""
    raw = scene.crash_forge.original_state
    if not raw:
        return
    snapshot = json.loads(raw)
    for name, state in snapshot.items():
        obj = bpy.data.objects.get(name)
        if obj is None:
            continue
        if "matrix_world" in state:
            obj.matrix_world = state["matrix_world"]
        if "parent" in state:
            parent_name = state["parent"]
            obj.parent = bpy.data.objects.get(parent_name) if parent_name else None


def reset_self_check(scene) -> list:
    """§8.0 self-check: assert both post-conditions.

    Returns a list of problem strings; empty means Reset actually worked.
    """
    problems = []
    leaked = [o.name for o in bpy.data.objects if is_cf_generated(o)]
    if leaked:
        problems.append(f"{len(leaked)} cf_generated object(s) survived reset: {leaked}")

    rbw = get_rigidbody_world(scene)
    if rbw is not None:
        for coll_name, coll in (("collection", rbw.collection), ("constraints", rbw.constraints)):
            if coll is None:
                continue
            stale = [o.name for o in coll.objects if o.name.startswith("CF_")]
            if stale:
                problems.append(f"rigidbody_world.{coll_name} still has CF_ objects: {stale}")
    return problems
