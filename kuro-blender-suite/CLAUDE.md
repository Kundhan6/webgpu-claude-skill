# CLAUDE.md

Read `BLENDER_ADDON_MASTER_PLAN.md` (authoritative spec, in this same
folder) and `PROGRESS.md` (current state) before doing anything.
**Verify state by running `scripts/test.sh`, never by trusting this file
or the chat.**

## Location note

This suite lives at `kuro-blender-suite/` inside the `webgpu-claude-skill`
repository, not in its own repository — see `DECISIONS.md` for why. If a
dedicated `kuro-blender-suite` repo now exists, prefer working there and
treat this folder as the historical copy.

## Before writing any code

1. Read `PROGRESS.md` to find the current phase and next incomplete step.
2. Run `scripts/test.sh`. If it contradicts `PROGRESS.md`, the test suite
   is right — fix that discrepancy before doing anything else.
3. If `blender` isn't on `PATH`, `scripts/test.sh` will say so and exit
   nonzero. Get Blender 5.1.2 (primary target) or 4.5 LTS on `PATH` before
   continuing — the whole test suite is unverified without it (see
   `DECISIONS.md`, "No live Blender to introspect against").
4. Before relying on any `bpy` API name you're not sure of, run
   `scripts/introspect.py` and check its output — do not guess.

## Ground rules (from the master plan, condensed)

- One add-on at a time (MatForge → StormKit → RuinFX), except
  `kuro_core`, built first. **This session deviated on purpose**: the
  user asked to start with StormKit directly, so MatForge does not exist
  yet. See `DECISIONS.md`.
- Introspect before you code. Never hardcode a socket/operator/enum name
  you haven't verified on the target Blender.
- Every feature ships with a headless test in `tests/`.
- Non-destructive: anything added to a scene/material is tagged
  (`node["kuro_addon"] = "<addon>:<feature>"`) and fully removable.
- No silent failures: every operator wraps its body, reports a
  human-readable error, and logs the traceback.
- Every mutating operator declares `bl_options = {'REGISTER', 'UNDO'}`
  and has a test that runs it, calls `bpy.ops.ed.undo()`, and asserts the
  scene is restored.
- No per-frame Python handlers doing heavy work — drive with keyframes/
  drivers. `stormkit.lightning`'s `frame_change_post` handler is the one
  documented, O(1) exception.
- Conventional commits, one logical change per commit, tests green before
  every commit — though see the caveat above: "green" currently means
  "written and internally consistent," not "executed," until this runs on
  a real Blender.

## Repo layout

Same as the master plan's §1, minus `matforge/` and `ruinfx/` (not
started yet):

```
kuro-blender-suite/
├── kuro_core/        # shared library — build.sh vendors this into each add-on
├── stormkit/         # the only add-on built so far
├── tests/            # tests/run_all.py is the entry point
├── scripts/          # test.sh, build.sh, introspect.py, build_qa_blend.py
├── DECISIONS.md
├── PROGRESS.md
└── CLAUDE.md         # this file
```
