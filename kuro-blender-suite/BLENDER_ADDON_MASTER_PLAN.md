# KURO BLENDER SUITE — MASTER BUILD PLAN
### Three production-grade add-ons: MatForge (AI Material Generator) · StormKit (Procedural Weather Engine) · RuinFX (Procedural Damage System)

**Audience of this document:** Claude Code (Sonnet, high effort), acting as a senior Blender pipeline TD + Python engineer.
**Owner:** Krish (KURO). He does visual QA in the Blender UI; you do everything else.
**Quality bar:** These add-ons must be installable in a fresh Blender and work flawlessly — the standard is "handed to a VFX studio department." That means: zero console errors, full undo support, non-destructive workflows, version guards, graceful failure with human-readable messages, and a test suite that proves it.

---

## 0. NON-NEGOTIABLE GROUND RULES

1. **Build ONE add-on at a time, in the order given (MatForge → StormKit → RuinFX).** Do not scaffold all three at once. Each add-on must pass its full acceptance checklist before the next begins. Shared code extracted into `kuro_core` is the only exception.
2. **Never guess a `bpy` API name.** Blender's Python API drifts between versions (4.0 renamed most Principled BSDF sockets; 4.1 removed the Musgrave texture). When unsure, write a tiny introspection script and run it headlessly:
   ```bash
   blender --background --factory-startup --python-expr "import bpy; n=bpy.data.materials.new('x'); n.use_nodes=True; p=n.node_tree.nodes['Principled BSDF']; print([s.name for s in p.inputs])"
   ```
   Introspect first, code second. This applies to node input names, operator IDs, enum values — everything.
