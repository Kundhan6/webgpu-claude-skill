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

from ..core.naming import (
    CF_GENERATED_KEY,
    CF_UID_KEY,
    build_snapshot,
    match_snapshot_records,
    new_cf_uid,
    parse_snapshot,
)
from ..core.report import StageResult


def _load_snapshot_records(scene):
    """Decode + validate scene.crash_forge.original_state. Returns
    (records, error); records is [] on any failure, including malformed
    JSON — treated the same as an unrecognised schema, not a crash."""
    raw = scene.crash_forge.original_state
    if not raw:
        return [], None
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError) as exc:
        return [], f"original_state is not valid JSON: {exc}"
    return parse_snapshot(parsed)


class CF_PG_scene_state(bpy.types.PropertyGroup):
    """Scene.crash_forge — §7.2."""

    car_object: bpy.props.PointerProperty(type=bpy.types.Object, name="Car")
    target_object: bpy.props.PointerProperty(type=bpy.types.Object, name="Target")
    # §12.3 step 5: a bounding box gives the forward *axis*, never which
    # end is the nose — detect_forward_sign()'s glass heuristic is a
    # best-effort guess (confirmed degenerate whenever a car has glass at
    # both ends, i.e. almost always — see tests/test_forward_sign.py), so
    # a wrong guess must be correctable, not just silently trusted.
    forward_sign_override: bpy.props.EnumProperty(
        name="Forward Direction",
        description="Override CF_Prep's auto-detected forward direction if it guessed wrong",
        items=[
            ('AUTO', "Auto-detect", "Guess from glass position (unreliable — verify against the CF_Prep report)"),
            ('POSITIVE', "+ (positive axis)", "Force forward to the positive end of the detected axis"),
            ('NEGATIVE', "- (negative axis)", "Force forward to the negative end of the detected axis"),
        ],
        default='AUTO',
    )
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
    opposed to cf_generated objects, which are Crash Forge's own.

    A snapshot this build can't parse (bad JSON, unrecognised
    schema_version) just yields an empty name set here — cf_* markers on
    the objects themselves still catch anything Crash Forge touched. The
    restore step is where an unparseable snapshot actually gets reported;
    this is only ever an extra net, never the sole source of truth."""
    records, _error = _load_snapshot_records(scene)
    snapshot_names = {r["name"] for r in records if r.get("name")}
    touched = []
    for obj in bpy.data.objects:
        if is_cf_generated(obj):
            continue
        has_cf_prop = any(k.startswith("cf_") for k in obj.keys())
        if obj.name in snapshot_names or has_cf_prop:
            touched.append(obj)
    return touched


def _ensure_cf_uid(obj) -> str:
    """Stamp obj["cf_uid"] once and reuse it on every later call — a
    fresh uid on every CF_Prep run would break idempotency (§3 rule 4):
    a snapshot taken on run 2 would then reference a different uid than
    run 1's, even though nothing about the object changed."""
    uid = obj.get(CF_UID_KEY)
    if not uid:
        uid = new_cf_uid()
        obj[CF_UID_KEY] = uid
    return uid


def snapshot_car_parts(parts) -> dict:
    """§8.1 step 1: build the original_state snapshot (build_snapshot's
    wire format, §7.2) CF_Reset's restore_original_state() above already
    knows how to read. `parts`: the bpy mesh objects CF_Prep found in the
    car hierarchy (bl/extract.py::collect_car_parts()).

    Only stamps cf_uid on objects in `parts` itself — never on some
    external parent outside the car hierarchy — so a part's own parent
    reference only carries a cf_uid when that parent is *also* one of
    the car's tracked parts (looked up from `parts`, not re-stamped from
    scratch, so every part gets exactly one uid regardless of walk
    order). A parent outside `parts` is recorded by name only, the same
    fallback match_snapshot_records() already provides for a record
    with no uid.
    """
    uid_by_name = {obj.name: _ensure_cf_uid(obj) for obj in parts}

    records = []
    for obj in parts:
        parent = obj.parent
        parent_uid = uid_by_name.get(parent.name) if parent is not None else None
        records.append({
            "cf_uid": uid_by_name[obj.name],
            "name": obj.name,
            "matrix_world": [list(row) for row in obj.matrix_world],
            "parent_uid": parent_uid,
            "parent_name": parent.name if parent is not None else None,
        })
    return build_snapshot(records)


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


def restore_original_state(scene) -> StageResult:
    """§8.0 step 5. No-op (empty StageResult) if CF_Prep (M4) never ran, so
    Reset stays safe to call on a scene Crash Forge has never touched.

    original_state is {"schema_version": int, "records": [...]}, each
    record: {"cf_uid": str|None, "name": str, "matrix_world": [[...]],
    "parent_uid": str|None, "parent_name": str|None}. cf_uid is CF_Prep's
    stamp on obj["cf_uid"] at snapshot time — the primary key, because
    object *names* can change between snapshot and Reset (manual rename,
    Prep re-running, a duplicate-and-delete) and a name-keyed lookup would
    then silently miss that object forever. Name is kept only as a
    fallback for a record that never got a uid.

    A snapshot whose schema_version this build doesn't recognise is
    refused outright — reported as an error, zero objects touched — rather
    than guessed at. CF_Prep is a separate, not-yet-built stage; the two
    sides drifting silently is a worse failure than refusing to run.

    Every record that *is* accepted either restores a live object or is
    recorded as missing — restoring some parts and staying silent about
    the rest is exactly the stale-state trap §1.3 describes; the caller
    must surface the tally.
    """
    result = StageResult()
    raw = scene.crash_forge.original_state
    if not raw:
        return result

    records, error = _load_snapshot_records(scene)
    if error is not None:
        result.error(error)
        return result

    live_objects = list(bpy.data.objects)
    live_index = [(obj.get(CF_UID_KEY), obj.name) for obj in live_objects]

    matches, missing = match_snapshot_records(records, live_index)

    restored = 0
    for record_idx, live_idx in matches.items():
        record = records[record_idx]
        obj = live_objects[live_idx]

        if "matrix_world" in record:
            obj.matrix_world = record["matrix_world"]

        if "parent_uid" in record or "parent_name" in record:
            obj.parent = _resolve_one(record.get("parent_uid"), record.get("parent_name"), live_index, live_objects)

        restored += 1

    result.data.update(total=len(records), restored=restored, missing=missing)
    if missing:
        result.warn(f"Restored {restored} of {len(records)} part(s); {len(missing)} not found: {missing}")
    else:
        result.info(f"Restored {restored} of {len(records)} part(s)")
    return result


def _resolve_one(uid, name, live_index, live_objects):
    matches, _ = match_snapshot_records([{"cf_uid": uid, "name": name}], live_index)
    idx = matches.get(0)
    return live_objects[idx] if idx is not None else None


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
            # Identity is is_cf_generated(), never a parsed/prefixed name (§3
            # rule 8 says generated objects *are* prefixed CF_, but this
            # self-check is the last line of defence against exactly the
            # case that guarantee doesn't hold — a generated object renamed
            # after creation, or any other name that doesn't happen to
            # start with "CF_". A name-based check here would let that
            # object sail through as "clean" and silently violate V20.
            stale = [o.name for o in coll.objects if is_cf_generated(o)]
            if stale:
                problems.append(f"rigidbody_world.{coll_name} still has cf_generated objects: {stale}")
    return problems
