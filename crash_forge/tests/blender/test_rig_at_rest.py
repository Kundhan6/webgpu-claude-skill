"""tests/blender/test_rig_at_rest.py — Tier C ONLY. Run this INSIDE
Blender, not pytest: it does a real `import bpy` and will fail
immediately outside Blender (same reasoning as
tests/blender_probe_script.py's own docstring). `pytest.ini`'s
`norecursedirs = blender` keeps this whole directory out of the Tier A/B
collection on purpose — a filename matching `test_*.py` would otherwise
get picked up and crash pytest's collection step on the bare `import bpy`.

§8.2 step 5 / V8, tightened after reviewer correction — the previous
definition only lived as an *embedded* check inside `ops/rig.py`
(`crashforge.rig`'s own `execute()`), asserting against whatever gravity
happened to be live at that moment and never printing anything. Real
physics can only be validated in real Blender, which this repo's build
sessions never have — so writing a pytest that mocks bpy positions and
calls that "the explosion test" would prove nothing and, worse, would
read as proof where there is none. This script is the actual test:
committed once, run the same way every time, results comparable across
runs and across cars.

What it checks, and why, in order:

1. **Zero gravity before touching a single frame.** Stage 2 has no
   ground plane yet (that's Stage 3/CF_Drive's `CF_Barrier`, not built).
   With real gravity on, the whole car free-falls from frame 1 — that's
   an expected effect having nothing to do with whether the constraint
   graph and no-collide pairs are correct, and it would either false-fail
   a good rig or mask a real explosion underneath an unrelated drop.
   Gravity is restored to whatever it was before, at the end, either way.
2. **Free the point cache and reset to frame_start before stepping.** A
   stale bake — this scene's own earlier Rig attempt, or a leftover
   cache from something else entirely — replays old keyframed motion
   instead of actually re-simulating anything. That is a false pass, not
   a real one.
3. **3 frames, ASSERTED.** Threshold is `core.rig.EXPLOSION_THRESHOLD_FRACTION`
   (the exact same named constant `ops/rig.py`'s own embedded check
   uses — imported, never re-typed) times the car's own length. Failing
   this is the actual PASS/FAIL result this script reports.
4. **30 frames total, REPORTED, not asserted.** 3 frames catches a
   sudden explosion; a short window like that cannot see slow drift — a
   constraint that's subtly too loose might hold for 3 frames and creep
   for 30. This prints the worst displacement at 30 frames so a human
   can judge it, without hard-failing the run over a number nobody set a
   real threshold for yet.

This test has a structural blind spot the numbers above cannot see, and
does not try to cover it: a part with *no* constraint or parent link to
the rest of the car sits perfectly still in zero gravity and reports a
clean 0.000, indistinguishable from one correctly held in place. That
gap is closed separately, structurally, not by this script:
`core.rig.build_rig_plan()` now builds a connectivity graph (every
hinge/motor/break/parent link) and refuses to build the rig at all if
any part isn't reachable from every other part — before Rig ever
touches a single frame. If `crashforge.rig` failed below, that refusal
(named in its own error message) is a more likely cause than anything
this script's tables would show. Every SIMULATED row below (a part with
its own rigid body) is genuinely exercised by the sim; every PARENTED
row (no rigid body, just inherits a parent's transform) moves *only*
because something else did and cannot independently fail — marked as
such so a passing table can't be read as testing more than it did.

No hardcoded axis, no assumed world origin, anywhere in this script.
Forward axis/sign are resolved fresh from *this* car's real geometry via
`core.classify.detect_forward_axis()`/`resolve_forward_sign()` — never
assumed to be +X. The car's own centre is `core.geometry.union_bbox()`'s
centroid, never `(0, 0, 0)` — printed once, for reference, precisely
because a car's centre is not guaranteed to sit at the world origin (a
real car this build has been tested against has forward = -Y and a
centre at x = -0.44, neither of which a hardcoded assumption would have
gotten right).

Usage: with `scene.crash_forge.car_object` already set (Car field in the
Crash Forge panel — CF_Prep does not need to have been run first, this
script runs Reset -> Prep -> Rig itself, fresh, every time, so results
are comparable run to run):

    Scripting tab -> open this file -> Run Script

or headless, against an already-saved .blend with Car already set:

    blender.exe --background your_car.blend --python tests/blender/test_rig_at_rest.py
"""
import os
import sys

try:
    import bpy
    print(f"Blender version: {bpy.app.version_string}", flush=True)
except Exception as exc:
    print(f"Blender version: <could not read bpy.app.version_string: {exc}>", flush=True)