3. **Primary target: Blender 5.1.2 (the owner's install — all development and gate tests run here).** Keep 4.5 LTS compatibility via the compat layer where cheap, but never at the cost of the 5.1 experience. Package using the Extensions format (`blender_manifest.toml`).
   **Blender 5.x API breaks you MUST respect (verify each by introspection before relying on it):**
   - Dict-like access to `bpy.props`-defined properties is removed (`scene['stormkit']`-style reads will fail). Use attribute access for registered props. Tagging with *actual* custom IDProperties (`node["kuro_addon"] = ...`) is still valid — but never mix the two patterns.
   - The legacy Action API (`action.fcurves`, `action.groups`) is removed — any direct F-curve work (lightning bake, preset transitions) must use the slotted-action API (layers/strips/channelbags, `action.fcurve_ensure_for_datablock()`); plain `obj.keyframe_insert()` remains fine.
   - Grease Pencil types were renamed to Annotation types; several previously-importable bundled modules (`bl_console_utils`, etc.) are now private — import nothing undocumented.
   - Python is 3.13; blendfiles saved from 5.x will not open below 4.5.
   - Render-engine identifiers and EEVEE naming have shifted across 4.x/5.x — introspect `bpy.context.scene.render.engine` enum items at register time; never hardcode the EEVEE identifier string without checking.
4. **Headless self-verification after every feature.** You cannot see the viewport. Your eyes are: stdout, saved renders analyzed with numpy (bundled with Blender), and structured logs. Every feature ships with a headless test that exercises it.
5. **Non-destructive by default.** Anything the add-on adds to a user's scene or materials must be tagged (custom property `["kuro_addon"] = "<addon>:<feature>"`) and fully removable with one operator. A studio will reject anything that mangles their materials.
6. **No silent failures.** Every operator wraps its body; on error it calls `self.report({'ERROR'}, msg)` with a human-readable message and logs the traceback. Never let a raw exception hit the user.
7. **Undo works.** Every operator that modifies data declares `bl_options = {'REGISTER', 'UNDO'}` and is verified by a headless test that runs the op, calls `bpy.ops.ed.undo()`, and asserts the scene is restored.
8. **Performance discipline.** No per-frame Python handlers doing heavy work. Drive animation with keyframes, drivers, or Geometry Nodes — not `frame_change_post` loops, except where explicitly specified (and then O(small)).
9. **Commit discipline.** Conventional commits, one logical change per commit, test suite green before every commit. Keep a `CHANGELOG.md` per add-on.
10. **When a spec detail is ambiguous, prefer the simpler, more robust option and note the decision in `DECISIONS.md`.** Do not block waiting for answers on minor points.

---

## 1. REPOSITORY LAYOUT

```
kuro-blender-suite/
├── kuro_core/                  # shared library, vendored INTO each add-on at build time
│   ├── __init__.py
│   ├── compat.py               # version guards, socket-name maps, feature detection
│   ├── nodeutils.py            # node graph builder helpers (create, link, layout, tag)
│   ├── presets.py              # JSON preset load/save/validate (per-addon namespaces)
│   ├── uiutils.py              # panel helpers, icon management, error dialogs
│   ├── log.py                  # logging: file + console, per-addon logger
│   └── cleanup.py              # find & remove all tagged nodes/objects/modifiers
├── matforge/                   # Add-on A
├── stormkit/                   # Add-on B
├── ruinfx/                     # Add-on C
├── tests/
│   ├── run_all.py              # entry: blender --background --python tests/run_all.py
│   ├── harness.py              # test runner, assertion helpers, render-stat helpers
│   ├── matforge/ stormkit/ ruinfx/ core/
│   └── golden/                 # tiny reference renders + stat baselines (JSON)
├── scripts/
│   ├── test.sh                 # runs full suite headlessly, exits nonzero on failure
│   ├── build.sh                # assembles installable .zip per add-on (vendors kuro_core)
│   └── introspect.py           # API introspection helpers
├── DECISIONS.md
└── README.md
```

**Vendoring rule:** each shipped `.zip` is fully self-contained — `build.sh` copies `kuro_core` into the add-on package as a subpackage (`matforge/kuro_core/`) and rewrites imports to relative. Studios install one zip, not three plus a dependency.

---

## 2. SHARED FOUNDATION — `kuro_core` (build this first, ~day one)

### 2.1 `compat.py`
- `BLENDER_VERSION = bpy.app.version` checks; minimum-version gate at register time with a clear error.
- **Principled BSDF socket map.** Blender 4.x names (verify by introspection before hardcoding):
  `Base Color, Metallic, Roughness, IOR, Alpha, Normal, Subsurface Weight, Subsurface Radius, Subsurface Scale, Transmission Weight, Coat Weight, Coat Roughness, Sheen Weight, Emission Color, Emission Strength, Specular IOR Level, Anisotropic`
  Expose `set_input(node, canonical_name, value)` that resolves via the map and raises a clear error listing available sockets if resolution fails.
- **Feature detection:** `has_musgrave()` (always False on 5.x — never use it; use Noise Texture with detail/roughness/lacunarity instead), render-engine detection (Cycles vs EEVEE — resolve identifiers via introspection per ground rule 3), and `pointiness_supported()` / `bevel_node_supported()` (Cycles-only features — every use needs an Eevee fallback path).

### 2.2 `nodeutils.py`
- `NodeGraphBuilder(material_or_group)` — fluent API: `add(node_type, name, **inputs)`, `link(from_node, from_socket, to_node, to_socket)`, `auto_layout()` (grid layout by dependency depth so generated graphs are human-readable — studios will open them), `tag_all(addon_id)`.
- `ensure_group(name, builder_fn)` — idempotent node-group creation; re-registering never duplicates groups (check `bpy.data.node_groups`, verify interface matches, rebuild if version bumped).
- `inject_between(material, target_socket, group)` / `eject(material, addon_id)` — the core non-destructive insertion/removal machinery StormKit and RuinFX depend on. Insertion records the original link in a custom property so ejection restores it exactly.

### 2.3 `presets.py`
- Presets are JSON files in the add-on's `presets/` dir + user dir (`bpy.utils.user_resource('SCRIPTS')`). Schema-validated on load (hand-rolled validator, no external deps). Corrupt preset → skip with warning, never crash the UI.

### 2.4 Test harness (`tests/harness.py`)
- Minimal runner (Blender's Python has no pytest): discovers `test_*` functions, isolates each in a fresh `bpy.ops.wm.read_factory_settings(use_empty=True)`, catches and reports, exits nonzero on any failure.
- **Render-stat verification:** helper that renders a 128×128 Cycles CPU frame (16 samples) to `/tmp`, loads pixels via `bpy.data.images` + numpy, and returns `{mean, std, min, max, channel_means}`. Assertions like "render is not black," "wet version is darker than dry version," "snow version has higher luminance" are how you *see*. Golden baselines stored as JSON stats (not pixel-perfect images — too fragile across versions).

**Acceptance gate for Phase 0:** `scripts/test.sh` runs green on a machine with only Blender installed; core tests cover compat map, builder, inject/eject round-trip (material byte-identical after eject), preset validation.

---
## 3. ADD-ON A — **MatForge** (AI Smart Material Generator)

**What it is:** Type a description ("weathered copper with teal patina and edge wear"), get a fully built, editable, procedural Principled BSDF node graph. Works offline via a rich preset/recipe engine; optionally uses the Anthropic API (user's own key) for true free-text generation.

### 3.1 Architecture — the three-layer rule
```
[Prompt / Preset]  →  [Material Spec (strict JSON)]  →  [Deterministic Node Builder]  →  [Node graph]
```
The LLM (or preset engine) ONLY ever produces the JSON spec. The builder is 100% deterministic Python. **The LLM never emits node names, socket names, or Python.** This is the single most important architectural decision — it makes output reliable, testable, and version-proof.

### 3.2 Material Spec schema (v1) — implement exactly, validate strictly
```json
{
  "spec_version": 1,
  "name": "Weathered Copper",
  "seed": 42,
  "base": {
    "base_color": [0.72, 0.45, 0.20], "metallic": 1.0, "roughness": 0.35,
    "ior": 1.45, "coat_weight": 0.0, "sheen_weight": 0.0,
    "emission_color": [0,0,0], "emission_strength": 0.0
  },
  "layers": [
    {
      "type": "color_variation | patina | dirt_cavity | edge_wear | scratches |
               rust | dust_top | fingerprints | streaks | tiles | wood_grain |
               fabric_weave | puddle_gloss",
      "strength": 0.6,
      "scale": 3.0,
      "color": [0.1, 0.5, 0.45],
      "roughness_shift": 0.25,
      "params": { "...type-specific, all optional with defaults..." }
    }
  ],
  "surface": { "bump_strength": 0.15, "bump_scale": 8.0, "displacement": false },
  "mapping": { "coords": "object | uv | generated", "scale": [1,1,1] }
}
```
- Every layer type is a **node-group recipe** in `matforge/recipes/` — a Python function that builds a reusable node group with exposed inputs (Strength, Scale, Color, Seed…). Layers chain: each takes the previous BaseColor/Roughness/Normal and outputs modified versions (a "smart material" stack, Substance-style).
- **Masks per layer type:** `edge_wear` → Bevel-node normal-difference + Pointiness (Cycles), fallback = noise-broken geometry mask on Eevee (document the visual difference); `dirt_cavity` → AO node inverted, radius param; `dust_top` / `streaks` → world-space Normal Z masks; `rust/patina` → layered noise+voronoi through color ramps. Seed offsets every noise `W`/vector so `seed` changes give distinct variants.
- Builder consumes the spec, uses `NodeGraphBuilder`, tags everything, auto-layouts, and names the material from spec.

### 3.3 Preset/offline engine (must be excellent — most users won't add an API key)
- Ship **≥40 curated presets** across metals, stone/concrete, wood, fabric, plastics, ceramics, glass, sci-fi/emissive, stylized. Each is just a spec JSON — write them, render them, tune them.
- Offline "prompt" mode: keyword matcher (material nouns → nearest preset; modifiers like "rusty/old/wet/polished/dark" → spec mutations: e.g. "rusty" appends a rust layer, "polished" drops roughness & wear). Deterministic and honest — UI labels it "Preset match" vs "AI generated."

### 3.4 AI bridge (optional, off by default)
- Add-on Preferences: Anthropic API key field (password subtype), model name (default `claude-sonnet-4-6`), timeout, "AI enabled" toggle.
- Request via `urllib.request` (no third-party deps) to `https://api.anthropic.com/v1/messages`, run in a **background thread** with `bpy.app.timers` polling a queue — the UI must never freeze. System prompt: the full spec schema + 3 few-shot examples + "respond ONLY with JSON."
- Response pipeline: strip fences → `json.loads` → schema validation → **clamp all numerics to legal ranges** → build. Any failure at any stage → clear error + automatic fallback offer to preset match. Retry once on malformed JSON with the validator errors appended to the prompt.
- Privacy note in prefs: prompt text is sent to Anthropic; nothing else ever leaves the machine.

### 3.5 UI (N-panel → "KURO" tab → MatForge)
- Prompt text field + Generate button (icon feedback: running/done/error).
- Preset browser: category enum + preset enum with live preview name; Apply / Apply as New.
- Post-generate stack editor: list of applied layers with per-layer Strength/Scale/Seed sliders that drive the exposed group inputs live (no rebuild needed — this is why layers are groups).
- Buttons: New Seed, Duplicate Material, **Remove MatForge Nodes** (full clean ejection), Open Preset Folder.

### 3.6 Tests & acceptance (all headless)
- Spec validator: 20+ good/bad spec fixtures.
- Every layer recipe builds without error on 5.1.2; graph node/link counts match expectations.
- Every shipped preset builds AND renders on a sphere; render stats sane (not black, std > threshold, metals vs dielectrics differ in expected channels).
- Seed test: same spec+seed → identical graph parameters; different seed → different noise W values.
- Eject test: apply → eject → material slot restored to pre-state.
- Undo test on the Generate operator.
- AI bridge: mocked responses (valid, malformed, over-range, timeout) — never call the live API in tests.
- **Manual QA handoff for Krish:** a generated `qa_matforge.blend` + checklist (viewport perf, preview quality in Eevee & Cycles, stack-editor feel).

---

## 4. ADD-ON B — **StormKit** (Procedural Weather Engine)

**What it is:** One panel that makes a scene *have weather*: sky/sun/time-of-day, fog & clouds, rain or snow with wind, surface wetness/snow accumulation on existing materials, and lightning — all driven by a handful of master sliders and one-click presets. It orchestrates Blender systems; it does not simulate an atmosphere.

### 4.1 The Weather State (single source of truth)
A `PropertyGroup` on `Scene` (`scene.stormkit`):
`time_of_day (0–24), overcast (0–1), fog_density, fog_height, precipitation_type (none/rain/snow), precipitation_amount, wind_speed, wind_direction, wetness (0–1), snow_cover (0–1), storm_intensity (drives lightning), turbulence`
Every subsystem reads ONLY this state. Preset = a saved state + transition. All properties have `update=` callbacks that push values into the scene via drivers/node inputs — and **all callbacks must be cheap** (set values, never rebuild graphs).

### 4.2 Subsystems
1. **Sky & Sun** — World gets a tagged Sky Texture (Nishita mode); `time_of_day` drives `sun_elevation`/`sun_rotation` via driver math (simple solar arc; expose latitude in prefs). A tagged Sun lamp is synced to the sky (angle, energy scaled by overcast). `overcast` blends sky toward a flat grey gradient group and drops sun strength/sharpens softness (angle ↑).
2. **Fog** — a tagged cube volume object scaled to a user-set region (default: camera frustum-ish box), Principled Volume with density = `fog_density * height_falloff` (Z gradient node group for ground fog via `fog_height`). Eevee: verify volumetrics enabled; expose quality hints. NEVER use world volume (kills performance and escapes control).
3. **Precipitation (Geometry Nodes, not legacy particles)** — one tagged GN object per type.
   - *Rain:* emitter box parented above the active camera (follows camera, so rain exists only where seen). Points distributed in volume; per-point fall offset = `(scene_time * fall_speed + hash(id)) mod box_height`; wind vector shears velocity & instance tilt. Instances = stretched thin cylinders with a simple translucent/refraction material; motion streaks via instance length ∝ speed (cheaper and more reliable than motion blur). Density slider remaps point count with a hard viewport cap + separate render multiplier.
   - *Splashes (optional toggle):* ray-cast a small fraction of drops to ground plane, instance ripple decal planes with animated radial-wave shader.
   - *Snow:* same skeleton; slower fall, per-point sine drift for flutter, instance = small ico/flake with SSS-lite material; wind drift stronger.
4. **Surface wetness & snow cover (the hard part — use `kuro_core.inject_between`)**
   - Build two node groups: `SK_Wetness` (input: BaseColor, Roughness; darkens color ~×0.55 at full wetness, drops roughness toward 0.05, adds puddle mask = up-facing normal × noise with hard ramp, puddles get flat normal + near-zero roughness) and `SK_SnowCover` (up-facing mask with noise-broken edge → mixes to snow shader: white, subsurface-ish, high-frequency bump).
   - **Injection mode (default):** for each selected/all-scene material, wrap the Principled BSDF's Base Color, Roughness, and Normal inputs through the group; record original links; one global "wetness" value drives all instances via a driver on the group input → single slider controls the whole scene. **Ejection restores materials exactly** (byte-level test).
   - **Override mode (fallback for exotic node setups):** skip materials whose output isn't fed by a Principled BSDF; list them in a report panel instead of guessing. Never inject into a graph you can't safely restore.
   - Snow *geometry* (visible thickness): optional GN modifier per mesh — top-facing faces extruded/displaced instance layer, tagged, removable. Off by default (perf).
5. **Wind** — a tagged Wind force field (affects any user cloth/particles) + a global "SK_WindShader" group (vector wobble) that precipitation and optional foliage materials read. `turbulence` adds a Turbulence field.
6. **Lightning (storm_intensity > 0)** — pre-generated set of 5–8 bolt meshes (recursive midpoint-displacement polylines → skin/curve bevel, emissive material). A lightweight `frame_change_post` handler (the ONE allowed handler; O(1) work) fires a bolt: on trigger frames (Poisson-ish schedule seeded per scene), unhide a random bolt for 2–3 frames + keyframe a sky/area light flash with 1-frame decay + optional distant-thunder marker on the timeline for sound sync. Bake schedule to keyframes on demand ("Bake Lightning") so renders on farms don't depend on the handler.

### 4.3 Presets (ship ≥10)
Clear / Golden Hour / Overcast / Light Rain / Thunderstorm / Drizzle Fog / Blizzard / Fresh Snow Morning / Sandstorm-ish Haze / Night Storm. Preset apply supports **transition**: keyframe current state → target state over N frames (great for shots).

### 4.4 UI
Master panel: preset row + big sliders (the state props). Subpanels: Sky, Fog, Precipitation, Surface FX (with material include/exclude list + "report skipped"), Wind, Lightning. Global buttons: Apply to Scene, **Remove StormKit** (total cleanup — objects, forces, injected nodes, drivers, handlers — verified by test), Bake Lightning, Bake Transition.

### 4.5 Engine notes
Detect Cycles vs EEVEE at apply time; volumetric density and rain-drop material get per-engine tuned defaults (store both in the group, switch via a driver on `scene.render.engine`). Document known visual deltas in README rather than chasing parity.

### 4.6 Tests & acceptance
- State round-trip: set every property, save/load .blend headlessly, values persist.
- Apply each preset to (a) empty scene, (b) scene with 50 objects/20 materials — no errors, object/node counts as expected.
- Injection/ejection byte-level restore test across a fixture library of 15 tricky materials (node groups, mix shaders, no-Principled, muted nodes).
- Render stats: wet scene darker + glossier (spec channel) than dry; snow scene brighter; fog scene lower contrast. Rain GN evaluates at frames 1/50/250 without error (point counts > 0, bounded).
- Full Remove leaves the .blend datablock-identical to pre-apply (orphan purge included).
- Handler test: register/unregister across file load; no duplicate handlers (idempotent registration).
- Manual QA .blend for Krish: one city-street-ish scene with all presets as scene copies.

---
## 5. ADD-ON C — **RuinFX** (Procedural Damage System)

**What it is:** Three tiers of damage, cleanly separated because they have different risk profiles. Tier 1 is shader-only and rock solid; Tier 2 modifies geometry non-destructively; Tier 3 orchestrates fracture + physics and is explicitly a bake workflow.

### 5.1 Tier 1 — Surface Damage (shader "smart wear", reuses MatForge recipe machinery)
- Node groups: `RX_EdgeWear` (bevel-normal-difference + pointiness → exposed metal/underlayer color, Cycles; baked-curvature path for Eevee — see 5.4), `RX_Scratches` (anisotropic stretched noise + directional ramp), `RX_Grime` (AO cavity + streak masks), `RX_Rust` (multi-octave noise → ramp → color + roughness + bump, with "spread" param), `RX_Chipped_Paint` (hard-ramp voronoi mask revealing undercoat + edge-follow bias), `RX_Cracks` (voronoi distance-to-edge → crack lines with bump depth).
- Applied via the same `inject_between` machinery (tagged, ejectable, single "Damage Amount" master driver per object or per material).
- Presets: Factory New → Light Wear → Heavy Wear → Abandoned → Corroded (each a stack of the above with tuned params).

### 5.2 Tier 2 — Geometric Damage (non-destructive modifiers)
- **Dents:** GN modifier — scatter N "impact points" (seeded, or user-placed empties in "paint mode": click adds a tagged empty) → radial falloff displacement inward along normal, with crumple noise inside the dent radius + optional edge-ring sharpening. Fully parametric: count/depth/radius/seed.
- **Bullet holes / punctures:** per-impact-point boolean spheres/cones via ONE collection-based Boolean modifier (exact solver), plus a matching decal ring (scorch/paint-crack) projected via UV-less object-coordinates in the shader. **Mesh-safety gate:** before enabling booleans, validate the mesh (manifold check via bmesh, triangulation sanity); on failure, refuse with a report ("mesh is non-manifold at N edges — use Dents/decal mode instead") instead of producing garbage. This gate is what separates studio-grade from toy.
- **Torn edges/erosion:** GN — select boundary/masked region → displace with high-octave noise + optional face deletion by noise threshold (destructive variant behind an explicit "Apply" click, never default).

### 5.3 Tier 3 — Fracture & Destruction (bake workflow, be honest about it)
- Orchestrate the bundled **Cell Fracture** add-on (`object.add_fracture_cell_objects`) — enable it programmatically if disabled; if unavailable, ship our own basic voronoi-cell fracture via GN as fallback (flag in DECISIONS.md which path shipped).
- Pipeline operator "Prepare Destruction": duplicate source (original hidden + preserved) → fracture with UI-chosen cell count/noise/interior material (auto-generate interior material via MatForge rust/concrete recipe — nice cross-sell) → rigid body setup (chunks active, ground passive, constraints between neighbor chunks with breaking threshold slider = "structural strength") → optional "trigger" empty: chunks sleep until trigger proximity/frame.
- "Simulate & Bake" operator: runs `bpy.ops.ptcache.bake_all` headlessly-safe, then optional "Convert to Keyframes" for farm-safe output.
- Dust/debris on break: GN emission from chunk boundaries during high-velocity frames (velocity attribute read from baked sim), simple smoke-card instances — NOT a full smoke sim (document as future work).
- Hard limits documented in UI tooltips: poly budget warning above ~500k source tris, chunk count caps with override checkbox.

### 5.4 Baking utility (shared, ships inside RuinFX, used by MatForge too)
"Bake Cycles-only masks" operator: smart-UV-project if no UVs (with consent dialog), bake pointiness/bevel/AO masks to an image at chosen resolution, auto-swap the procedural mask input for the baked texture (tagged, reversible). This is the Eevee-parity path and also the game-export path — studios will love it. Test: bake on a fixture mesh headlessly, assert image is non-uniform and plugged in.

### 5.5 UI
Three subpanels matching the tiers, damage presets row on top, per-object damage seed + master amount, "Remove RuinFX from Selected/All", mesh-safety report panel.

### 5.6 Tests & acceptance
- All Tier-1 groups build + render-stat tests (worn version differs from clean in expected direction).
- Dent GN: apply to sphere fixture, assert bounding box shrinks locally / displacement attribute nonzero; seed determinism.
- Boolean gate: fixture set of good/bad meshes — bad meshes must be *refused*, good ones produce manifold results (bmesh validation post-op).
- Fracture pipeline headless: cube → 20 chunks → rigid body world exists → bake 30 frames → chunk transforms at frame 30 ≠ frame 1 → original mesh untouched & recoverable.
- Undo + full-removal tests as per ground rules.

---

## 6. PHASE PLAN & GATES (Claude Code: follow strictly)

| Phase | Deliverable | Gate to pass |
|---|---|---|
| 0 | Repo, kuro_core, harness, CI script | core tests green on 5.1.2 |
| 1 | MatForge builder + 10 presets + UI skeleton | all presets build+render headlessly |
| 2 | MatForge full (40 presets, stack editor, eject, offline prompt) | full acceptance list §3.6 |
| 3 | MatForge AI bridge (mocked tests) | §3.4 pipeline tests green |
| 4 | StormKit sky/fog/state + 3 presets | state round-trip + render stats |
| 5 | StormKit precipitation + wind | GN frame-eval tests |
| 6 | StormKit wetness/snow injection + lightning + all presets | byte-level eject test, §4.6 |
| 7 | RuinFX Tier 1 + baking utility | §5.6 shader tests + bake test |
| 8 | RuinFX Tier 2 (dents, booleans w/ gate) | mesh-safety fixture suite |
| 9 | RuinFX Tier 3 fracture pipeline | headless sim test |
| 10 | Packaging, docs, demo .blends, final QA pass | fresh-Blender install test of all three zips |

Each gate: run `scripts/test.sh`, paste the summary into the phase's commit message, update CHANGELOG. If a gate fails twice in a row on the same root cause, stop and write an analysis in DECISIONS.md before attempting a third fix (no thrash loops).

## 7. DOCUMENTATION (part of "studio grade")
Per add-on: README with install steps (Extensions + legacy), quickstart GIF placeholders, every operator/property documented, known limitations section (be blunt: Eevee mask differences, boolean mesh requirements, fracture is baked), and a TROUBLESHOOTING.md. In-UI: every property gets a real tooltip (`description=`), not placeholder text.

## 8. RISK REGISTER (top 6 — mitigate, don't ignore)
1. **API drift** → compat layer + introspection habit + version gate at register.
2. **Injected-node corruption of user materials** → byte-level restore tests on tricky fixtures; override mode; skip-and-report over guess-and-break.
3. **UI freeze from AI calls** → threaded + timer polling, tested with simulated 30s latency.
4. **Viewport perf (fog + rain + snow geo)** → viewport/render density split, caps, perf warnings in UI.
5. **Boolean garbage on bad meshes** → validation gate, refuse loudly.
6. **Handler leaks / duplicate registration** → idempotent register/unregister, load_post-safe, tested.

## 9. KICKOFF PROMPT — paste this into Claude Code as the first message

> You are acting as a senior Blender pipeline TD and Python engineer. Read `BLENDER_ADDON_MASTER_PLAN.md` in full before writing any code — it is the authoritative spec for this project and its ground rules are non-negotiable (one add-on at a time, introspect API names before use, headless test after every feature, non-destructive + fully removable, no silent failures, undo support).
> Environment: Blender 5.1.2 is installed and on PATH as `blender` (verify with `blender --version`; if missing, tell me how to expose it). You cannot see the viewport — verify everything through headless runs, render statistics, and logs as described in §2.4.
> Begin with Phase 0 exactly as specified in §6. At each phase gate, run `scripts/test.sh`, show me the summary, and wait for my go before starting the next phase. Keep DECISIONS.md updated whenever you resolve an ambiguity. Work in small, tested, committed increments.


## 10. SESSION & CONTEXT WORKFLOW (how work resumes across chats)

The owner works in fresh Claude Code sessions — sometimes one per phase, sometimes one per add-on. **The repository is the memory, not the chat.** Therefore:

1. **On Phase 0, create `CLAUDE.md` at repo root** containing: "Read `BLENDER_ADDON_MASTER_PLAN.md` (authoritative spec) and `PROGRESS.md` (current state) before doing anything. Verify state by running `scripts/test.sh`, never by trusting the chat." Claude Code auto-loads CLAUDE.md every session.
2. **Maintain `PROGRESS.md`:** updated at every phase gate — current phase, what passed, what's next, open issues. A fresh session must be able to resume from PROGRESS.md alone.
3. **On every fresh session:** read CLAUDE.md → PROGRESS.md → run the test suite to confirm the recorded state is real → continue from the next incomplete phase. If tests contradict PROGRESS.md, fix that first.
4. Commit at every gate so any session can be rolled back cleanly.
