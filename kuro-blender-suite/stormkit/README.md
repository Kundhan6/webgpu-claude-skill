# StormKit — Procedural Weather Engine

One panel that makes a Blender scene *have weather*: sky/sun/time-of-day,
fog, rain or snow with wind, surface wetness/snow accumulation on
existing materials, and lightning — all driven by a handful of master
sliders and one-click presets.

> **Status:** built, not yet verified on a real Blender — see
> `../PROGRESS.md` and `../DECISIONS.md` before relying on this in
> production. Run `../scripts/test.sh` first.

## Install

**Extensions (Blender 4.2+, recommended):**
1. Run `../scripts/build.sh` to produce `dist/stormkit-<version>.zip`.
2. In Blender: Edit > Preferences > Get Extensions > (dropdown) > Install
   from Disk... and pick the zip.

**Legacy add-on install (any supported version):**
1. Run `../scripts/build.sh`.
2. Edit > Preferences > Add-ons > Install... and pick
   `dist/stormkit-<version>.zip`.
3. Enable "StormKit" in the add-on list.

Either way, the installed zip is fully self-contained — `kuro_core` is
vendored inside it, nothing else needs installing.

## Quickstart

1. Open the sidebar in the 3D Viewport (`N`), find the **KURO** tab.
2. Pick a preset (Clear, Thunderstorm, Blizzard, ...) or drag the master
   sliders yourself.
3. Click **Apply to Scene**. StormKit builds/updates its sky, fog,
   precipitation, wetness/snow, wind, and lightning objects.
4. Adjust sliders freely afterward — most of them are driver-connected
   and update live with no need to re-click Apply. `precipitation_type`
   and anything requiring a fresh subsystem build (e.g. switching Rain to
   Snow) will need one more **Apply to Scene** click.
5. **Remove StormKit** cleanly deletes everything StormKit added and
   restores materials/World exactly as they were.

## Properties reference

All state lives on `scene.stormkit` (see `properties.py` for full
tooltips): `time_of_day`, `overcast`, `fog_density`, `fog_height`,
`precipitation_type`, `precipitation_amount`, `wind_speed`,
`wind_direction`, `wetness`, `snow_cover`, `storm_intensity`,
`turbulence`, `latitude`, `transition_frames`.

## Known limitations

- **EEVEE vs. Cycles visual differences**: fog volumetrics and any
  Cycles-only masking StormKit might add in the future will look
  different (or absent) in EEVEE. The Fog subpanel shows a warning if it
  can't verify EEVEE volumetrics are enabled on your Blender version —
  check Render Properties > Volumetrics manually in that case.
- **Wetness/Snow Cover only injects into materials whose output is fed
  directly by a Principled BSDF.** Anything more exotic (Mix Shader
  stacks, no Principled at all) is skipped and listed in the panel's
  report box — StormKit will never guess at how to wire an unfamiliar
  shader graph.
- **Visible snow geometry is off by default** (performance cost) — see
  the "Add/Remove Snow Geometry" buttons in the Surface FX subpanel.
- **Lightning's visual schedule is deterministic per-scene** (seeded
  once, stored on the scene) but is *not* meant to be frame-accurate
  before you click **Bake Lightning** — bake before rendering on a farm.
- Geometry Nodes rain/snow density has a hard viewport cap
  (`precipitation.MAX_VIEWPORT_POINTS`); rendering uses a separate,
  higher multiplier applied only during the actual render.

See `../DECISIONS.md` for the reasoning behind these choices and
`TROUBLESHOOTING.md` for what to do when something doesn't look right.
