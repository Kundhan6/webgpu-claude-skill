# StormKit Troubleshooting

## "Applied; N material(s) skipped" after Apply to Scene

StormKit's Wetness/Snow Cover injection only touches materials whose
output is fed **directly** by a Principled BSDF node. If a material uses
a Mix Shader, has no Principled BSDF at all, or has some other
non-standard graph shape, it's skipped and named in the report box under
the Apply/Remove buttons — check the log
(`~/.config/blender/<version>/scripts/kuro_logs/stormkit.log`, or
wherever `bpy.utils.user_resource('SCRIPTS')` points on your OS) for the
exact reason per material.

This is deliberate (ground rule: "skip and report, never guess"). If you
need wetness on one of these materials, restructure it so its output
socket is fed directly by a Principled BSDF, or extend
`stormkit/wetness.py`'s `_find_principled_feeding_output` to recognize
your specific pattern.

## Fog looks identical between EEVEE and Cycles, or doesn't show up

StormKit builds a real *object* volume (never a world volume), and
EEVEE's volumetric rendering has to be enabled for it to show. The Fog
subpanel shows an info box if it couldn't verify your Blender version's
EEVEE volumetric settings automatically — check Render Properties >
Volumetrics manually and enable it if needed.

## Rain/snow looks sparse or way too dense

`precipitation_amount` (0-1) maps to a **viewport-capped** point count
(`stormkit.precipitation.MAX_VIEWPORT_POINTS`, currently 4000) for
interactive performance. Final renders automatically get a density
multiplier on top of that (`RENDER_DENSITY_MULTIPLIER`, currently 3x) via
a `render_pre`/`render_post` handler — so what you see in the viewport is
intentionally sparser than what renders. If a render still looks too
sparse or too dense, adjust `RENDER_DENSITY_MULTIPLIER` in
`precipitation.py` and re-run `Apply to Scene`.

## Lightning never seems to flash

`storm_intensity` must be > 0 — lightning frequency scales with it (0 =
never). The schedule is deterministic per scene (seeded once, stored as
`scene["kuro_lightning_seed"]`), so if you need a *guaranteed* flash on a
specific frame for a shot, use **Bake Lightning** and then manually adjust
the baked keyframes on `SK_Bolt0`-`SK_Bolt5` and `SK_LightningFlash`.

## "Remove StormKit" didn't remove something

Everything StormKit creates is tagged with a custom property
`["kuro_addon"] = "stormkit:<feature>"` on the node/object/modifier
itself. If you find something StormKit clearly created that survived
Remove StormKit, that's a bug — check whether it's tagged (Blender's
Python console: `bpy.data.objects['name']['kuro_addon']`) and file it
against `kuro_core/cleanup.py` or the relevant subsystem's `teardown()`.

## The add-on won't enable / register() raises

Check Blender's version first — StormKit requires Blender 4.5.0+
(`kuro_core.compat.check_min_version()` raises a clear error naming the
minimum otherwise). If you're on a supported version and it still fails,
check the console for a traceback; every operator wraps its body per
ground rule #6, but `register()` itself intentionally does **not** —
a broken registration should be loud, not silently half-working.
