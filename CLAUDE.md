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

M0–M5 complete. **M5 (Stage 2 Rig + the V8 3-frame explosion test) is
done this session — stop and report per §14, don't start M6.** See
"M5 — Stage 2 Rig" below for what was built, the scope decisions made
(barrier handling, wheel-hardware parenting, motor target velocity), and
the exact Blender steps to verify it. Three corrections landed on top of
the first draft this session, all from real gaps the reviewer/Krish
caught, not hypothetical ones: "M5 correction: real 3-frame explosion
test as a committed Blender script" (gravity/cache/frame-reset flaw in
the rest test), "M5 correction: structural connectivity + honest
SIMULATED/PARENTED reporting" (the rest test's blind spot to an entirely
unattached part — which, while building it, also caught a real,
previously-unnoticed bug: glass panels had a rigid body but no
constraint attaching them to anything at all), and "M5 — first real
Blender run: two fixes" (the Stage 0 probe silently validating nothing
at registration, and `sys.exit(1)` in the standalone script breaking
under Krish's harness).

Also this session, before M5: `core/tuning.py::CLASSIFY_BOOT_REAR_EXTREME`
moved from 0.25 to 0.35 — see "CLASSIFY_BOOT_REAR_EXTREME: 0.25 -> 0.35"
below.

M0–M4.5 status (classification, verified against a real car) is unchanged
from last session — see "M4.5" below, kept as-is.

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

210/210 passing as of this session (175 carried forward from before this
session's own baseline check + 28 in `tests/test_rig.py` + 3 in
`test_wheels.py` for `find_wheel_hardware_parents` + 4 in
`tests/test_probe_lazy.py`) — no xfails. Tier A + Tier B only — no
Blender needed to run this at all. `tests/blender/` holds Tier C scripts
(real bpy, real Blender only) and is excluded from this count by
`pytest.ini`'s `norecursedirs = blender` on purpose.

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

## M5 rigging requirement — flagged last session, built this session

