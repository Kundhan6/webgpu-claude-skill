"""CF_ naming convention and the cf_generated tag contract (§7.1). No bpy import.

Deliberately minimal for now: only what CF_Reset (M2) needs. The full
name-generator/parser set for every constraint kind (hinge, motor, break,
no-collide pair — §7.1's full table) is M3 scope, once core/pairs.py and
core/classify.py exist to feed it from real part data. Building it now
would be exactly the "jump ahead to the interesting physics" the working
rules say not to do.
"""
import uuid

CF_PREFIX = "CF_"
CF_GENERATED_KEY = "cf_generated"
CF_STAGE_KEY = "cf_stage"
CF_UID_KEY = "cf_uid"


def is_cf_name(name: str) -> bool:
    return name.startswith(CF_PREFIX)


def cf_name(suffix: str) -> str:
    return f"{CF_PREFIX}{suffix}"


def new_cf_uid() -> str:
    """A stable identity for one car part, stamped onto obj["cf_uid"] the
    moment CF_Prep first snapshots it (M4, not yet built). Object *names*
    are not a safe key for the original_state snapshot — anything that
    renames a part between snapshot and CF_Reset (a manual rename, a
    duplicate-and-delete, Prep re-running under a different scheme) makes
    a name-keyed lookup silently miss, and that object never gets
    restored. cf_uid survives all of that; name is kept only as a
    best-effort fallback for a record that never got one."""
    return uuid.uuid4().hex


def match_snapshot_records(records, live_objects):
    """Match snapshot records against live objects. No bpy — both sides are
    plain data so this is fully unit-testable without Blender.

    `records`: iterable of dicts with a "cf_uid" (str or None/missing) and
    a "name". `live_objects`: iterable of (cf_uid, name) tuples describing
    what currently exists in the scene.

    Keys on cf_uid first; falls back to name only when a record has no
    uid or that uid matches nothing live. Returns (matches, missing):
    `matches` maps record index -> live_objects index; `missing` lists the
    identifier (name, or uid if no name) of every record that matched
    nothing, so the caller can report exactly what it couldn't restore
    instead of restoring some parts and staying quiet about the rest —
    that silent partial restore is the exact stale-state trap §1.3 warns
    about.
    """
    live_objects = list(live_objects)
    by_uid = {uid: i for i, (uid, name) in enumerate(live_objects) if uid}
    by_name = {name: i for i, (uid, name) in enumerate(live_objects) if name}

    matches = {}
    missing = []
    for idx, record in enumerate(records):
        uid = record.get("cf_uid")
        name = record.get("name")
        if uid and uid in by_uid:
            matches[idx] = by_uid[uid]
        elif name and name in by_name:
            matches[idx] = by_name[name]
        else:
            missing.append(name or uid or f"<record {idx}>")
    return matches, missing