# This file lives at crash_forge/tests/blender/test_rig_at_rest.py --
# `import crash_forge` needs crash_forge's *parent* directory (the repo
# root) on sys.path. Never a bare relative path or os.getcwd() (CLAUDE.md
# landmine: Blender does not preserve the shell's cwd for --python).
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))          # crash_forge/tests/blender
_TESTS_DIR = os.path.dirname(_THIS_DIR)                          # crash_forge/tests
_CRASH_FORGE_DIR = os.path.dirname(_TESTS_DIR)                   # crash_forge
REPO_ROOT = os.path.dirname(_CRASH_FORGE_DIR)                    # repo root
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Defensive, same reasoning as blender_probe_script.py: a stale
# installed Crash Forge extension already in sys.modules would shadow
# this repo's copy no matter what sys.path says.
for _name in list(sys.modules):
    if _name == "crash_forge" or _name.startswith("crash_forge."):
        del sys.modules[_name]

import crash_forge  # noqa: E402
from crash_forge.bl import extract as bl_extract  # noqa: E402
from crash_forge.bl import rig as bl_rig  # noqa: E402
from crash_forge.core import rig as core_rig  # noqa: E402
from crash_forge.core.classify import VERTICAL_AXIS, PartRole, detect_forward_axis, resolve_forward_sign  # noqa: E402
from crash_forge.core.geometry import extents, union_bbox  # noqa: E402

print(f"crash_forge package resolved from: {crash_forge.__file__}", flush=True)

_resolved_root = os.path.abspath(REPO_ROOT)
assert os.path.commonpath([os.path.abspath(crash_forge.__file__), _resolved_root]) == _resolved_root, (
    f"crash_forge resolved from an unexpected location ({crash_forge.__file__}), "
    f"not under {REPO_ROOT} — a stale installed copy is shadowing this repo."
)

# §8.2 step 5, tightened per reviewer correction: 3-frame window is the
# actual PASS/FAIL gate; 30-frame window is report-only (slow drift a
# 3-frame window can't see). Not spec-numbered constants — this script's
# own definition of the test, kept here rather than in core/tuning.py
# because they're script-shape (how many frames to step), not a tuned
# physics threshold like EXPLOSION_THRESHOLD_FRACTION (which *is* in
# core/rig.py, and is reused below rather than re-typed).
ASSERT_FRAMES = 3
DRIFT_REPORT_FRAMES = 30
_AXIS_NAMES = ("X", "Y", "Z")


def _fail(message: str) -> None:
    print(f"test_rig_at_rest.py: {message}", flush=True)
    print("\ntest_rig_at_rest.py: RESULT = FAIL", flush=True)
    sys.exit(1)


def _ensure_registered() -> None:
    if not hasattr(bpy.types.Scene, "crash_forge"):
        crash_forge.register()


def _run_operator(idname: str):
    """bpy.ops.crashforge.<idname>(). A hard-stopped operator raises
    RuntimeError even though execute() itself returns {'CANCELLED'}
    cleanly (CLAUDE.md landmine — standard bpy.ops behaviour, not
    specific to Crash Forge); this normalises both paths to a returned
    result set so the caller doesn't need to know which one happened."""
    op = getattr(bpy.ops.crashforge, idname)
    try:
        return op()
    except RuntimeError as exc:
        print(f"test_rig_at_rest.py: crashforge.{idname} raised: {exc}", flush=True)
        return {'CANCELLED'}


def _resolve_forward(descriptors):
    """Forward axis/sign resolved fresh from this car's real geometry —
    never assumed. See module docstring: this build has already been
    tested against a car whose forward is -Y, not +X."""
    forward_axis = detect_forward_axis(descriptors)
    forward_sign, _confidence, source = resolve_forward_sign(descriptors, forward_axis)
    lateral_axis = 3 - forward_axis - VERTICAL_AXIS
    sign_str = "+" if forward_sign >= 0 else "-"
    print(
        f"test_rig_at_rest.py: forward = {sign_str}{_AXIS_NAMES[forward_axis]} ({source}), "
        f"lateral = {_AXIS_NAMES[lateral_axis]}, vertical = {_AXIS_NAMES[VERTICAL_AXIS]}",
        flush=True,
    )
    return forward_axis, lateral_axis