**Wheel hardware must follow its parent wheel, not the body, once M5
rigs it.** `classify()` maps brake calipers/rotors to `UNKNOWN`, and
`UNKNOWN`'s documented treatment is "kept rigid and welded to the body"
(§12.1 step 4) — correct for classification (there's no dedicated role
for wheel hardware) but **not** the same thing as correct *rig* behaviour.
If a wheel detaches on impact (§9's breakable panel constraints) and its
caliper is welded to the chassis instead of parented to that wheel, the
caliper stays behind, floating in mid-air where the wheel used to be,
while the wheel itself flies off without it. Flagged, not acted on, at
the end of the M4.5 session — this was M5 scope, not M4.5's.

**Built this session:** `core/classify.py::find_wheel_hardware_parents()`
(new, public — a refactor of the existing `_is_wheel_hardware()` bbox
containment test that now also reports *which* wheel each hardware part
belongs to, not just that it's hardware). `core/rig.py::build_rig_plan()`
uses it to route every hardware part to `wheel_hardware_parent[name] =
<wheel name>`; `bl/rig.py::apply_rig_plan()` parents each one directly to
its own wheel object. See "M5 — Stage 2 Rig" below for the rest.

## CLASSIFY_BOOT_REAR_EXTREME: 0.25 -> 0.35 (this session, before M5)

The reviewer's read: 0.25 sat at the edge of the true class (every
synthetic fixture's own Boot part is at fwd=0.2375 — a 0.0125 margin)
instead of the middle of the gap between the two known data points
(Boot at 0.2375, the real light bar at 0.465). Moved to 0.35 — close to
the true midpoint (≈0.351) — and confirmed both sides still hold:
`tests/test_classify_structural.py`'s two BOOT tests and
`tests/test_real_car.py`'s `Roof light bar_0`/`roof lights_0` cases all
still pass at the new threshold. `core/tuning.py`'s comment was rewritten
in the same pass to note explicitly that sedan/suv/van/badly_named all
place Boot at the *same* fraction of `hl_body`
(`car_fixture_builder.py::make_car`), so the fwd=0.2375 data point is one
scale-invariant confirmation, not three or four independent ones — the
previous comment's "verified against all three synthetic fixtures" read
as more independent evidence than it actually was.

## M5 — Stage 2 Rig (this session)

Built `core/rig.py` (pure planning, no bpy — `build_rig_plan()`,
`check_connectivity()`, `check_explosion()`), `bl/rig.py` (the bpy
execution layer), and `ops/rig.py` (`crashforge.rig`), wired into
`__init__.py` and the panel. 210/210 total, still Tier A + Tier B only
(counts and section numbers below are from the *final* state of this
session, after all three corrections — see the "M5 correction" sections
and "M5 — first real Blender run" below). **Krish's first real Blender
run against this build surfaced two real bugs, both fixed — see "M5 —
first real Blender run: two fixes" below.** Krish also hit a separate
V2 hard-stop on that same run (non-uniform/unapplied scale on the real
car) — expected §11 behaviour, not a bug, nothing to fix here — which
means CF_Prep did not reach completion on that run either, so the
actual rig-building logic (rigid bodies, constraints, the rest test
itself) still has not been exercised end to end in real Blender. See
"Blender verification steps for M5" at the end of this file for exactly
what to run next.

**§9's constraint graph, built correctly from the start rather than
fixed up after the fact:** every `ACTIVE` rigid body always gets
`CONVEX_HULL` (V6 never needs to auto-fix anything Rig itself built);
every overlapping rigid-part pair always gets a `CF_NoCol_` constraint
(V7, via `core/pairs.py::generate_pairs()` — already spec-compliant,
unchanged); 4 hinges (all wheels) + 2 motors (rear wheels only, §9.2's
"two motors rather than four") per car; one breakable `FIXED` constraint
per door/hood/boot/bumper, `breaking_threshold` from §12.6's formula
using `scene.crash_forge.speed_kmh`/`panel_toughness` (already-known user
inputs, available at Rig time — no need to wait for Drive).

**Three scope decisions, made explicitly rather than guessed at:**

1. **Wheel motor target velocity is left at 0.0.** §9.2's table and
   §8.4 CF_Drive step 3 both describe setting it from `speed_kmh` and
   wheel radius, but Drive is not built (M6+) and doesn't need to be for
   M5's rest test — 0.0 is the physically correct value for a car at
   rest, and it's Drive's job to overwrite it later.
2. **`CF_Barrier` auto-creation is out of scope.** §8.2 step 1 lists a
   barrier rigid body among what Rig sets up, but §8.4 CF_Drive step 2
   is explicitly where `CF_Barrier` gets created if the user supplied no
   `target_object`. Rig rigs a `target_object` if one already exists
   (`PASSIVE`, `MESH`, + a Collision modifier per §9.5), but builds a
   car-only rig if not — which is exactly what a rest test needs: nothing
   is driving into anything.
3. **Two kinds of part get parented, not rigid-bodied, to stay inside
   "12–20 rigid parts, never more" (§3 rule 7) without literally joining
   meshes** (Surface Deform in a later stage needs every original piece
   separate, §2.2 step 6): wheel hardware parents to its own wheel;
   every other `UNKNOWN`/uncategorised part parents to the chassis
   ("welded to the body", §12.1 step 4). This is plain
   `obj.parent = ...`, never a rigid body `FIXED` constraint — §8.2's
   "No part welding" refers specifically to v1's broken FIXED-constraint
   weld (§1.1/§1.2), a different mechanism entirely. One consequence
   worth knowing: `CF_Reset` already restores every part's original
   parent from `original_state` (CF_Prep's snapshot, unconditionally, on
   every Reset run) — so undoing Rig's parenting needed **zero** changes
   to `bl/scene.py` or `ops/reset.py`. Confirmed by reading the existing
   Reset code path, not assumed.

**Stage 0 probe: nothing new added.** Every bpy surface `core/rig.py`'s
plan is executed against — `rigidbody.object_add`, `rigidbody.constraint_add`,
`RigidBodyConstraint.type/props`, `motor_properties`,
`RigidBodyObject.collision_shape`, `scene.rigidbody_world` — is already
in `PROBE_ROWS` and confirmed (see "Facts already confirmed" in this
session's task). Two things `bl/rig.py` relies on are genuinely
unconfirmed and **not** added as new probe rows, on purpose — they're
either out of §6's table's explicit scope or too basic/stable a
property to be worth gating a whole stage on, the same status as
`obj.scale`/`obj.parent`/`obj.matrix_world`, which Prep already uses
unprobed:
- `RigidBodyObject.type` (`ACTIVE`/`PASSIVE`) and `.mass` — not in §6's
  RigidBodyObject row (only `collision_shape` is), and unchanged, stable
  API since Blender 2.67.
- `bpy.ops.rigidbody.constraint_add`'s poll-by-type — confirmed to
  *exist* (already probed), but whether `EMPTY` specifically passes its
  poll was never tested the way `object_add`'s MESH-only restriction
  was. Standard Blender workflow uses Empties for constraints; if this
  is wrong, expect a poll() RuntimeError on the very first hinge/motor/
  break/no-collide constraint Krish's Tier C run tries to create — loud
  and immediate, not silent.
If Krish's Blender run below turns up a real gap here, add the probe row
before touching `bl/rig.py` again, per §3's non-negotiable rules.

**The 3-frame explosion test (§8.2 step 5 / V8), the actual point of
this milestone:** `ops/rig.py` samples every rigid part's world position
right after building the rig, steps the scene 3 frames with nothing
driving it (`bl/rig.py::step_frames()`), samples again, restores the
original frame, then calls `core/rig.py::check_explosion()` — pure,
Tier-A-tested comparison logic. It measures each non-chassis part's
displacement **relative to the chassis** (so a chassis settling slightly
under gravity doesn't itself count against every other part) against
5% of the car's own length (§8.2 step 5's literal number, scale-relative
like `core/pairs.py`'s own margin, named `core/rig.py::EXPLOSION_THRESHOLD_FRACTION`
rather than a magic number). A failure names the single worst offending
part, then `ops/rig.py` tears the whole rig back down — reusing
`bl/scene.py`'s existing Reset helpers (`remove_cf_generated_objects` +
`purge_orphaned_constraint_empties`) rather than a second cleanup path —
before returning `{'CANCELLED'}`. Never a half-built rig left in the
scene (§3 rule 10).

**Mid-session correction, both parts acted on:** the first draft above
asserted with whatever `scene.gravity` and point-cache state happened to
be live at that moment. Two real problems with that, caught before any
Blender run: (1) Stage 2 has no ground plane yet (that's Stage 3
CF_Drive's job) — with real gravity on, the whole ungrounded car
free-falls from frame 1, an expected effect with nothing to do with
whether the rig itself is sound, and it would either false-fail a good
rig or mask a real explosion underneath an unrelated drop; (2) a stale
point cache (this scene's own earlier Rig attempt, or a leftover bake
from outside Crash Forge entirely) would replay old keyframed motion
instead of re-simulating anything — a false pass. Fixed in both places
that step frames: `bl/rig.py::prepare_for_rest_test()` (new — zeroes
`scene.gravity`, calls the existing `bl_scene.free_all_point_caches()`,
resets to `frame_start`, all restored afterward) is now called both by
`ops/rig.py`'s embedded check above and by the new standalone script
below.

**`tests/blender/test_rig_at_rest.py` (new) is the actual, authoritative
version of this test** — real physics can only be validated in real
Blender, which this build session never has, so writing this as a
pytest that mocks bpy positions would prove nothing and would read as
proof where there is none. Committed, not improvised, so Krish runs the
exact same script every time and results are comparable run to run and
car to car. It runs Reset -> Prep -> Rig itself, fresh, every run, then:
zeroes gravity, frees the cache, resets to `frame_start`; steps 3 frames
and **asserts** against `EXPLOSION_THRESHOLD_FRACTION * car_length`
(imported from `core/rig.py`, never re-typed); steps to 30 frames total
and **reports only** the worst displacement, not asserted — 3 frames
catches a sudden explosion, 30 catches slow drift a 3-frame window is
too short to see. Prints a full per-part displacement table (both
windows) and one `RESULT = PASS`/`RESULT = FAIL` line at the end.
`pytest.ini` gained `norecursedirs = blender` so this file (named
`test_*.py` on purpose, for consistency at the call site — "run
`test_rig_at_rest.py`") never gets collected by the Tier A/B suite,
which would otherwise crash immediately on its unconditional `import
bpy`.

No hardcoded axis or assumed world origin anywhere in the script:
forward axis/sign come from `core.classify.detect_forward_axis()`/
`resolve_forward_sign()` run fresh against the live car's real geometry,
and "the car's centre" (printed once, for reference only — every
displacement is relative to the chassis, never to this) is
`core.geometry.union_bbox()`'s centroid, never `(0, 0, 0)`. This matters
concretely, not just in principle: the real car this build has already
been verified against has forward = -Y and a union-bbox centre at
x = -0.44 — a script that assumed forward = +X or centre = world origin
would mislabel every column in its own printed table on exactly this
car.

**Degenerate wheel-hardware colliders — confirmed by code inspection,
not assumed:** this car's 4 brake discs are `extents[0] == 0.0` exactly,
27 verts each. A `CONVEX_HULL` of a zero-thickness disc is a degenerate,
near-zero-volume hull — a bad rigid body, unstable in Bullet. They get
**no collider and no rigid body at all.** `classify.py` step 1.5 already
routes any part whose centroid falls inside a wheel's bbox to `UNKNOWN`
(this is exactly what a brake disc/caliper is); `build_rig_plan()`'s
`unknown_names` computation only ever adds `chassis`/wheels/breakable
panels/glass to `rigid_names` — a disc is none of those, so it never
gets a `RigidBodySpec`, and `apply_rig_plan()`'s rigid-body loop never
touches it. Instead it's in `plan.wheel_hardware_parent`, and
`bl/rig.py::parent_to()` makes it a plain child object of its own
wheel — no `bpy.ops.rigidbody.object_add()` call, no collision shape,
no participation in the Bullet simulation at all. It moves purely by
inheriting its parent's transform every frame, the same as any other
Blender parent/child relationship. Traced through the actual code path
end to end this session, not inferred from the design description.

**M5 correction, second round, this session: structural connectivity +
honest SIMULATED/PARENTED reporting.** The rest test (gravity=0, nothing
driving) has a real blind spot: it can only catch a part the solver
actively shoves. A wheel with no hinge to the chassis sits perfectly
still in zero gravity and passes cleanly — a PASS there means "nothing
shoves parts apart," not "the car is one car." Fixed with a separate,
pure-data check, not a physics one:

- `core/rig.py::check_connectivity()` (new) builds a graph — nodes are
  every part CF_Prep classified, edges are every hinge/motor/break
  constraint plus every parent link Rig creates (`weld_to_chassis`,
  `wheel_hardware_parent`) — and asserts a single connected component.
  `core/rig.py::build_connectivity_edges()` deliberately excludes
  no-collide (`plan.nocols`) constraints: §9.4 is explicit that one
  "must hold nothing" (`enabled=False`), so counting it as structural
  would reopen the exact blind spot this check exists to close.
  `build_rig_plan()` calls this itself and raises `RigPlanError`,
  naming every isolated part, before Rig ever touches a single bpy
  object — the check runs identically in Tier A (`tests/test_rig.py`,
  8 new tests, both directions: drop a hinge and watch the right test
  fail, restore it and watch it pass) and inside the real Blender
  script, since it's the same pure function either way.
- **Caught a real bug while building this, not a hypothetical one:**
  glass panels get a rigid body (§8.2 step 1) but §9's table names no
  constraint that attaches them to anything at all — every glass panel
  was its own disconnected island. Fixed: `core/rig.py::BreakSpec`
  gained a `breakable: bool` field; glass now gets the same FIXED
  chassis<->panel attachment every breakable panel gets
  (`core/rig.py::build_rig_plan()`), just with `breakable=False` —
  `bl/rig.py::add_break()` only sets `use_breaking`/`breaking_threshold`
  when `spec.breakable` is true, so glass is held in place but never
  detaches as a whole panel through this mechanism (it shatters later,
  via §8.8 CF_Glass_Sim's separate mesh-level Quick Explode, not built
  yet). `tests/test_rig.py::test_glass_gets_its_own_rigid_body_and_a_non_breakable_attachment`
  locks this in; the real 13-part car (`tests/fixtures/real_car.json`)
  confirmed via direct code run this session: its one GLASS part
  (`windows glass_0`) gets exactly this treatment, and the whole car
  passes `check_connectivity()` end to end.
- The barrier is the one legitimate exception — named and explained,
  not excused by loosening the assert (per the reviewer's explicit
  instruction not to). It's excluded from `check_connectivity()`'s node
  set because it was never one of the car's own classified parts to
  begin with (`roles.keys()` never includes it) — it's the external
  wall the car collides with, meant to be disconnected from the car.
  `tests/test_rig.py::test_barrier_is_excluded_from_connectivity_not_required_to_connect`
  checks both halves: `build_rig_plan()` doesn't raise even though
  nothing attaches the barrier to anything, and the barrier never
  appears in `isolated_parts`.
- **`tests/blender/test_rig_at_rest.py`'s table now marks every row
  SIMULATED or PARENTED**, and its `RESULT` line reports both counts.
  A PARENTED part (no rigid body — wheel hardware, or any other
  UNKNOWN part welded to the chassis) inherits its parent's transform
  exactly and cannot independently fail no matter what the sim does;
  before this fix, this car's 4 degenerate brake discs would report a
  clean `0.000` in the same table as the 9 genuinely-simulated parts,
  reading as "13/13 verified" when only 9 parts were actually
  exercised. Only SIMULATED rows can show `OVER` or contribute to the
  worst-displacement tracking used for pass/fail; PARENTED rows print
  `n/a` and are informational only. `ops/rig.py`'s own success report
  line got the same split (`N rigid part(s) SIMULATED, M part(s)
  PARENTED`) for the same reason, plus a `connectivity: 1 component`
  line, at negligible cost, for consistency.

**Known gap, flagged not fixed: idempotency (§3 rule 4).** Rig is the
first stage that creates brand-new objects, and `ops/rig.py` does not
yet clean up a *previous* Rig run's own artifacts before building a new
one. Mitigated, not solved: `CF_OT_rig.poll()` requires
`stage_completed == 1` exactly, so clicking Rig twice in a row is
blocked (Reset is required in between). This does not close every path
— Prep resets `stage_completed` to 1 on every successful run regardless
of its previous value, and has no reason today to know Rig exists or to
clean up after it, so Prep -> Rig -> Prep -> Rig without a Reset in
between can still leave orphaned first-generation `CF_Hinge_*`/etc.
objects sitting in the scene. The real fix likely belongs in
`ops/prep.py` (invalidate/clean stage >= 2 artifacts on re-run, matching
§7.2's own wording: "Re-running stage n... invalidates everything
downstream"), not in Rig itself — noted for a future session, not acted
on now.

**Not verified in this session — genuinely can't be, no Blender here:**
whether the rig actually holds together in real Blender at all. Every
line above is code review and Tier A logic, not a real simulation run.
`tests/blender/test_rig_at_rest.py` is written to answer this, but
written blind — it has never actually executed. See the Blender
verification steps at the end of this file, which now lead with running
that script.

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

## M5 — first real Blender run: two fixes, unrelated to the V8 blocker

Krish's first actual Blender run against M5 surfaced two real bugs,
both fixed this session, both confirmed by tracing the actual failure
rather than guessed at:

**1. The Stage 0 probe silently validated nothing at registration.**
`register()` printed `'_RestrictContext' object has no attribute
'scene'` to the console and still reported success. Root cause,
confirmed against the real traceback: `bpy.context` is Blender's
restricted proxy object during `register()` — accessing `.scene` on it
*raises* `AttributeError` rather than returning `None`, and the old
`_run_stage0_probe()` wrapped the whole probe call in a bare
`try/except Exception: print(...); return`. That caught the exception,
printed it, and moved on — registration "succeeded" while the probe,
the single source of every "fact, not guess" this project depends on
(§3 rule 1), had validated *nothing at all*, silently.

Fixed by moving the probe off registration entirely — `register()` no
longer calls it, full stop. `bl/probe.py::ensure_probed()` (new) runs
it lazily instead, the first time any stage operator's `execute()`
calls it, where real, unrestricted context is guaranteed. It caches
(module-level, cleared on `unregister()` via the new
`reset_probe_cache()`) so it only actually runs once per session, and
it **never swallows anything** — an exception from `run_probe()`
propagates straight through `ensure_probed()` unchanged. Each of
`ops/prep.py`, `ops/rig.py`, and `ops/reset.py` now calls it as the
very first thing in `execute()`: a raised exception becomes a clean,
named `self.report({'ERROR'}, ...)` + `{'CANCELLED'}` (never a raw
traceback, never silent); a structurally-failed probe
(`probe_result.ok == False`) refuses to run at all, naming every
failed check, rather than proceeding on unverified API assumptions.
All three stages go through the identical gate — including Reset,
deliberately: if this Blender build's rigidbody/constraint API doesn't
match what the probe expects, Reset's own `bpy.ops.rigidbody.
object_remove()` calls are exactly as unverified as Rig's, and letting
Reset through on an unverified build just to avoid the user feeling
"stuck" would be quietly reintroducing the same silent-assumption
failure this fix exists to close.

`tests/test_probe_lazy.py` (new, 4 Tier B tests) locks this in:
`register()` genuinely never calls `run_probe()` (checked by call
count, not by whether a raised exception escapes — a raising fake
can't distinguish old from new here, since the old code caught
exceptions too; that was the bug), `ensure_probed()` propagates a
raised exception rather than swallowing it, and the cache both persists
across calls and can be forced to re-run via `reset_probe_cache()`.

**2. `tests/blender/test_rig_at_rest.py` called `sys.exit(1)` on
failure.** Works fine under a plain `blender --background --python
script.py` invocation, but Krish's local harness intercepts `sys.exit`
from LLM-run code and raises a `RuntimeError` instead — an unnamed,
generic exception instead of a real signal of what failed. Fixed:
`main()` never calls `sys.exit()` anywhere now. On any failure it
raises `RestTestFailed` (new, a plain named `RuntimeError` subclass);
on success it returns a `RestTestReport` (new, a small dataclass —
worst displacement + part name for both the 3-frame assert and the
30-frame drift window, the threshold, and the simulated/parented
counts) instead of returning nothing. Every internal early-exit path
(`_fail()`, called for a missing `car_object`, a failed Reset/Prep/Rig,
or no chassis found) raises the same way. `if __name__ == "__main__":
main()` at the bottom is unchanged in shape — it was never wrapping
anything in a `try/except SystemExit`, so nothing there needed to
change to stop relying on `sys.exit`.

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
  `CLASSIFY_GLASS_FALLBACK_HIGH_Z`, `CLASSIFY_BOOT_REAR_EXTREME` (0.35
  as of this session — see "CLASSIFY_BOOT_REAR_EXTREME: 0.25 -> 0.35" above)
- `IMPACT_SPIKE_FACTOR`, `IMPACT_EPSILON_FACTOR`, `IMPACT_MIN_MAX_SPEED`
- `DENSITY_ASSUMED_VERTS_PER_VOXEL_AREA`
- `PAIRS_DEFAULT_MARGIN_FRACTION`
- `RIG_DENSITY_BODY`, `RIG_DENSITY_PANEL`, `RIG_DENSITY_WHEEL`,
  `RIG_DENSITY_GLASS`, `RIG_MIN_MASS` (M5, this session — §8.2 step 2's
  mass derivation; entirely unverified against a real car's actual mass
  distribution, same status as everything else in this file)

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

## Blender verification steps for M5 (Krish, from scratch)

Nothing below has been run in Blender. Written assuming zero prior
context of your car — every step names exactly what to look at and what
"correct" looks like, not just "run it and see."

0. Remove any previously installed Crash Forge extension from Blender
   Preferences first (see "Landmines" above — a stale copy shadows the
   new code via `sys.modules` and produces confusing failures that have
   nothing to do with M5 itself). Install/reload this build, confirm the
   Stage 0 probe printout in the console still looks like last session's
   (no new errors — M5 added no new probe rows on purpose).
1. Open your car (the same one CF_Prep has already been verified against
   is fine, or a fresh one — CF_Prep must run clean first either way).
   Set Car in the panel, click **Prep**. Confirm it finishes `{'FINISHED'}`
   and the console/report line looks like last session's.
2. Click **Rig** (new button, between Prep and Reset). Watch the report
   line and the console:
   - **If it reports success:** it will read something like `CF_Rig: N
     rigid part(s), 4 hinge(s), 2 motor(s), M breakable panel(s), K
     no-collide pair(s) — rest test passed (worst displacement X / Y
     threshold)`. Open the Outliner: you should see new `CF_Hinge_*`,
     `CF_Motor_*`, `CF_Break_*`, `CF_NoCol_*` empties, and each rigid
     part (Body, 4 wheels, doors/hood/boot/bumpers, glass) should show a
     Rigid Body entry in its Physics properties tab (chassis/wheels/
     panels/glass = Active, `Convex Hull`; a target object if you set
     one = Passive, `Mesh`). Any brake calipers/rotors should now be
     parented (in the Outliner hierarchy) under their own wheel, not
     under Body — expand a wheel object and confirm.
   - **If it reports the 3-frame rest-test failure** (`"exploded on the
     3-frame rest test — '<part>' moved ..."`): that is real, useful
     information, not a bug report waiting to happen — paste the exact
     message and console output back. Do **not** try to work around it
     by hand; the whole point of this milestone is that this check
     catches exactly the failure mode that killed v1.
   - **If it raises a Python traceback instead of a clean report**
     (`RuntimeError`, `AttributeError`, anything not a `self.report(...)`
     line): this is the most likely real gap — paste the full traceback.
     The two most likely places, per this session's report above: (a)
     `bpy.ops.rigidbody.constraint_add`'s poll rejecting an Empty (never
     independently probed — see "M5 — Stage 2 Rig" above), or (b) the
     `RigidBodyObject.type`/`.mass` properties not existing/being named
     differently than assumed.
3. **Run the standalone rest test — this is the authoritative check, and
   the one to paste back.** Scripting tab -> Open ->
   `crash_forge/tests/blender/test_rig_at_rest.py` -> Run Script (it
   drives Reset -> Prep -> Rig itself, fresh, so it's fine to run right
   after step 2 regardless of whether step 2 passed or failed — you
   don't need to redo steps 1-2 by hand first). Read the console output
   top to bottom:
   - The very first two lines confirm the resolved `crash_forge` package
     path (catches a stale install shadowing this repo — see
     "Landmines") and the detected `forward = ±X/Y/Z (...)` direction —
     confirm that direction actually matches your car in the viewport,
     since a wrong sign here would silently mislabel every column below.
   - If `CF_Rig` refused outright with "the rig is not a single
     connected car" (a real, structural failure, not the rest test) —
     that's `core/rig.py::check_connectivity()` catching a part with no
     constraint or parent link to anything, before a single frame ever
     stepped. It names every isolated part. This is a different, and in
     some ways more fundamental, failure than the rest test below —
     paste it back as-is.
   - Two tables print: a 3-frame one (the actual pass/fail gate) and a
     30-frame one (drift only, not asserted) — each row is one *car*
     part (not just rigid ones), marked `SIMULATED` (has its own rigid
     body — genuinely exercised by the sim) or `PARENTED` (no rigid
     body, just inherits its parent's transform — cannot independently
     fail no matter what happens; e.g. your car's brake discs/calipers
     if it has them). Only `SIMULATED` rows get an `OK`/`OVER` status
     against the printed threshold; `PARENTED` rows print `n/a`.
   - The last line is `RESULT = PASS` or `RESULT = FAIL`, followed by
     the SIMULATED/PARENTED counts — check that the SIMULATED count
     looks like what you'd actually expect to be under test (chassis +
     4 wheels + however many breakable panels/glass your car has), not
     inflated by parts that were never really at risk of failing. Paste
     the **whole console output**, not just this line — the tables are
     the part that's actually diagnostic.
4. Whether step 2/3 passed or hit the rest-test failure, click **Reset**.
   Confirm: `{'FINISHED'}`, no error lines, and every `CF_Hinge_*`/
   `CF_Motor_*`/`CF_Break_*`/`CF_NoCol_*` empty gone from the Outliner.
   This is the actual point of asking you to run this in particular —
   it's the first time anything Crash Forge creates has gone through
   `reset_self_check`'s identity-based (not name-based) leak check for
   real. If anything `CF_`-named survives, or the report names a leaked
   `cf_generated` object, that is the exact bug last session's fix was
   supposed to close — paste the report.
5. If step 2 passed cleanly, try clicking **Rig** a second time in a
   row without Reset in between: it should now be greyed out
   (`poll()` requires `stage_completed == 1` exactly, and a successful
   Rig run leaves it at 2) — confirm that. This is a known partial gap,
   not full idempotency (§3 rule 4): it blocks the double-click, but
   Prep -> Rig -> Prep -> Rig with no Reset in between is *not* yet
   guarded (Prep doesn't know Rig exists, so re-running Prep resets
   `stage_completed` to 1 without cleaning up the first Rig run's
   artifacts) — don't test that sequence expecting it to be safe yet;
   it's flagged in "M5 — Stage 2 Rig" above for a future session.
