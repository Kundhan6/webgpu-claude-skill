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

M0–M4 complete. M4.5 (this session — `core/classify.py` fixes, not M5)
is **partially done**: the diagonal wheel-swap bug is fixed and the
forward-direction visibility/override landed. **The real-car re-triage
(§ "M4.5" step 4 below) has not run** — it needs `tests/fixtures/real_car.json`
(real geometry + Krish's hand-labelled ground truth), which had not
arrived as of this session ending. M5 (Stage 2 Rig + the V8 explosion
test) has not started — stop and report after it per §14, don't cascade
further.

CF_Prep has been run **end to end** against a real car (a Sketchfab
"Crown Victoria police car" .glb — Blender 5.1.2, Windows) and every
mechanical piece of it — extraction, V1/V2/V3/V5/V21, snapshot, geometry
cleanup, origin placement, the dump_car.py-schema JSON write, idempotency,
and CF_Reset — is confirmed correct on real geometry, not just synthetic
fixtures (see "Real-car verification" below for the full step-by-step
results). `core/validate.py`'s exact hard-stop messages for V1, V2, and
V21 were seen verbatim in a real Blender console and match what the code
produces. Classification accuracy on that same run was poor (wheels
swapped, calipers read as doors, light-bar read as glass) — the wheel-
swap root cause is now fixed (see "M4.5" below); the rest is unverified
against real geometry until the dump arrives.

Test command:

    cd crash_forge && python3 -m pytest tests/ -v

147/147 passing as of the last session. Tier A + Tier B only — no
Blender needed to run this at all.

## M4.5 — classify.py forward-direction fix (this session)

Scoped explicitly as "not M5" — Rig stays blocked on role accuracy, but
this pass is about `core/classify.py`, not Stage 2. Two things landed;
one (real-car re-triage) is blocked on data.

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

**4. Blocked — real-car re-triage.** Needs `tests/fixtures/real_car.json`
(real geometry from `crash_forge_car_dump.json` + Krish's hand-labelled
ground truth — never fabricate this, ask for it). Once it arrives: re-run
classification, report per-part role diffs before/after this fix, and
only then triage what's still wrong (the brake-caliper-as-door and
light-bar-as-glass misclassifications are suspected downstream of the
wheel-position confusion, not yet confirmed).

**Also found, not fixed — same class of bug, different function:**
`_classify_remaining_part()`'s `DOOR_L`/`DOOR_R` split
(`PartRole.DOOR_R if lat >= 0.5 else PartRole.DOOR_L`) uses the raw
normalised lateral coordinate with no `forward_sign` coupling at all —
the identical uncoupled-convention shape as the wheel bug, just never
symptomatic yet because it's also only ever been exercised at
forward_sign=+1. Not touched this pass (step 4's "report what's still
wrong before fixing anything else" — this needs the real-car re-triage
first, since the door misclassification on the real car looks more like
"calipers hitting the DOOR fallback by coincidence" than a sign issue,
per the earlier verification report).

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
  `CLASSIFY_GLASS_FALLBACK_HIGH_Z`
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
