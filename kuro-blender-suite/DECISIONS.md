# DECISIONS.md

Record of ambiguous points resolved during development, per ground rule
#10 ("prefer the simpler, more robust option and note the decision here
rather than blocking"). Newest first.

---

## Repository location (2026-07-08)

The master plan specifies a standalone `kuro-blender-suite/` repository.
This session's GitHub integration could not create a new repository
(403 from the GitHub API — the App isn't permissioned for repo creation),
and the user was on mobile without laptop access to create one manually.
**Decision:** build the suite inside the existing `webgpu-claude-skill`
repository, in a clearly separated `kuro-blender-suite/` subfolder, on the
branch the session was already assigned. If/when a dedicated repo becomes
available, this folder can be `git subtree split` or just copied wholesale
— nothing here assumes it lives at the repo root.

## Build order deviates from ground rule #1 (2026-07-08)

Ground rule #1 mandates building MatForge fully (with its acceptance gate
passing) before StormKit begins. The user explicitly asked to start with
"the 2nd addon" (StormKit) directly. **Decision:** honor the explicit
request — kuro_core (the one exception ground rule #1 allows) was built
first as the unavoidable shared dependency, then StormKit directly.
MatForge and RuinFX are not started. `PROGRESS.md` reflects this real
state; do not assume MatForge exists.

## No live Blender to introspect against (2026-07-08, ongoing)

Ground rule #2 requires introspecting every `bpy` API name before relying
on it. This dev container has no `blender` binary at all (verified via
`which blender` / `blender --version`, both fail). Every node-graph,
socket-name, and property-name choice in `kuro_core/` and `stormkit/` was
therefore written from documented/training knowledge of the Blender
Python API, not live introspection, with three mitigations:

1. `scripts/introspect.py` is provided specifically to close this gap —
   run it once on Blender 5.1.2 (or 4.5 LTS) and diff its output against
   the assumptions called out in each module's docstring.
2. Wherever the actual API surface was genuinely uncertain (render engine
   identifiers, EEVEE volumetrics property names), the code queries the
   live enum/property list at runtime and searches defensively rather
   than hardcoding a string — see `kuro_core/compat.py`'s
   `get_eevee_identifier()` and `stormkit/fog.py`'s
   `eevee_volumetrics_hint()`.
3. `scripts/test.sh` / `tests/run_all.py` exist and are believed correct
   by construction, but **have never actually been executed** in this
   session — there is no Blender to run them. Do not report the test
   suite as "passing"; report it as "written, pending a run on Blender
   5.1.2." The very first thing a session with Blender access should do
   is run `scripts/test.sh` and fix whatever it finds.

## Latitude lives on `scene.stormkit`, not add-on preferences (2026-07-08)

§4.2.1 says "expose latitude in prefs." AddonPreferences aren't reachable
from a driver's `SINGLE_PROP` variable via an RNA path from an ID-block
(preferences aren't parented under Scene/Object/etc. in the RNA tree), so
a preferences-based latitude couldn't drive the sun's solar-arc elevation
directly. **Decision:** move `latitude` onto `STORMKIT_PG_state`
(`scene.stormkit.latitude`) instead. This is also arguably better UX — a
single .blend can then hold shots set in different real-world locations,
each with its own scene and its own latitude.

## GN viewport/render density split done in Python, not in the node graph (2026-07-08)

§4.2.3 asks for "viewport density cap + separate render multiplier."
There is no reliable, version-stable way for a Geometry Nodes tree to
branch on "am I being evaluated for the viewport or for a final render"
from inside the graph. **Decision:** expose a single `Viewport Density`
input, and implement the render-time boost via a `render_pre` /
`render_post` handler pair (`stormkit/precipitation.py`) that multiplies
the value up before rendering and restores it after — O(1) work per
render, not per frame, so it doesn't violate ground rule #8.

## Lightning scheduling is a pure hash function, not a stored list (2026-07-08)

§4.2.6 describes a "Poisson-ish schedule seeded per scene." Rather than
generating and persisting a list of trigger frames (which would need to
survive undo/redo, file save/load, and re-registration cleanly),
`stormkit/lightning.py` computes `is_trigger_frame(frame, seed,
storm_intensity)` as a pure integer-hash function of its arguments. This
makes the one `frame_change_post` handler trivially O(1) (ground rule
#8's named exception) and makes the whole scheduling algorithm directly
unit-testable without simulating hundreds of frames in sequence.

## Lightning bake and preset transitions avoid the slotted-action API entirely (2026-07-08)

Ground rule #3 explicitly flags "lightning bake" and "preset transitions"
as needing Blender 5.x's new slotted-action API (`layers/strips/
channelbags`) instead of the removed `action.fcurves`/`action.groups`.
Rather than hand-roll that unfamiliar API from documentation alone (high
risk of a subtle mismatch with zero ability to verify here):

- `lightning.bake_lightning()` only ever calls plain
  `obj.keyframe_insert(...)` — explicitly called out as still fine in
  ground rule #3 — and never touches interpolation modes or reads the
  resulting FCurves back.
- `stormkit/presets.py`'s transition support does the same
  (`keyframe_insert` only).
- The corresponding tests (`test_presets.py`,
  `test_lightning.py::test_bake_lightning_...`) verify the *result* by
  evaluating `frame_set()` + reading the property, never by walking
  `action.layers`/`.fcurves` — so the test suite has no dependency on
  that API surface either, and nothing in this codebase needs updating if
  the slotted-action API's exact method names differ from what ground
  rule #3's summary implies.

## Unified Mix node socket names assumed as Factor/A/B/Result (2026-07-08)

`ShaderNodeMix` (the 3.4+ unified replacement for `ShaderNodeMixRGB`) is
used throughout `sky.py`, `wetness.py`, and `wind.py` with socket names
`"Factor"`/`"A"`/`"B"`/`"Result"` across all three `data_type` variants
(FLOAT/VECTOR/RGBA). This is the standard, documented behavior, but is
specifically flagged in `scripts/introspect.py`'s
`introspect_mix_node()` for verification, since it's the single node
reused the most across the highest-risk modules.
