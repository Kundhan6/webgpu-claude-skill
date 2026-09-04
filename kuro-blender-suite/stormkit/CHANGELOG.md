# StormKit Changelog

All notable changes to StormKit are recorded here. Format is loosely
Keep-a-Changelog; versions track `blender_manifest.toml`.

## [0.1.0] — 2026-07-08 — initial build

Built end-to-end in one session, without a live Blender to test against
(see `../DECISIONS.md`). Not yet verified on Blender 5.1.2.

### Added
- `scene.stormkit` state (single source of truth for all sliders).
- Sky & Sun: Nishita sky, solar-arc sun rotation/energy from
  `time_of_day` + `latitude`, overcast blend to flat grey.
- Fog: tagged volume cube, height-falloff density.
- Precipitation: Geometry Nodes rain/snow, camera-parented, wind-sheared,
  viewport-density-capped with a render-time density boost.
- Surface FX: non-destructive Wetness/Snow Cover injection into scene
  materials via `kuro_core.inject_between`, single global driver per
  effect, skip-and-report for non-Principled materials, optional
  off-by-default visible snow-geometry modifier.
- Wind: Wind/Turbulence force fields + shared `SK_WindShader` node group.
- Lightning: pre-generated bolt curves + flash light on a deterministic
  hash-based schedule; Bake Lightning converts it to real keyframes.
- 10 weather presets (Clear, Golden Hour, Overcast, Light Rain,
  Thunderstorm, Drizzle Fog, Blizzard, Fresh Snow Morning, Sandstorm
  Haze, Night Storm) with optional keyframed transitions.
- Apply to Scene / Remove StormKit / Bake Lightning / Toggle Snow
  Geometry operators, all undo-safe and exception-wrapped.
- KURO > StormKit N-panel with master sliders and per-subsystem
  subpanels.
- Full test suite under `../tests/stormkit/` (written, not yet executed
  — see `../PROGRESS.md`).
