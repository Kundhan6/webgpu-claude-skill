"""CF_ naming convention and the cf_generated tag contract (§7.1). No bpy import.

Full §7.1 name table now that core/pairs.py and core/classify.py exist to
feed it from real part data (M3): CF_Proxy, CF_Barrier, CF_Hinge_<wheel>,
CF_Motor_<wheel>, CF_Break_<part>, CF_NoCol_<a>__<b>, CF_RBW, CF_RBWC.
"""
import uuid
from dataclasses import dataclass, field

CF_PREFIX = "CF_"
CF_GENERATED_KEY = "cf_generated"
CF_STAGE_KEY = "cf_stage"
CF_UID_KEY = "cf_uid"

# §7.1's fixed names — never generated, always exactly this.
PROXY_NAME = f"{CF_PREFIX}Proxy"
BARRIER_NAME = f"{CF_PREFIX}Barrier"
RBW_COLLECTION_NAME = f"{CF_PREFIX}RBW"
RBWC_COLLECTION_NAME = f"{CF_PREFIX}RBWC"

_HINGE_PREFIX = f"{CF_PREFIX}Hinge_"
_MOTOR_PREFIX = f"{CF_PREFIX}Motor_"
_BREAK_PREFIX = f"{CF_PREFIX}Break_"
_NOCOL_PREFIX = f"{CF_PREFIX}NoCol_"
_NOCOL_SEPARATOR = "__"

# original_state wire format (§7.2/§8.0 step 5). Bump this the moment the
# record shape changes — CF_Prep (M4) and CF_Reset are two independent
# writers/readers of this contract, built in separate sessions; a bare
# prose description is exactly the kind of thing that quietly drifts.
# CF_SNAPSHOT_SCHEMA_VERSION is the thing both sides can actually be
# checked against instead of trusted to agree with.
CF_SNAPSHOT_SCHEMA_VERSION = 1


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


def build_snapshot(records) -> dict:
    """Wrap per-part records with the current schema_version. CF_Prep (M4)
    should call this when writing scene.crash_forge.original_state, so the
    writer and the reader (parse_snapshot below) share one source of truth
    for the wire format instead of Prep re-deriving its own shape."""
    return {"schema_version": CF_SNAPSHOT_SCHEMA_VERSION, "records": list(records)}


def parse_snapshot(snapshot):
    """Validate and unwrap an original_state payload (already JSON-decoded).

    Returns (records, error): error is None on success. On any failure —
    not a dict, missing/wrong schema_version, no records list — records is
    [] and error explains exactly why. The point is refusal, not a guess:
    a snapshot written by a schema CF_Reset doesn't recognise must not be
    silently reinterpreted (some fields present, others coincidentally
    absent) as if it matched. Restoring from a misread snapshot is worse
    than not restoring at all.
    """
    if not isinstance(snapshot, dict):
        return [], f"original_state snapshot must be a JSON object, got {type(snapshot).__name__}"

    version = snapshot.get("schema_version")
    if version != CF_SNAPSHOT_SCHEMA_VERSION:
        return [], (
            f"original_state snapshot has schema_version={version!r}, expected "
            f"{CF_SNAPSHOT_SCHEMA_VERSION}. Refusing to restore from a format this "
            f"build doesn't recognise — re-run CF_Prep to regenerate the snapshot."
        )

    records = snapshot.get("records")
    if not isinstance(records, list):
        return [], "original_state snapshot is missing its 'records' list"

    return records, None


# --- §7.1 constraint/object name generators -------------------------------

def hinge_name(wheel: str) -> str:
    """§9.1: CF_Hinge_<wheel>."""
    return f"{_HINGE_PREFIX}{wheel}"


def motor_name(wheel: str) -> str:
    """§9.2: CF_Motor_<wheel>."""
    return f"{_MOTOR_PREFIX}{wheel}"


def break_name(part: str) -> str:
    """§9.3: CF_Break_<part>."""
    return f"{_BREAK_PREFIX}{part}"


class AmbiguousNoColNameError(ValueError):
    """Raised by nocol_name() when a part name would make the generated
    CF_NoCol_ name impossible to round-trip unambiguously."""


def nocol_name(a: str, b: str) -> str:
    """§9.4: CF_NoCol_<a>__<b>. Order matters for the generated name (not
    for the physics it represents) — callers that want a canonical form
    regardless of pair order should sort (a, b) themselves before calling.

    Raises AmbiguousNoColNameError if either name itself contains "__":
    there is no way to tell, from CF_NoCol_door__l__Body alone, whether
    the pair was ("door__l", "Body") or ("door", "l__Body") — splitting
    on the first or last occurrence of "__" guesses right for one of
    those and silently wrong for the other. §3 rule 10 (fail loud, fail
    early) means refusing to generate a name that can't be parsed back,
    not guessing and hoping the guess matches what the caller meant.
    """
    if _NOCOL_SEPARATOR in a or _NOCOL_SEPARATOR in b:
        raise AmbiguousNoColNameError(
            f"nocol_name({a!r}, {b!r}): a part name containing {_NOCOL_SEPARATOR!r} "
            f"cannot be embedded in a CF_NoCol_ pair name and parsed back unambiguously"
        )
    return f"{_NOCOL_PREFIX}{a}{_NOCOL_SEPARATOR}{b}"


@dataclass(frozen=True)
class ParsedCFName:
    """Result of parse_cf_name(). `kind` is one of "proxy", "barrier",
    "rbw", "rbwc", "hinge", "motor", "break", "nocol", or "unknown".
    `args` holds the part name(s) embedded in the name, empty for the
    fixed singleton names."""
    kind: str
    args: tuple = field(default_factory=tuple)


def parse_cf_name(name: str) -> ParsedCFName:
    """The inverse of the generators above — round-trips any name they
    produce back to its kind and embedded part name(s). A name Crash
    Forge didn't generate (including a bare "CF_" prefix with no
    recognised pattern) parses as kind="unknown", not an exception:
    scanning arbitrary scene objects for CF_ names must not crash on
    something that merely happens to start with the prefix.

    For "nocol" specifically: this only ever sees names nocol_name()
    actually produced (which never embeds a part name containing "__" —
    it refuses to generate those), so splitting on the first "__" is
    unambiguous for anything Crash Forge itself generated. A hand-crafted
    or historical CF_NoCol_ name that violates that constraint parses on
    a first-occurrence best-effort basis, which is not guaranteed correct.
    """
    if name == PROXY_NAME:
        return ParsedCFName("proxy")
    if name == BARRIER_NAME:
        return ParsedCFName("barrier")
    if name == RBW_COLLECTION_NAME:
        return ParsedCFName("rbw")
    if name == RBWC_COLLECTION_NAME:
        return ParsedCFName("rbwc")
    if name.startswith(_HINGE_PREFIX):
        return ParsedCFName("hinge", (name[len(_HINGE_PREFIX):],))
    if name.startswith(_MOTOR_PREFIX):
        return ParsedCFName("motor", (name[len(_MOTOR_PREFIX):],))
    if name.startswith(_BREAK_PREFIX):
        return ParsedCFName("break", (name[len(_BREAK_PREFIX):],))
    if name.startswith(_NOCOL_PREFIX):
        rest = name[len(_NOCOL_PREFIX):]
        if _NOCOL_SEPARATOR in rest:
            a, b = rest.split(_NOCOL_SEPARATOR, 1)
            return ParsedCFName("nocol", (a, b))
    return ParsedCFName("unknown", (name,))
