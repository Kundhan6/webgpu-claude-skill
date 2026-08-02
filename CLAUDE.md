# CLAUDE.md — Crash Forge v2

Briefing for the next session, which starts with zero context. This repo
is otherwise an unrelated `webgpu-claude-skill` project — everything
below is scoped to `crash_forge/`.

**Read `crash_forge/SPEC.md` before writing any code.** It's the
authoritative brief (copied into the repo so a zero-context session can
find it — it originally lived outside the repo, in a chat upload that
won't exist next time). Where this file and the spec disagree, the spec
wins; if you think the spec is wrong, say so before deviating.

Anything derivable by reading the repo is deliberately left out below —
this is pitfalls and rationale, not a tour.

## Status

M0–M4 complete. **M4.5 (`core/classify.py` fixes) is done — classification
is now clean on the real car, M5 is unblocked.** All 13/13 real-car parts
classify correctly (the `Roof light bar_0` miss from the previous round
is fixed — see "M4.5" below); `core/classify.py`'s only other confirmed
uncoupled-`forward_sign` bug (`DOOR_L`/`DOOR_R`) is fixed too, pre-emptively,
without waiting for a real car with doors to exist. **M5 (Stage 2 Rig +
the V8 explosion test) has not started this session — stop and report
after it per §14, don't cascade further**, but nothing is blocking it
from starting next session. One M5-relevant rigging requirement was
surfaced but deliberately not acted on — see "M5 rigging requirement,
noted not built" below.

CF_Prep has been run **end to end** against a real car (a Sketchfab
"Crown Victoria police car" .glb — Blender 5.1.2, Windows) and every
mechanical piece of it — extraction, V1/V2/V3/V5/V21, snapshot, geometry
cleanup, origin placement, the dump_car.py-schema JSON write, idempotency,
and CF_Reset — is confirmed correct on real geometry, not just synthetic
fixtures (see "Real-car verification" below for the full step-by-step
results). `core/validate.py`'s exact hard-stop messages for V1, V2, and
V21 were seen verbatim in a real Blender console and match what the code
produces. Classification accuracy on that same run started out poor
(wheels swapped, calipers read as doors, light-bar read as glass) — all
of that is now fixed (see "M4.5" below).

Test command:

    cd crash_forge && python3 -m pytest tests/ -v

175/175 passing as of the last session — no xfails; the one from the
previous round (`Roof light bar_0`) got fixed and its `strict=True`
marker caught the fix working, forcing the marker to be removed rather
than silently going green. Tier A + Tier B only — no Blender needed to
run this at all.

## M4.5 — classify.py real-car fixes (this session)

Scoped explicitly as "not M5" — Rig stays blocked on role accuracy, but
this pass is about `core/classify.py`, not Stage 2. Ran in two rounds:
round 1 (sign-coupling fix + visibility/override) shipped without real
data, per the reviewer's explicit instruction that it didn't need any;
round 2 landed once `crash_forge_car_dump.json` (13-part real geometry)
arrived and became `tests/fixtures/real_car.json`.

**1. Fixed — the diagonal wheel-swap, root cause confirmed by hand-trace,
not guessed.** `_assign_wheel_roles()` multiplied `rel_forward` by
`forward_sign` but left `rel_lateral`'s sign as a fixed,
`forward_sign`-independent "positive = right" convention. Physically,
"right" only means anything relative to which way the car is facing
(right = forward × up; negate forward and right negates with it) — the
uncoupled convention is only correct when `forward_sign` happens to be
+1, which every synthetic fixture in this project is by construction, so
nothing here ever exercised the negative-sign path before. On a real car
whose resolved sign is -1, front/back *and* left/right both flip at
once — the diagonal swap. Fix: multiply `rel_lateral` by `forward_sign`
too, the same treatment `rel_forward` already got. Provably a no-op for
every forward_sign=+1 fixture (×1 changes nothing); confirmed by
reverting the one-line fix and watching `tests/test_forward_sign.py` fail
in both directions.

**Scope note, found while building the regression test, not predicted by
the fix itself:** this coupling uses the *same baseline* "positive
lateral = right" convention the code already had for forward_sign=+1 —
it does **not** derive "right" from a literal `forward × up` cross
product for both possible forward axes (X or Y). Doing that would flip
the meaning of "right" for every existing X-forward fixture (verified by
hand — it's not a hunch), which is forbidden. A rotated version of the
X-forward sedan fixture (same physical car, described with Y as forward)
is therefore *not* guaranteed to reproduce the same left/right labels
under this fix — that case isn't asserted anywhere. Only two things are
guaranteed and tested: every forward_sign=+1 fixture is untouched, and a
car whose forward_sign is correctly known to be -1 (via override or a
non-degenerate auto-detect) classifies self-consistently, no diagonal
swap.

**2. Found while building the fix — the glass-based sign heuristic is
structurally degenerate, not just occasionally wrong.**
`detect_forward_sign()` averages every glass part's forward position.
Almost any real car (and every synthetic fixture here) has glass at
*both* ends — windshield and rear window — roughly symmetric about the
car's centre. The average is a near-exact tie against `whole_center`,
and `sign` only resolves via the `>=` comparison's tie-break defaulting
to +1 — not because the signal said anything. Every synthetic fixture
happens to be built nose-first along +forward, so the tie-break has
always silently agreed with the truth; it would agree just as often with
a car facing the other way. Locked in as
`tests/test_forward_sign.py::test_glass_at_both_ends_gives_a_mathematically_tied_forward_sign_signal`.
This is exactly why the spec's "print it, add an override" instruction
(not "tune the heuristic harder") was the right call — confirmed, not
just followed on faith.

**3. Landed — visibility + override (§12.3 step 5).** `classify()` takes
an optional `forward_sign_override`; `core/classify.py` exposes
`resolve_forward_sign(parts, forward_axis, override=None)` as the single
source of truth callable *before* `classify()` runs, so a caller can
report the resolved direction and never diverge from what `classify()`
actually used. `ops/prep.py` now: resolves the direction before
classifying, reports `"CF_Prep: ... (forward = -Y (auto))"` in the
summary line (exact format), adds a separate WARNING when the direction
was auto-detected (not overridden) pointing at the new override, and
reads `scene.crash_forge.forward_sign_override` (AUTO/POSITIVE/NEGATIVE,
wired into the panel as "Forward Direction" under Car settings).

**4. Round 2 — real-car re-triage, done.** `tests/fixtures/real_car.json`
is the raw `dump_car.py`-schema geometry from the real Crown Victoria
(13 parts). Ground truth in `tests/test_real_car.py::REAL_CAR_EXPECTED_ROLES`
is Krish's hand-confirmed table, cross-checked against the raw numbers —
never relabelled by this codebase. With `forward_sign=-1` (confirmed
correct: Body extents `[2.48, 6.70, 1.74]` make Y the length axis; the
cabin — glass centroid y=+0.534, interior centroid y=+0.481 — sits well
behind the body centroid y=+0.083, consistent with a front-engine layout
where the cabin is behind the engine bay, so +Y is rear and the nose is
-Y), three more real findings landed:

- **Wheel hardware, structural, no threshold.** Confirmed on the data:
  every brake caliper's centroid sits exactly inside its own wheel's
  bbox. `_is_wheel_hardware()` — pure bbox containment, checked right
  after wheel detection (classify()'s new step 1.5) — reclassifies them
  UNKNOWN before the DOOR_L/R lateral-extreme heuristic ever sees them.
  The calipers also have `extents[0] == 0.0` exactly (27-vert degenerate
  flat discs); the containment check does no division at all, so this
  needed no new divide-by-zero guard, but `core/geometry.py`'s existing
  `roundness()`/`sizes_agree()` guards (`hi<=0`/`bigger==0`) were audited
  against this data and confirmed already sufficient.
- **Glass-fallback skip.** `_is_glass()`'s priority-3 planar/high-Z
  fallback is now skipped scene-wide the moment any part has a confirmed
  transmissive material (`_has_confirmed_glass_material()`) — confirmed
  necessary: this car's real glass (`windows glass_0`,
  max_transmission=0.9375) already matched priority 1 correctly; the
  fallback was *independently* misfiring on two opaque roof parts
  (light-bar housing, roof-light lenses, both max_transmission=0.0) only
  because they're high, thin, and planar like a windshield.
- **World-origin concern (Krish's finding 1): audited, not a live bug.**
  `whole_center` is already `union_bbox(all parts)`'s centroid — for
  this car, `(-0.436, 0.083, 1.015)`, matching the body's own offset
  almost exactly, not `(0,0,0)`. No code path in the wheel-role or
  forward-sign logic uses world origin. Locked in with a synthetic car
  translated 500 units from the origin
  (`tests/test_classify_structural.py::test_wheel_roles_unaffected_by_a_car_far_from_world_origin`)
  rather than left as an unverified claim either way.
- **Zero doors (finding 4): already valid and warning-free**, confirmed
  both by inspection (nothing in `classify()`/`ops/prep.py` requires a
  door to exist) and by the real-car test suite once the wheel-hardware
  fix stops the calipers from being the thing that *used* to produce
  doors on this car.

**5. Round 3 — the two remaining fixes, both landed, M5 unblocked.**

- **`Roof light bar_0` fixed — BOOT tightened to the rear** *extremity*,
  **not just the rear half.** §12.1 step 4 only ever said "rear half,
  high Z, broad and flat" — wide enough that a roof-mounted light bar
  sitting at fwd=0.465 (barely past dead centre) satisfied it purely by
  coincidence (high, planar, thin along the vertical axis — indistinguishable
  from a boot lid on those three tests alone). A real boot lid sits close
  to the car's rear extremity, not merely "somewhere in the rear half" —
  a shape fact, not a curve fitted to this one car.
  `core/tuning.py::CLASSIFY_BOOT_REAR_EXTREME = 0.25` ("rear quarter")
  replaces the old `fwd <= 0.5` cutoff for `BOOT` only (`HOOD` untouched —
  never had the problem, no data suggested it does). Verified numerically
  against all three synthetic fixtures before trusting it: every one's own
  `Boot` part sits at `fwd=0.2375`, comfortably inside 0.25, while the real
  light bar's `fwd=0.465` is nowhere close — confirmed by reverting the
  fix and watching the new structural test fail, then restoring it.
  `tests/test_real_car.py`'s `xfail(strict=True)` marker did exactly its
  job here: the fix made it XPASS, `strict=True` turned that into a
  failure, forcing the marker to be removed rather than silently drifting
  green. All 13/13 real-car parts now classify correctly — no residual
  miss.
- **`DOOR_L`/`DOOR_R` fixed pre-emptively — the identical uncoupled-`forward_sign`
  bug the wheel fix had, in a different function, fixed without waiting
  for a real car with doors to exist.** `_classify_remaining_part()`'s
  `lat` was the raw normalised lateral coordinate, never multiplied by
  `forward_sign` the way `fwd` already was — mechanically identical to
  the wheel bug, and root-caused the same way (right only means anything
  relative to which way the car faces). This car has no separate door
  meshes to catch it on, so it's tested synthetically instead: the sedan
  fixture already has doors; forcing `forward_sign_override=-1` on it
  exercises the exact code path a real car with a wrong-signed forward
  guess would hit. Confirmed both a no-op at `forward_sign=+1` (every
  existing fixture, unchanged) and a clean, self-consistent swap of both
  sides together at `forward_sign=-1` (not one side flipping independently
  of the other, which would be the bug) — verified by reverting the fix
  and watching that exact test fail. Matters for M5: doors get hinges:
  a left/right swap would put the hinge on the wrong edge.

**Secondary, not acted on:** `detect_wheels()`'s roundness scoring gives
the real wheels ~1.0 and the (nearly-square-cross-section) brake
calipers ~0.992 — both clear the `CLASSIFY_WHEEL_SCORE_FLOOR` and would
both be "plausible" wheel candidates; the wheels still win by score on
this car (correctly, confirmed), but the margin is close enough to be
worth knowing about if a future car's caliper shape tips the other way.

## M5 rigging requirement, noted not built

**Wheel hardware must follow its parent wheel, not the body, once M5
rigs it.** `classify()` maps brake calipers/rotors to `UNKNOWN`, and
`UNKNOWN`'s documented treatment is "kept rigid and welded to the body"
(§12.1 step 4) — correct for classification (there's no dedicated role
for wheel hardware) but **not** the same thing as correct *rig* behaviour.
If a wheel detaches on impact (§9's breakable panel constraints) and its
caliper is welded to the chassis instead of parented to that wheel, the
caliper stays behind, floating in mid-air where the wheel used to be,
while the wheel itself flies off without it. M5 needs to either give
wheel-hardware parts their own rig treatment (rigidly attached to their
*wheel*, not the body) or otherwise special-case them — `cf_role=UNKNOWN`
alone doesn't carry enough information to do this automatically; M5 may
need `_is_wheel_hardware()`'s bbox-containment result (or an equivalent
check) surfaced as its own signal, not folded into `UNKNOWN` indistinguishably
from every other catch-all part. Flagged now, per the reviewer's explicit
instruction, rather than acted on — this is M5 scope, not M4.5's.

### Real-car verification (this session)

First-ever Blender run of CF_Prep, against a real downloaded car
(Sketchfab Crown Victoria police car, glTF, 13 parts, single-rooted
hierarchy — no manual regrouping needed). Ran in two passes: the first
hit a crash at step 5 and stopped there; the fix landed, then the full
pass (steps 4–12) re-ran clean start to finish. Full results:

| Step | Result |
|---|---|
| 4 — `tools/dump_car.py` | PASS — wrote all 13 parts |
| 5 — `CF_Prep` | PASS (after the fix below — crashed before it) |
| 6 — diff `dump_car.py` vs Prep's own dump | PASS — 0 diffs across all 13 parts |
| 7 — `cf_role` sanity | ran clean, but several roles are wrong (see below) |
| 8 — `frame_end` / `original_state` | PASS — `frame_end=250`, valid JSON, 13 records |
| 9 — idempotency | PASS — `cf_uid` unchanged across a second run |
| 10 — V21 test | PASS — cancelled naming the offending object exactly, clean revert |
| 11 — V1/V2 tests | PASS — both cancel with the exact spec messages, clean revert |
| 12 — Reset | PASS — `FINISHED`, zero leftover `cf_*` props, `stage_completed` back to 0 |

- **Crash, fixed:** `bl/apply.py`'s two `bpy.ops` wrappers
  (`apply_shade_auto_smooth`, `set_origin_to_center_of_mass`) relied on
  `context.temp_override(...)` alone to make `obj` the operator's target.
  `shade_auto_smooth.poll()` checks the *real* `view_layer` active object
  underneath — the override doesn't change that — so whenever the real
  active object was a non-mesh (the car's root Empty, exactly what's
  selected after a normal "set car_object, click Prep" run), the operator
  raised `RuntimeError: poll() failed, context is incorrect` as an
  *unhandled* exception straight out of `CF_Prep.execute()`. Fixed by
  actually mutating real selection/active state before the call (matching
  the pattern `bl/probe.py`'s own auto-smooth probe already used) and
  restoring it afterward; both wrappers now catch `RuntimeError` and
  return `False` instead of raising, and `ops/prep.py` turns a `False`
  into a clean, named `{'CANCELLED'}` instead of a crash. Covered by
  `tests/test_apply_context.py` — verified those tests fail against the
  old code and pass against the fix, in both directions. **Confirmed
  fixed in the same real Blender session** — the re-run got past step 5
  and all the way through Reset.
- **Landmine, not a bug — worth knowing if you ever drive these operators
  from a script:** `bpy.ops.crashforge.prep()` does not quietly return
  `{'CANCELLED'}` on a hard stop. Blender's own `bpy.ops` wrapper raises a
  `RuntimeError` (containing the reported message) whenever a script-invoked
  operator reports at `ERROR` level, even though `execute()` itself returns
  `{'CANCELLED'}` cleanly — this is standard Blender behavior for every
  operator, not something specific to Crash Forge. Anything that drives
  `crashforge.prep`/`crashforge.reset` from Python (a test harness,
  `blender_suite.py` when it exists) needs to catch `RuntimeError`, not
  branch on the return value, to detect a hard stop.
- **Still open — real classification disagreement, deliberately not fixed
  this pass (scope decision, confirmed across both verification runs, not
  an oversight):** on this car, all four wheels came back with
  front↔back *and* left↔right swapped simultaneously (WHEEL_FL called
  WHEEL_RR, etc.) — smells like a 180°-yaw sign issue in `classify.py`'s
  `_detect_forward_sign` or `_assign_wheel_roles`, not random noise. This
  car has no distinct door meshes at all (one joined body shell) and its
  four brake-caliper meshes were misclassified as `DOOR_L`/`DOOR_R`
  instead of falling through to `UNKNOWN` — the lateral-extreme-and-planar
  heuristic in `_classify_remaining_part` matched them by coincidence. The
  roof light-bar housing was also misclassified as `GLASS` (it's opaque
  plastic, not glass) — likely `_is_glass`'s priority-3 planar/high-Z
  fallback firing on a part that happens to sit high and thin, with no
  real transmission material to override it. All three are
  `core/classify.py` questions, not `bl/` bugs — worth investigating
  before trusting classification on any real car, but deliberately left
  for a separate, explicitly-scoped pass rather than bundled into the
  crash fix.

Two fixes carried forward into this session, both landed before M4:

- `core/naming.py::nocol_name()`'s "__"-in-a-part-name check used to only
  fire during Stage 2 Rig's pair generation. Pulled forward into Prep as
  an added validation (`core/validate.py::validate_no_ambiguous_part_names`,
  reported as `V21` — not one of §11's original ten rows). `Door__L` (a
  real pattern on downloaded car models) now hard-stops at Prep, named,
  instead of blowing up deep in Rig.
- `bl/scene.py::reset_self_check()`'s rigidbody-world stale-object scan
  matched `o.name.startswith("CF_")` instead of `is_cf_generated(o)` — a
  generated object renamed after creation would've passed that check as
  "clean" while still orphaned, silently breaking V20. Fixed to match by
  identity; see `tests/test_reset_identity.py`.

## Blender version

**5.1.2 — CONFIRMED by a real Stage 0 probe run, not assumed.** The spec
names 5.2 LTS as primary; that's the target to eventually support, not
the version actually in front of you. Don't retarget anything to 5.2
specifically unless a probe on an actual 5.2 build says something
differs. Nothing in the manifest, `bl_info`, or `bl/probe.py` hardcodes
5.2 — keep it that way. `blender_probe_script.py` prints the running
version as its first line, unconditionally, before anything that could
fail; don't remove that.

## §3 non-negotiable rules (the ones that actually bite)

- **`core/` imports nothing from bpy, bmesh, or mathutils.** Enforced by
  `tests/test_no_bpy.py` (AST scan of every file, not a text grep — a
  docstring saying "no bpy" can't false-positive it). If new `core/`
  logic needs something bpy-shaped, it takes a plain dataclass instead;
  the bpy-touching side goes in `bl/`.
- **Probe, never assume.** Every bpy property/operator/enum this add-on
  depends on is verified at runtime by `bl/probe.py`, not trusted from
  memory or docs — including things that seem obviously stable. Adding a
  stage that touches a new API surface means adding a probe row for it
  first, in `PROBE_ROWS`, and wiring `_mark_row()` for both its success
  and failure paths (`tests/test_probe_complete.py` fails immediately on
  a row that never marks itself).
- **No `bpy.ops` where a data-API call exists.** Operators depend on
  context and are the fragile, hard-to-test path. Where unavoidable, wrap
  in `context.temp_override(...)` and check the returned status set.
- **Fail loud, fail early.** A stage that can't guarantee a correct
  result reports and stops — never a half-built rig, never a silent
  guess. `core/report.py`'s `StageResult` (`.error()`/`.warn()`/`.info()`)
  is the shared vocabulary; use it, don't invent a parallel one.

## The working loop

- **You build. You never run Blender.** There is no Blender in this
  sandbox, and nothing in `core/` is even importable if it accidentally
  needs bpy — that's what test_no_bpy.py guarantees.
- **Krish runs Blender** (5.1.2, Windows) and pastes results back —
  `run_probe.bat` output, tracebacks, whatever a Tier C step produces.
  Don't fabricate what a probe or test *would* say; wait for the real
  paste, and say plainly if a message claims to include one but it didn't
  actually come through.
- **A reviewer chat writes your prompts.** It has read the real probe
  output and holds you to specifics — expect numbered follow-up lists,
  not vague feedback. Answer the exact items asked, confirm-or-fix each
  one explicitly, and don't silently reinterpret an ask.
- **One or two milestones per session, then stop and report.** Don't
  cascade into the next milestone unprompted, even when the next step
  looks obvious.

## Landmines

- **Auto-smooth GN socket identifiers are inconsistently named**
  (`Input_0`, `Input_1`, `Socket_1`, ...) across builds *and* node
  groups — never hardcode one. Resolve by socket **name** (e.g. "Angle")
  through `node_group.interface.items_tree` first, then use whatever
  identifier that lookup returns. Reuse
  `bl/probe.py::resolve_gn_input_identifier_by_name()` — don't
  reimplement it. Geometry-type sockets are confirmed *not* readable via
  `mod[identifier]` at all; don't attempt them.
- **Old Crash Forge installs must be removed from Blender Preferences
  before testing anything new.** If a stale copy is enabled, Blender's
  extension system imports it at startup and that import sits in
  `sys.modules` — a second copy reached via `sys.path` (e.g. by
  `blender_probe_script.py`) gets shadowed by the stale one and fails in
  confusing ways. This already broke an import once ("No module named
  `crash_forge.bl`" while `crash_forge` itself resolved fine — the
  installed copy was missing `bl/`). `blender_probe_script.py` now purges
  `sys.modules` before importing as a guard, but the clean fix is:
  disable/remove any installed Crash Forge extension first, and it
  prints the resolved `__file__` paths so you can see which copy actually
  loaded.
- Don't assume Blender preserves the shell's cwd for `--python <relative
  path>`. Any new standalone script should resolve its own paths via
  `os.path.abspath(__file__)`, never a bare relative path or `os.getcwd()`.

## Tuned-not-verified constants — `core/tuning.py`

Every threshold invented (not given by the spec) to make
`classify.py`/`impact.py`/`density.py`/`pairs.py` behave correctly lives
in **`core/tuning.py`**, one file, each commented with what it affects.
When `tools/dump_car.py`'s output on a real car disagrees with these,
retune there — one file, not a hunt through four modules:

- `CLASSIFY_LOW_Z`, `CLASSIFY_HIGH_Z`, `CLASSIFY_FORWARD_EXTREME`,
  `CLASSIFY_LATERAL_EXTREME`, `CLASSIFY_WHEEL_SCORE_FLOOR`,
  `CLASSIFY_GLASS_FALLBACK_HIGH_Z`, `CLASSIFY_BOOT_REAR_EXTREME`
- `IMPACT_SPIKE_FACTOR`, `IMPACT_EPSILON_FACTOR`, `IMPACT_MIN_MAX_SPEED`
- `DENSITY_ASSUMED_VERTS_PER_VOXEL_AREA`
- `PAIRS_DEFAULT_MARGIN_FRACTION`

Constants that *are* spec-given (§12.2's 15% wheel-size tolerance, §11
V11's 5-frame boundary, §12.5's ~200k-vert ceiling, §8.5's 0.5×max_speed
threshold) deliberately stay local to their own module, not here —
retuning those means the spec changed, not that a real car disagreed
with a guess.

`core/validate.py` (M4, new) has zero invented constants — its V1/V2/V3/V5
thresholds (unit scale 1.0, frame_end ≥ 250, part count 4–25) are all
exact values §11's own table gives, not tuned guesses, so none of them
belong in tuning.py either.

**One threshold sits outside this whole system and should probably move
into it eventually:** `bl/extract.py::PLANAR_THIN_RATIO` (0.15) is a
direct copy of `tools/dump_car.py`'s own `PLANAR_THIN_RATIO` — duplicated
on purpose, since dump_car.py must stay a standalone script that never
imports `crash_forge`. It's tuned-not-verified by the same definition as
everything above, just not tracked in tuning.py because it lives in `bl/`
(which imports bpy) rather than `core/`. If a real car disagrees with it,
change both copies together.

## Getting a real fixture

`crash_forge/tools/dump_car.py` — standalone, imports nothing from
`crash_forge` and nothing imports it. Run inside Blender against a real
car (Scripting tab, select the hierarchy, Run Script). Dumps raw
PartDescriptor JSON — bbox, centroid, extents, vert count, materials,
transmission, planarity — and assigns zero part roles. Krish labels roles
by hand from that JSON; don't do it for him.