def _print_displacement_table(before: dict, after: dict, chassis_name: str, roles: dict,
                               simulated_names: set, forward_axis: int, lateral_axis: int,
                               threshold: float, header: str):
    """Per-part displacement relative to the chassis, decomposed along
    the *detected* forward/lateral/vertical axes (never a hardcoded X/Y/Z
    guess). Every car part gets a row, marked SIMULATED (has its own
    rigid body -- the sim can actually move it independently) or
    PARENTED (no rigid body at all, just inherits its parent's transform
    every frame, so it moves *only* because something else did and
    cannot fail on its own no matter what the sim does).

    Reviewer correction, this session: a table that doesn't say this out
    loud overstates how much it actually tested -- 4 wheel-hardware
    "passengers" reporting a clean 0.000 look identical to 4 genuinely
    verified parts. Only SIMULATED rows are eligible for OK/OVER status
    and the worst-part tracking used for pass/fail; PARENTED rows are
    informational only.

    Returns (worst_simulated_name, worst_simulated_magnitude).
    """
    print(f"\n{header}", flush=True)
    col_fwd = f"fwd({_AXIS_NAMES[forward_axis]})"
    col_lat = f"lat({_AXIS_NAMES[lateral_axis]})"
    col_vert = f"vert({_AXIS_NAMES[VERTICAL_AXIS]})"
    print(
        f"{'part':30s} {'role':10s} {'kind':10s} {col_fwd:>10s} {col_lat:>10s} {col_vert:>10s} "
        f"{'|delta|':>10s} {'status':>8s}",
        flush=True,
    )

    chassis_delta = tuple(after[chassis_name][i] - before[chassis_name][i] for i in range(3))
    worst_name, worst_mag = None, 0.0
    for name in sorted(before):
        if name == chassis_name or name not in after:
            continue
        part_delta = tuple(after[name][i] - before[name][i] for i in range(3))
        rel = tuple(part_delta[i] - chassis_delta[i] for i in range(3))
        mag = sum(c * c for c in rel) ** 0.5
        is_simulated = name in simulated_names
        kind = "SIMULATED" if is_simulated else "PARENTED"
        if is_simulated:
            status = "OK" if mag <= threshold else "OVER"
            if mag > worst_mag:
                worst_mag, worst_name = mag, name
        else:
            status = "n/a"
        role = roles.get(name, PartRole.UNKNOWN).value
        print(
            f"{name:30s} {role:10s} {kind:10s} {rel[forward_axis]:10.4f} {rel[lateral_axis]:10.4f} "
            f"{rel[VERTICAL_AXIS]:10.4f} {mag:10.4f} {status:>8s}",
            flush=True,
        )

    print(f"chassis {'(reference)':10s} moved {chassis_delta} in world space (excluded above by definition)", flush=True)
    return worst_name, worst_mag


