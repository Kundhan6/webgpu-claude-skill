"""§11 Prep-stage validations (V1, V2, V3, V5 — V4 is an unconditional
bl-side action, see below) plus one addition beyond the spec's own
table. No bpy import: every check here runs on plain data bl/extract.py
hands it, so it is fully unit-testable without Blender (§0, §3 rule 3).

V4 ("sharp_face / custom_normal removed after joins — Auto-fix") has
nothing to *check*: §8.1 step 6 always strips those attributes and
re-applies shade-auto-smooth, unconditionally. That action lives in
bl/apply.py, not here, because it's a mutation, not a validation.

Every numeric threshold below is given an exact value directly by the
spec (§11 V5: "between 4 and 25"; §11 V3: "end >= 250") — none of it is
tuned against synthetic fixtures the way core/tuning.py's constants are,
so none of it belongs there.
"""
from dataclasses import dataclass, field

from .naming import name_is_nocol_safe
from .report import StageResult

MIN_PART_COUNT = 4          # §11 V5
MAX_PART_COUNT = 25         # §11 V5 / §3 rule 7's explosion guard
MIN_FRAME_END = 250         # §11 V3


@dataclass(frozen=True)
class ObjectScaleInfo:
    """Per-object scale state, as bl/extract.py reports it for V2.
    `applied`: obj.scale is (1, 1, 1) — already baked into the mesh via
    Ctrl+A. `uniform`: the scale's three components agree with each
    other, applied or not — a non-uniform scale can still be *applied*,
    but the result is still non-uniform geometry that stays a problem for
    soft body, which assumes an isotropic space."""

    name: str
    applied: bool
    uniform: bool


@dataclass(frozen=True)
class SceneMeta:
    """Everything V1-V3 need, extracted from bpy by bl/extract.py."""

    unit_scale: float
    fps: float
    frame_start: int
    frame_end: int
    object_scales: tuple = field(default_factory=tuple)  # tuple[ObjectScaleInfo, ...]


def validate_unit_scale(meta: SceneMeta, result: StageResult) -> None:
    """V1: Hard stop — soft body is extremely scale-sensitive."""
    if meta.unit_scale != 1.0:
        result.critical(
            f"V1: scene unit scale is {meta.unit_scale}, must be exactly 1.0 — "
            f"soft body is extremely scale-sensitive. Fix: Scene Properties > "
            f"Units > Unit Scale = 1.0, then re-run Prep.",
            code="V1",
        )


def validate_object_scale(meta: SceneMeta, result: StageResult) -> list:
    """V2: object scale applied, uniform. Hard stop; offer to apply (the
    fix is reported, not silently executed — applying scale changes mesh
    data and should be a deliberate step, per §3 rule 10's "never a
    half-built rig" spirit extended to "never a silently-mutated one").
    Returns the offending object names."""
    offenders = [o.name for o in meta.object_scales if not o.applied or not o.uniform]
    if offenders:
        result.critical(
            f"V2: {len(offenders)} part(s) have unapplied or non-uniform scale: "
            f"{offenders}. Fix: select them and Object > Apply > Scale "
            f"(Ctrl+A > Scale), then re-run Prep.",
            code="V2",
        )
    return offenders


def validate_frame_range(meta: SceneMeta, result: StageResult) -> int:
    """V3: fps and frame range sane; end >= 250. Warn; auto-extend cache
    end. Returns the frame_end Prep should actually use (only different
    from meta.frame_end when it had to be extended)."""
    if meta.fps <= 0:
        result.critical(f"V3: scene fps is {meta.fps}, must be positive.", code="V3")
        return meta.frame_end

    if meta.frame_start >= meta.frame_end:
        result.critical(
            f"V3: frame_start={meta.frame_start} is not before frame_end="
            f"{meta.frame_end} — there's no timeline for the crash to run "
            f"in. Fix the scene's frame range and re-run Prep.",
            code="V3",
        )
        return meta.frame_end

    frame_end = meta.frame_end
    if frame_end < MIN_FRAME_END:
        result.warn(
            f"V3: frame_end={frame_end} is below the {MIN_FRAME_END}-frame minimum "
            f"the crash timeline needs; auto-extending to {MIN_FRAME_END}.",
            code="V3",
        )
        frame_end = MIN_FRAME_END
    return frame_end


def validate_part_count(parts, result: StageResult) -> None:
    """V5: part count between 4 and 25. Hard stop above 25 — the v1
    explosion guard (§3 rule 7)."""
    count = len(parts)
    if count > MAX_PART_COUNT:
        result.critical(
            f"V5: {count} parts found, exceeds the {MAX_PART_COUNT}-part ceiling "
            f"(§3 rule 7 — the v1 explosion guard). Join or delete parts until the "
            f"car has {MAX_PART_COUNT} or fewer separate mesh objects, then re-run Prep.",
            code="V5",
        )
    elif count < MIN_PART_COUNT:
        result.warn(
            f"V5: only {count} part(s) found; Crash Forge expects at least "
            f"{MIN_PART_COUNT} separable parts for a convincing rig.",
            code="V5",
        )


def validate_no_ambiguous_part_names(parts, result: StageResult) -> list:
    """Not one of §11's original ten Prep-time checks — added on top of
    them, carried forward from a review of core/naming.py.

    core/naming.py::nocol_name() refuses to generate a
    CF_NoCol_<a>__<b> constraint name when either part name itself
    contains "__" (raises AmbiguousNoColNameError): there is no way to
    tell CF_NoCol_door__l__Body apart from ("door__l", "Body") vs
    ("door", "l__Body"). That check previously only ever fired during
    Stage 2 Rig's pair generation, on whichever overlapping pair happened
    to include the offending part — potentially deep into an otherwise
    successful run. "Door__L" is a real, common name on downloaded car
    models: many FBX/OBJ importers use "__" as their own namespace or
    slot separator.

    §3 rule 10 ("fail loud, fail early"): the moment every part name is
    known — right here, in Prep, before Rig runs at all — is the
    earliest point this is knowable, so that's where it's checked, named
    per offending object.

    Returns the offending part names."""
    offenders = [p.name for p in parts if not name_is_nocol_safe(p.name)]
    if offenders:
        result.critical(
            f"V21 (added beyond §11's table): {len(offenders)} part name(s) "
            f"contain '__', which cannot be embedded in a CF_NoCol_<a>__<b> "
            f"no-collide constraint name and parsed back unambiguously "
            f"(core/naming.py:nocol_name). Offending object(s): {offenders}. "
            f"Rename these objects to remove '__' (e.g. \"Door__L\" -> "
            f"\"Door_L\") and re-run Prep.",
            code="V21",
        )
    return offenders


def run_prep_validations(meta: SceneMeta, parts) -> StageResult:
    """Runs every Prep-time validation in one pass and returns one
    StageResult. `.ok` goes False the moment any check hard-stops, but
    every check still runs — the user gets the whole picture in one
    report, not a fix-one-rerun-five-times loop across five separate hard
    stops. `result.data["frame_end"]` carries V3's (possibly extended)
    frame_end back to the caller regardless of ok/not-ok, so a caller
    that only cares about non-fatal state can still use it.
    """
    result = StageResult()
    validate_unit_scale(meta, result)
    validate_object_scale(meta, result)
    validate_part_count(parts, result)
    validate_no_ambiguous_part_names(parts, result)
    result.data["frame_end"] = validate_frame_range(meta, result)
    return result
