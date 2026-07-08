# PROGRESS.md

**Last updated:** 2026-07-08
**Current phase:** StormKit built end-to-end (spec §4 complete); MatForge
and RuinFX not started (see `DECISIONS.md` — the user asked to build the
2nd add-on, StormKit, directly).

## What's done

- **`kuro_core/`** (§2): `compat.py` (version gate, Principled BSDF socket
  aliasing, Cycles/EEVEE identifier detection, pointiness/bevel support
  checks), `nodeutils.py` (`NodeGraphBuilder`, `ensure_group`,
  `inject_between`/`eject`, `add_scene_driver`, `gn_input_identifiers`),
  `presets.py` (schema validation, load/save, corrupt-file handling),
  `uiutils.py` (KURO tab panel base, error reporting/dialogs),
  `cleanup.py` (tagged-object/modifier/node-group sweep + full removal).
- **`stormkit/`** (§4), all subsystems:
  - `properties.py` — `scene.stormkit` state (single source of truth,
    including `latitude` and `transition_frames` — see `DECISIONS.md`
    for why latitude isn't in add-on preferences).
  - `sky.py` — Nishita sky, solar-arc-driven sun, overcast blend to grey,
    byte-level World-Surface restore on teardown (including deleting a
    freshly-created World, not just clearing nodes).
  - `fog.py` — tagged volume cube, height-falloff Principled Volume,
    EEVEE-volumetrics best-effort hint (never hardcodes a property name
    that might not exist on this Blender version).
  - `precipitation.py` — shared Geometry Nodes builder for rain/snow,
    camera-parented emitter, wind shear + flutter, viewport density cap
    with a `render_pre`/`render_post` handler pair for a separate render
    multiplier.
  - `wetness.py` — `SK_Wetness`/`SK_SnowCover` node groups injected via
    `kuro_core.inject_between`, single global driver per effect, skip-
    and-report for non-Principled materials, optional off-by-default
    snow-geometry GN modifier.
  - `wind.py` — Wind/Turbulence force fields + shared `SK_WindShader`
    node group for foliage materials.
  - `lightning.py` — pre-generated bolt curves + flash light, scheduled
    by a pure hash function (not stored state) so the one
    `frame_change_post` handler is O(1); Bake Lightning converts the
    schedule to real keyframes.
  - `presets.py` + `presets/*.json` — 10 shipped presets (Clear, Golden
    Hour, Overcast, Light Rain, Thunderstorm, Drizzle Fog, Blizzard,
    Fresh Snow Morning, Sandstorm Haze, Night Storm), schema-validated.
  - `operators.py` — Apply to Scene, Remove StormKit (confirm-gated),
    Bake Lightning, Apply Weather Preset (± transition), Toggle Snow
    Geometry. All REGISTER+UNDO, all exception-wrapped.
  - `ui.py` — KURO > StormKit N-panel: master sliders + Sky/Fog/
    Precipitation/Surface FX/Wind/Lightning subpanels, skipped-materials
    report box.
  - `blender_manifest.toml` — Extensions-format packaging metadata.
- **`tests/`** — `harness.py` (isolated test runner, render-stat helper,
  preview-scene builder), `run_all.py` (entry point), full coverage per
  subsystem plus the §4.6 cross-cutting acceptance tests (preset apply on
  empty/populated scenes, full-removal datablock-count restore, handler
  idempotency, undo round-trip on Apply to Scene). The required 15-fixture
  byte-level material inject/eject test lives in `tests/stormkit/test_wetness.py`.
- **`scripts/`** — `test.sh`, `build.sh` (verified working in this dev
  environment — see below), `introspect.py`, `build_qa_blend.py`.

## What's NOT done / open issues

1. **The test suite has never actually been run.** This dev container has
   no `blender` binary (`which blender` fails). Every test in `tests/` was
   written to be correct by careful construction and cross-checking
   against documented Blender API behavior, but **none of it has been
   executed**. The single highest-priority next step for any session with
   Blender access is: run `scripts/test.sh`, fix whatever it finds, and
   update this file honestly with the real pass/fail state.
2. **`scripts/build.sh` has been verified in this environment** — it
   successfully vendors `kuro_core` into `stormkit/kuro_core/`, rewrites
   the dev-time imports to relative, and produces
   `dist/stormkit-0.1.0.zip`. (`rsync` isn't installed here, so it uses
   `cp -r` instead — works fine, just slightly slower on large trees.)
   Installing that zip into a real Blender has **not** been verified.
3. **MatForge and RuinFX do not exist.** Only `kuro_core` and StormKit
   were built, per the user's explicit request to build "the 2nd add-on."
4. **The QA `.blend` has not been generated** — `scripts/build_qa_blend.py`
   exists and is believed correct, but generating and opening the actual
   file requires Blender, which isn't available here.
5. High-risk-for-API-drift areas (flagged in each module's docstring and
   summarized in `DECISIONS.md`): the Geometry Nodes graph in
   `precipitation.py` (the single biggest/most intricate node graph in
   the codebase), the unified `ShaderNodeMix` socket names used
   throughout, and `Object.field` force-field scripting in `wind.py`.
   Run `scripts/introspect.py` before trusting any of these.

## Next steps, in order

1. Get Blender 5.1.2 on `PATH` and run `scripts/test.sh`. Fix failures —
   expect some, especially in `precipitation.py`'s Geometry Nodes graph
   and anywhere `scripts/introspect.py` flags a mismatch.
2. Run `scripts/build_qa_blend.py`, open the result in Blender, and do a
   visual pass per subsystem (sky color/sun angle, fog thickness, rain/
   snow look and density, puddle/snow material response, wind-driven
   drift, lightning flash timing).
3. Once StormKit's gate is genuinely green (tests run and passing, QA
   pass done), decide whether to continue to MatForge/RuinFX per the
   master plan's original order, or continue extending StormKit.
4. Consider migrating this folder into its own `kuro-blender-suite`
   repository if one becomes available (see `DECISIONS.md`).