def main():
    scene = bpy.context.scene
    _ensure_registered()

    cf = getattr(scene, "crash_forge", None)
    car_object = getattr(cf, "car_object", None) if cf is not None else None
    if car_object is None:
        _fail(
            "scene.crash_forge.car_object is not set. Open the Crash Forge panel, "
            "set Car, then run this script again."
        )

    # Fresh every run, deliberately -- "the same script every run so
    # results are comparable" means starting from a known clean state,
    # not trusting whatever Prep/Rig state the scene happened to be in.
    print("test_rig_at_rest.py: resetting to a clean baseline...", flush=True)
    reset_result = _run_operator("reset")
    if 'CANCELLED' in reset_result:
        _fail("CF_Reset did not complete cleanly (see the report above) -- refusing to build on a possibly-dirty scene.")

    print("test_rig_at_rest.py: running CF_Prep...", flush=True)
    prep_result = _run_operator("prep")
    if 'CANCELLED' in prep_result or cf.stage_completed < 1:
        _fail("CF_Prep did not complete (see the report above) -- nothing to rig.")

    print("test_rig_at_rest.py: running CF_Rig...", flush=True)
    rig_result = _run_operator("rig")
    if 'CANCELLED' in rig_result or cf.stage_completed < 2:
        _fail(
            "CF_Rig did not complete -- its own embedded 3-frame check already tore "
            "the rig down (see the report above), or Rig failed before reaching it."
        )

    parts = bl_extract.collect_car_parts(car_object)
    descriptors = bl_extract.extract_part_descriptors(parts)
    roles = {obj.name: PartRole(obj["cf_role"]) for obj in parts if obj.get("cf_role")}

    forward_axis, lateral_axis = _resolve_forward(descriptors)

    whole_min, whole_max = union_bbox([(d.bbox_min, d.bbox_max) for d in descriptors])
    car_length = max(extents(whole_min, whole_max))
    car_centre = tuple((whole_min[i] + whole_max[i]) / 2.0 for i in range(3))
    print(
        f"test_rig_at_rest.py: car_length={car_length:.4f}, union bbox centre={car_centre} "
        f"(reference only -- every displacement below is relative to the chassis, not this)",
        flush=True,
    )

    chassis_name = next((name for name, role in roles.items() if role == PartRole.BODY), None)
    if chassis_name is None:
        _fail("no BODY-role part found after CF_Rig -- cannot measure a rest test without a chassis.")

    by_name = {obj.name: obj for obj in parts}
    rigid_names = [name for name, obj in by_name.items() if getattr(obj, "rigid_body", None) is not None]
    simulated_names = set(rigid_names)

    # Everything else got parented instead of a rigid body -- confirm it
    # live, from real bpy state, not just from core.rig's plan. This is
    # exactly where this car's 4 degenerate brake discs (extents[0]==0.0,
    # 27 verts each) should land: a zero-thickness disc getting its own
    # CONVEX_HULL collider would be a degenerate, unstable rigid body, so
    # the design gives wheel hardware no collider and no rigid body at
    # all -- it just rides its own wheel's transform as a parented child.
    #
    # Both kinds are tracked below (not just the rigid ones) so the
    # table can show every part, not just the ones that can pass:
    # reviewer correction, this session -- a PARENTED part inherits its
    # parent's transform exactly, so it can never independently fail no
    # matter what the sim does, and a table that only ever shows
    # SIMULATED rows next to a "13/13" count would silently be counting
    # parts that were never actually exercised.
    parented = sorted(name for name in by_name if name not in rigid_names and name != chassis_name)
    tracked_names = rigid_names + parented
    tracked_objects_by_name = {name: by_name[name] for name in tracked_names}
    if parented:
        print(
            f"test_rig_at_rest.py: {len(parented)} part(s) PARENTED, not rigid-bodied "
            f"(no collider at all -- they move with their parent's transform only, cannot "
            f"independently fail this test): {parented}",
            flush=True,
        )
    print(
        f"test_rig_at_rest.py: {len(rigid_names)} part(s) SIMULATED (have their own rigid body, "
        f"chassis included) -- only these are eligible to fail the rest test below.",
        flush=True,
    )

    print(
        f"test_rig_at_rest.py: zeroing scene.gravity for the rest test (was {tuple(scene.gravity)}) "
        f"-- Stage 2 has no ground plane yet.",
        flush=True,
    )
    print("test_rig_at_rest.py: freeing the point cache and resetting to frame_start...", flush=True)
    prev_gravity = bl_rig.prepare_for_rest_test(bpy.context)

    threshold = core_rig.EXPLOSION_THRESHOLD_FRACTION * car_length
    print(
        f"test_rig_at_rest.py: threshold = {core_rig.EXPLOSION_THRESHOLD_FRACTION:.0%} of "
        f"car_length ({car_length:.4f}) = {threshold:.4f}",
        flush=True,
    )

    try:
        before = bl_rig.gather_positions(tracked_objects_by_name)

        bl_rig.step_frames(bpy.context, ASSERT_FRAMES)
        after_assert = bl_rig.gather_positions(tracked_objects_by_name)
        worst_name_3, worst_mag_3 = _print_displacement_table(
            before, after_assert, chassis_name, roles, simulated_names, forward_axis, lateral_axis, threshold,
            header=f"--- {ASSERT_FRAMES}-frame rest test (gravity=0, ASSERTED against threshold) ---",
        )
        passed = worst_mag_3 <= threshold

        remaining = DRIFT_REPORT_FRAMES - ASSERT_FRAMES
        bl_rig.step_frames(bpy.context, remaining)
        after_drift = bl_rig.gather_positions(tracked_objects_by_name)
        worst_name_30, worst_mag_30 = _print_displacement_table(
            before, after_drift, chassis_name, roles, simulated_names, forward_axis, lateral_axis, threshold,
            header=f"--- {DRIFT_REPORT_FRAMES}-frame drift report (gravity=0, NOT asserted) ---",
        )
    finally:
        scene.frame_set(scene.frame_start)
        bl_rig.restore_after_rest_test(scene, prev_gravity)

    # SIMULATED count here does NOT include the chassis (it's the
    # reference every displacement is measured against, never a row that
    # could itself pass/fail) -- reported separately for an honest count
    # of how many parts this run actually exercised, not "13/13" when 4
    # of those 13 were passengers that cannot fail no matter what.
    simulated_tested = len(rigid_names) - 1
    print(
        f"\ntest_rig_at_rest.py: {ASSERT_FRAMES}-frame worst displacement = {worst_mag_3:.4f} "
        f"({worst_name_3}), threshold = {threshold:.4f}",
        flush=True,
    )
    print(
        f"test_rig_at_rest.py: {DRIFT_REPORT_FRAMES}-frame worst displacement (not asserted) = "
        f"{worst_mag_30:.4f} ({worst_name_30})",
        flush=True,
    )
    print(
        f"\ntest_rig_at_rest.py: RESULT = {'PASS' if passed else 'FAIL'} "
        f"({simulated_tested} SIMULATED part(s) exercised, {len(parented)} PARENTED part(s) "
        f"along for the ride, not tested)",
        flush=True,
    )
    if not passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
