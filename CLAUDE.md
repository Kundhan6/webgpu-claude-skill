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

M0–M3 complete: package skeleton, Stage 0 probe, CF_Reset, core/
detection modules (geometry/classify/pairs/impact/density/naming). M4
(Stage 1 Prep) has not started.

Test command:

    cd crash_forge && python3 -m pytest tests/ -v

97/97 passing as of the last session. Tier A + Tier B only — no Blender
needed to run this at all.

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

## Getting a real fixture

`crash_forge/tools/dump_car.py` — standalone, imports nothing from
`crash_forge` and nothing imports it. Run inside Blender against a real
car (Scripting tab, select the hierarchy, Run Script). Dumps raw
PartDescriptor JSON — bbox, centroid, extents, vert count, materials,
transmission, planarity — and assigns zero part roles. Krish labels roles
by hand from that JSON; don't do it for him.
