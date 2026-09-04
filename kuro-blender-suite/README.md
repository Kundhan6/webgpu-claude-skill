# KURO Blender Suite

Three production-grade Blender add-ons per `BLENDER_ADDON_MASTER_PLAN.md`:
**MatForge** (AI material generator), **StormKit** (procedural weather
engine), **RuinFX** (procedural damage system).

> **Only `kuro_core` and StormKit exist so far** — see `PROGRESS.md` for
> exactly what's built and `DECISIONS.md` for why (short version: the
> owner asked to build "the 2nd add-on" — StormKit — directly, rather
> than the master plan's default MatForge-first order).
>
> **This suite has not been tested against a real Blender.** The
> development container this was built in has no `blender` binary at all.
> Every module was written carefully against documented Blender API
> behavior and cross-checked internally, but `scripts/test.sh` has never
> actually been run. Do that first, on Blender 5.1.2, before trusting any
> of it — see `PROGRESS.md`'s "Next steps."

## Layout

```
kuro-blender-suite/
├── BLENDER_ADDON_MASTER_PLAN.md   # authoritative spec
├── CLAUDE.md                      # read this first in any new session
├── PROGRESS.md                    # current state — trust this, not the chat
├── DECISIONS.md                   # ambiguous points, resolved and recorded
├── kuro_core/                     # shared library, vendored into each add-on at build time
├── stormkit/                      # the only add-on built so far
├── tests/                         # tests/run_all.py is the entry point
└── scripts/
    ├── test.sh                    # run the full suite headlessly
    ├── build.sh                   # assemble installable .zip(s)
    ├── introspect.py              # verify bpy API assumptions on your Blender
    └── build_qa_blend.py          # generate the manual-QA .blend for StormKit
```

## Quickstart

```bash
# 1. Verify the API assumptions this codebase makes, on YOUR Blender:
blender --background --factory-startup --python scripts/introspect.py

# 2. Run the test suite:
scripts/test.sh

# 3. Build an installable zip:
scripts/build.sh
# -> dist/stormkit-0.1.0.zip

# 4. Generate the manual-QA scene for visual review:
blender --background --factory-startup --python scripts/build_qa_blend.py
# -> qa_stormkit.blend, one scene per preset
```

See `stormkit/README.md` for install steps and a properties reference,
and `stormkit/TROUBLESHOOTING.md` when something doesn't look right.
