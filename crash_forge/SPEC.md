# Crash Forge v2 — Operator & Architecture Spec

**Target:** Blender 5.x (5.2 LTS primary), Windows, single-user tool
**Author context:** Krish — solo, RTX 5070 Ti 16 GB, 64 GB RAM
**Status:** complete rewrite. v1 is abandoned, not refactored.

---

## 0. HOW TO USE THIS DOCUMENT

You are building a Blender add-on called **Crash Forge**. This document is the
complete brief. You do not have access to the conversation that produced it.

Read sections 1–4 before writing any code. They contain the failures of the
previous attempt and the rules that exist specifically to prevent them.

**Before you write a single operator, complete Stage 0 (§6).** It is not
optional. The previous build failed three times on assumptions about the
Blender API that were never checked.

**Your development environment has no Blender installed.** Everything in
`core/` must be testable with plain Python. Everything requiring `bpy` must be
runnable by the user on his workstation via a single reported command.

---

## 1. WHAT WENT WRONG IN V1 — DO NOT REPEAT

Three real, reproduced failures. Each has a rule attached.

### 1.1 Rigid body added to an Empty

```
Operator bpy.ops.rigidbody.object_add.poll() failed, context is incorrect
```

The rig used an Empty (`CF_CarRoot`) as the shared physics root. Blender's
rigid body system does not accept Empties.

**Wrong fix (v1 took it):** abandon the shared root and weld ~130 parts
together with FIXED constraints.
**Right fix:** the root is a real mesh object. If a shared root is needed at
all, use the `COMPOUND` collision shape — Blender has this exact primitive for
combining child shapes into one rigid body without constraints.
**Rule:** never assume an object type is accepted by a physics operator.
Probe it (§6).

### 1.2 Frame-1 explosion

~130 welded, overlapping parts were simultaneously constrained together *and*
colliding with each other. The constraint solver and the collision solver
fought on frame 1 and the car detonated.

Two compounding causes:
- `disable_collisions` on a constraint only affects **that constraint's two
  objects**. With 130 overlapping parts you would need thousands of pairs.
- Bullet is unstable with mesh-shape-vs-mesh-shape contacts at small scales.

**Rule:** the rig has **12–20 parts, not 130.** Anything that does not need to
detach independently stays joined. Every overlapping neighbour pair gets an
explicit no-collide constraint (§9).

### 1.3 Stale state made every retest meaningless

Re-running Setup built a new rig on top of the old wreckage — old
`CF_Weld_*` / `CF_Break_*` empties, orphaned rigid bodies, ~147 stale
keyframes. Reinstalling the add-on does not reset the scene.

**Critical detail v1 missed:** `scene.rigidbody_world.collection` and
`scene.rigidbody_world.constraints` are **separate collections from the
scene**. Deleting an object from the scene does *not* remove it from the rigid
body world. This is the classic leak and is very likely still present.

**Rule:** every stage is idempotent. A full `CF_Reset` (§8.10) is implemented
**first**, before any stage that creates anything.

### 1.4 The meta-failure

v1 was `bpy.ops` orchestration end to end, so nothing could be tested without
Blender, so bugs were only ever found by the user running it manually. See §5.

---

## 2. THE METHOD BEING AUTOMATED

This add-on automates a **proven manual workflow**, not a new technique. Do not
invent physics. Do not use Cloth. Do not use the 5.2 XPBD solver node. Do not
write a custom solver.

The technique is **Soft Body with Plasticity**, driven by a *pre-baked* rigid
body animation.

### 2.1 The critical structural property

**The rigid body simulation and the soft body simulation are SEQUENTIAL, never
simultaneous.**

```
  rigid body sim  →  BAKE TO KEYFRAMES  →  soft body sim reads the bake
```

Once the rigid body result is keyframes, it is frozen and cannot change. This
single ordering choice eliminates three whole classes of bug:

| Problem | Why it disappears |
|---|---|
| Cloth/soft body and Bullet are separate solvers | They never run together |
| No Python API for rigid body initial velocity | No kinematic→dynamic handoff exists |
| Impact detection tunnels at speed | Impact frame is read off baked f-curves, offline and exact |

### 2.2 The manual workflow, in order

1. Clean the car; separate into parts (wheels, doors, hood, bumper, glass)
2. Rig: hinge + motor on wheels, breakable FIXED on panels, no-collide pairs
3. Run rigid body sim; **bake to keyframes** (`bpy.ops.nla.bake`)
4. Build a **deform proxy**: duplicate body parts (not wheels), join, Remesh
5. Soft Body on the proxy with **Plasticity at max**; bake to point cache
6. **Surface Deform** every original piece onto the proxy
7. Glass: subdivide, separate inner region, Quick Explode particles

Step 6 is done **by hand** in the source tutorial, for every single piece, and
re-done whenever any mesh changes. **That is this add-on's primary reason to
exist.**

### 2.3 Known-good physics values

From the established lineage of this technique, cross-validated against the
source video:

```
Soft Body / Goal:     goal_default 0.8, goal_min 0.98, goal_max 1.0,
                      goal_spring 0.1, goal_friction 50 (max)
Soft Body / Edges:    plastic 100 (max), bend 10, use_edges True
Obstacle:             passive rigid body AND a Collision modifier — both
```

Two values in the source transcript are **transcription artifacts** and must
never be written literally:

- `goal = 8` is **0.8**. `goal_default` is clamped to `[0, 1]`; writing 8
  silently becomes 1.0, which pins every vertex to its goal and produces
  **zero deformation** — a failure that looks like broken code.
- `bending = 110` is **10**. `bend` is clamped well below 110.

---

## 3. NON-NEGOTIABLE RULES

1. **Probe, never assume.** Every `bpy` property, operator and enum value used
   is verified to exist on the running build at registration (§6).
2. **No silent clamping.** Every physics value is range-checked against its
   RNA definition before assignment. A clamp raises a visible warning.
3. **Pure core.** `core/` imports nothing from `bpy`, `bmesh` or `mathutils`.
4. **Idempotent stages.** Running any stage twice produces the same result as
   running it once.
5. **Reset first.** `CF_Reset` is implemented and passing before any creating
   stage is written.
6. **No `bpy.ops` where a data-API call exists.** Operators depend on context
   and are the main source of v1's failures. Where an operator is unavoidable,
   wrap it in `context.temp_override(...)` and check the return value.
7. **12–20 rigid parts. Never more.**
8. **Everything the add-on creates is tagged** with the custom property
   `["cf_generated"] = True` and prefixed `CF_`.
9. **Fully automatic.** The user supplies Car, Target, Speed. Nothing else.
   Everything else is derived (§12).
10. **Fail loud, fail early.** A stage that cannot guarantee a correct result
    reports and stops. It never produces a half-built rig.

---

## 4. ENVIRONMENT

| | |
|---|---|
| Blender | 5.2 LTS primary; must not hard-fail on 5.0/5.1 |
| Packaging | Extension — `blender_manifest.toml`. Also ship a legacy `bl_info` fallback path |
| Python | 3.13 (Blender 5.1+) |
| Dev sandbox | **No Blender.** `core/` tests run on plain CPython |
| Dependencies | stdlib only. No wheels, no numpy requirement in the shipped add-on |

Note: the Python API for accessing Geometry Nodes modifier properties changed
in 5.2. The "Smooth by Angle" auto-smooth is a **modifier**, not a mesh flag,
in 4.1+. Both matter in §8.6.

---

## 5. PACKAGE LAYOUT

```
crash_forge/
├── blender_manifest.toml
├── __init__.py              register/unregister only
├── core/                    ← ZERO bpy imports. 100% unit-tested.
│   ├── __init__.py
│   ├── geometry.py          AABB math, symmetry, roundness
│   ├── classify.py          part classification from AABB descriptors
│   ├── pairs.py             overlapping-neighbour pair generation
│   ├── impact.py            impact frame + vector from a transform track
│   ├── density.py           voxel size / shard count derivation
│   ├── ranges.py            RNA range table + clamp-with-warning
│   ├── naming.py            CF_ name generation and parsing
│   └── report.py            structured result/warning objects
├── bl/                      ← thin bpy layer. No decisions made here.
│   ├── probe.py             Stage 0 API probe
│   ├── scene.py             collection/rigidbody-world plumbing
│   ├── extract.py           bpy objects → core descriptors
│   ├── apply.py             core results → bpy state
│   └── caches.py            point cache bake/free
├── ops/                     one module per stage, §8
├── ui/
│   └── panel.py
└── tests/
    ├── test_*.py            pure-python, run anywhere
    └── fixtures/*.json      golden car descriptors
```

**The contract:** `bl/extract.py` converts Blender objects into plain
dataclasses. `core/` makes every decision using only those dataclasses.
`bl/apply.py` writes the decisions back. This is what makes the add-on
testable without Blender, and it is the single most important structural
difference from v1.

Example of the boundary:

```python
# core/classify.py — no bpy anywhere
@dataclass(frozen=True)
class PartDescriptor:
    name: str
    bbox_min: tuple[float, float, float]
    bbox_max: tuple[float, float, float]
    centroid: tuple[float, float, float]
    vert_count: int
    material_names: tuple[str, ...]
    max_transmission: float
    is_planar: bool

def classify(parts: list[PartDescriptor], forward_axis: int) -> dict[str, PartRole]:
    ...
```

---

## 6. STAGE 0 — API PROBE (build this first, ship it enabled)

`bl/probe.py`. Runs at add-on registration and again at the start of the
one-button pipeline. Writes a structured report to the console and to the
panel.

For every entry in the table below, verify existence and, for numeric
properties, read the actual min/max from the RNA definition via
`bl_rna.properties[name].hard_min / hard_max`.

| Check | What to verify |
|---|---|
| `bpy.ops.rigidbody.object_add` | exists; **which object types pass poll** — test MESH, EMPTY, CURVE |
| `bpy.ops.rigidbody.constraint_add` | exists |
| `RigidBodyConstraint.type` | enum contains FIXED, HINGE, MOTOR, GENERIC |
| `RigidBodyConstraint` | `use_breaking`, `breaking_threshold`, `disable_collisions`, `enabled`, `object1`, `object2` |
| motor properties | `use_motor_ang`, `motor_ang_target_velocity`, `motor_ang_max_impulse` — **names vary, confirm** |
| `RigidBodyObject.collision_shape` | enum contains `COMPOUND`, `CONVEX_HULL`, `MESH` |
| `scene.rigidbody_world` | `.collection`, `.constraints`, `.point_cache`, `.substeps_per_frame`, `.solver_iterations` |
| `SoftBodySettings` | `goal_default`, `goal_min`, `goal_max`, `goal_spring`, `goal_friction`, `plastic`, `bend`, `pull`, `push`, `damping`, `use_goal`, `use_edges`, `vertex_group_goal` — **record every hard_min/hard_max** |
| `bpy.ops.object.surfacedeform_bind` | exists; parameter name is `modifier` |
| `SurfaceDeformModifier` | `.target`, `.is_bound` |
| Remesh modifier | `.mode` enum contains `VOXEL`; `.voxel_size` |
| `bpy.ops.object.shade_auto_smooth` | exists; what it adds (modifier name) |
| `bpy.ops.nla.bake` | exists; accepts `bake_types={'OBJECT'}`, `visual_keying`, `clear_constraints` |
| `bpy.ops.object.quick_explode` | exists; parameter names |
| `bpy.ops.ptcache.bake` / `.free_bake_all` | exist |
| mesh attributes | `sharp_face`, `custom_normal` present/removable |

**Known ground truth to check the probe against** (verified from the Blender
Python API docs — if the probe disagrees, trust the probe and report):

```
plastic        int   [0, 100]
goal_friction  float [0, 50]
goal_spring    float [0, 0.999]
goal_min       float [0, 1]
goal_max       float [0, 1]
goal_default   float [0, 1]
pull           float [0, 0.999]
mass           float [0, 50000]
```

Any failed probe entry **disables the affected stage with a readable message**
rather than letting it fail mid-run.

**CONFIRMED (Stage 0 probe, Blender 5.1.2):** of the three types tested for
`rigidbody.object_add.poll()`, only **MESH** passes on this build — **CURVE
does not**. EMPTY was already established as rejected (§1.1); treat CURVE as
rejected too until a probe on another build says otherwise. Do not assume
SURFACE or FONT objects pass either — they were never in the probe's test
set and nothing in this document has verified them. §1.1's "Right fix" (the
shared root must be a real mesh object) holds regardless.

---

## 7. DATA MODEL & NAMING

### 7.1 Naming

```
CF_Proxy              the remeshed soft body deform object
CF_Barrier            auto-created target, if the user supplied none
CF_Hinge_<wheel>      wheel hinge constraint empty
CF_Motor_<wheel>      wheel motor constraint empty
CF_Break_<part>       breakable panel constraint empty
CF_NoCol_<a>__<b>     no-collide pair constraint empty
CF_RBW                rigid body world collection
CF_RBWC               rigid body world constraints collection
```

Every created object: `obj["cf_generated"] = True`, `obj["cf_stage"] = <int>`.

### 7.2 Scene state

A `PropertyGroup` on `Scene` named `crash_forge`:

```python
car_object       : PointerProperty(Object)     # user input 1
target_object    : PointerProperty(Object)     # user input 2 (optional)
speed_kmh        : FloatProperty(default=60)   # user input 3
crumple_detail   : IntProperty(1..10, default=5)
panel_toughness  : FloatProperty(0..1, default=0.5)
shard_density    : IntProperty(1..10, default=5)
enable_debris    : BoolProperty(default=False)

# derived / written by stages — never edited by the user
stage_completed  : IntProperty(default=0)
impact_frame     : IntProperty(default=-1)
impact_vector    : FloatVectorProperty(size=3)
original_state   : StringProperty()   # JSON snapshot for Reset
probe_report     : StringProperty()   # JSON
```

`stage_completed` is the gate. A stage's `poll()` requires
`stage_completed >= n-1`. Re-running stage *n* resets `stage_completed` to
`n` and invalidates everything downstream.

### 7.3 Part roles

```python
class PartRole(Enum):
    BODY, WHEEL_FL, WHEEL_FR, WHEEL_RL, WHEEL_RR,
    DOOR_L, DOOR_R, HOOD, BOOT, BUMPER_F, BUMPER_R,
    GLASS, MIRROR, UNKNOWN
```

---

## 8. STAGES

Ten stages. Stage 1 requires user input; **stages 2–9 run unattended from one
button.** Every stage is also individually runnable for debugging.

### 8.0 `CF_Reset` — build this FIRST

`crashforge.reset`

Must fully return the scene to its pre-Crash-Forge state. Order matters:

1. Free all point caches: rigid body world, every soft body, every particle
   system (`bpy.ops.ptcache.free_bake_all` with override; verify it returned
   `FINISHED`)
2. Remove every object with `["cf_generated"]` **from `scene.rigidbody_world.collection`
   and `.constraints` explicitly**, then from all scene collections, then
   `bpy.data.objects.remove(obj, do_unlink=True)`
3. Purge orphaned constraint empties whose `object1`/`object2` are `None`
4. On every original car part: clear `animation_data`, remove `CF_*` vertex
   groups, remove `CF_*` and Surface Deform modifiers, remove rigid body
   (`bpy.ops.rigidbody.object_remove` with override), clear `["cf_*"]` props
5. Restore transforms and parenting from `original_state` JSON
6. Reset `stage_completed = 0`

**Self-check:** after Reset, `len([o for o in bpy.data.objects if o.get("cf_generated")]) == 0`
**and** `scene.rigidbody_world.collection` contains no `CF_` objects. Assert both.

### 8.1 `CF_Prep`

`crashforge.prep`

1. Snapshot `original_state` — for every mesh object in the car hierarchy:
   name, matrix_world, parent, vert count, modifier names. JSON to scene prop.
2. **Validate the scene** (§11): unit scale, fps, frame range, applied scale.
   Fix what is safely fixable, warn on the rest, hard-stop on unit scale != 1.0.
3. Extract `PartDescriptor` list via `bl/extract.py`.
4. Determine the car's forward axis: longest bounding box dimension in local
   space; disambiguate front/rear by wheel-pair spacing (front pair is usually
   closer to the body's forward extreme).
5. Classify parts (§12.1). Write `obj["cf_role"]`.
6. **Clean geometry:** remove `sharp_face` and `custom_normal` attributes,
   then apply shade-auto-smooth. This fixes the shading corruption that
   appears after joining meshes.
7. Set each part's origin to its own centre of mass
   (`origin_set(type='ORIGIN_CENTER_OF_MASS')` with override).
8. Report the classification as one line: `Found 4 wheels, 2 doors, hood,
   bumper, 6 glass panels`. If confidence is low on any part, expose a
   dropdown override — this is a two-second confirmation, not manual work.

**Failure modes:** non-manifold parts (warn only — soft body runs on the
proxy, not these); a single joined mesh with no separable parts (hard stop
with instructions); non-uniform scale (hard stop, offer to apply).

### 8.2 `CF_Rig`

`crashforge.rig`

Build the full constraint graph from §9. No part welding. No compound root
unless the probe confirmed `COMPOUND` and the car has a genuine multi-mesh
chassis.

1. Add rigid bodies:
   - body/chassis: ACTIVE, `collision_shape='CONVEX_HULL'`
   - wheels: ACTIVE, `CONVEX_HULL`
   - panels (doors/hood/boot/bumper): ACTIVE, `CONVEX_HULL`
   - glass: ACTIVE, `CONVEX_HULL`, low mass
   - barrier: PASSIVE, `MESH` **and** a Collision modifier (§9.5)
   **Never `MESH` shape on an active body.** Bullet is unstable with
   mesh-vs-mesh contact.
2. Masses: derive from bounding volume × a per-role density constant. Chassis
   dominates (~70% of total). Write them explicitly; do not leave defaults.
3. Create constraints per §9, each on its own Empty in `CF_RBWC`.
4. Set `rigidbody_world.substeps_per_frame` ≥ 60 and `solver_iterations` ≥ 20.
   Blender exposes no CCD; substeps are the only defence against tunneling.
5. **Immediately verify:** step the scene 3 frames, measure the maximum
   displacement of any part relative to the chassis. If any part moved more
   than 5% of the car's length, the rig is exploding — **stop, report the
   offending pair, do not continue.** This single check would have caught v1's
   failure #2 automatically.

### 8.3 `CF_Glass_Prep` — must run BEFORE binding

`crashforge.glass_prep`

Topology changes invalidate Surface Deform binds. All mesh-changing glass work
happens here, before Stage 6.

1. Identify glass (§12.4).
2. For each glass panel: inset the face region, separate the inner section into
   `CF_Shards_<name>`, leaving a rim attached to the frame. A window that
   vanishes cleanly reads as fake; the rim is what sells it.
3. Subdivide the shard section; cut count from `shard_density` (§12.5).
4. Record final vertex counts into `obj["cf_vhash"]` for the bind guard.

### 8.4 `CF_Drive`

`crashforge.drive`

1. Position the car at a computed start offset so that it reaches the barrier
   at roughly 40% through the frame range at the requested speed.
2. If `target_object` is None, create `CF_Barrier` — a wall sized to 3× the
   car's width, placed on the forward axis.
3. Set the motor target velocity from `speed_kmh` and wheel radius:
   `omega = v / r` (rad/s). Convert km/h → m/s first.
4. Bake the rigid body world point cache over the frame range.
5. **Bake to keyframes:** `bpy.ops.nla.bake(..., bake_types={'OBJECT'},
   visual_keying=True, clear_constraints=False)` on every rigid part.
   Verify f-curves exist afterwards; if not, stop.
6. Remove rigid bodies from all parts **after** the bake — the animation is now
   authoritative and further physics would fight it.

### 8.5 `CF_Impact`

`crashforge.impact`

Pure-core work in `core/impact.py`, and therefore fully unit-testable without
Blender.

Input: a list of `(frame, position)` for the chassis, plus fps.

```
speed[f]  = |p[f] - p[f-1]| * fps
decel[f]  = speed[f-1] - speed[f]
impact_frame = argmax(decel) over frames where speed[f-1] > 0.5 * max(speed)
impact_vector = normalize(p[impact_frame-1] - p[impact_frame-2])
impact_speed  = speed[impact_frame-1]
```

Then:
1. Write `impact_frame`, `impact_vector` to scene state.
2. **Keyframe the motor constraints off** at `impact_frame`: `enabled = True`
   at `impact_frame - 1`, `enabled = False` at `impact_frame`. Without this the
   car keeps driving into and through the barrier.
3. Sanity: if `impact_frame` is within 5 frames of either end of the range, the
   collision probably never happened or happened instantly — report and stop.

This replaces v1's per-frame BVH overlap test entirely. There is no tunneling
risk because the motion is already baked; the analysis is offline and exact.

### 8.6 `CF_Deform`

`crashforge.deform`

1. Duplicate every body part **except wheels and glass**; join the duplicates
   into `CF_Proxy`.
2. Add a Remesh modifier, `mode='VOXEL'`, `voxel_size` from §12.5. Apply it.
   The voxel remesh produces a closed, evenly-tessellated volume — this is what
   makes the soft body stable.
3. Transfer the baked chassis animation to `CF_Proxy` (copy the f-curves, or
   parent to the chassis with `matrix_parent_inverse` set). The proxy must
   follow the crash exactly.
4. Add Soft Body with the §10 values, every one written through
   `core/ranges.py::clamped()`.
5. Optional crumple zones — see the warning in §10.2.
6. Barrier: ensure it has **both** a passive rigid body and a **Collision
   modifier**. These are separate systems; the rigid body alone is invisible to
   the soft body solver. This is the single most commonly missed step in the
   whole workflow.
7. Bake the soft body point cache to `frame_end`. Verify the cache reports as
   baked before proceeding.

**Self-check:** compare `CF_Proxy` vertex positions at `frame_end` against
frame 1. If the maximum displacement (excluding whole-body translation) is
below 1% of car length, **nothing deformed** — report as a failure with the
three likely causes: goal too high, no Collision modifier on the barrier, or
the proxy never reached the barrier.

### 8.7 `CF_Bind` — the centrepiece

`crashforge.bind`

This is the feature the whole add-on exists for. Doing this by hand for every
piece, and redoing it whenever any mesh changes, is what makes people abandon
this workflow.

For every original car piece (all parts except wheels):

1. Ensure the auto-smooth / "Smooth by Angle" modifier sits **above** (earlier
   in the stack than) the Surface Deform modifier. Wrong order produces
   corrupted shading. Reorder by index; do not assume a position.
2. Add a `SURFACE_DEFORM` modifier, `target = CF_Proxy`.
3. Bind: `bpy.ops.object.surfacedeform_bind(modifier=mod.name)` inside
   `context.temp_override(object=obj, active_object=obj, selected_objects=[obj])`.
4. Verify `mod.is_bound is True`. If not, record the piece and continue;
   report all failures together at the end.
5. Store `obj["cf_vhash"] = vert_count` and `obj["cf_bound_to"] = proxy_name`.

**`CF_Rebind` (`crashforge.rebind`):** iterate every bound piece, compare live
vert count against `cf_vhash`. For each mismatch, unbind → rebind → update the
hash. Report `Rebound 6 of 47 pieces`. Runs automatically at the start of
Stage 8 and can be invoked manually at any time.

**Bind failures to detect and name specifically:** proxy has zero vertices;
piece lies entirely outside the proxy volume; proxy has shape keys; piece has
zero vertices.

### 8.8 `CF_Glass_Sim`

`crashforge.glass_sim`

1. Run `CF_Rebind` first — glass prep may have changed vertex counts.
2. On each `CF_Shards_*`: Quick Explode → particle system.
3. **Lifetime** = `frame_end - impact_frame + 25`, computed, never defaulted.
   Shards despawning mid-shot is a known failure of the source workflow.
4. **Velocity set explicitly** from `impact_vector * impact_speed * 0.6`, plus
   a randomised spread. Do not rely on "inherit velocity" — it is documented as
   unreliable here, and Stage 5 already gives us the exact impact vector, so
   guessing is unnecessary.
5. Particle `frame_start = impact_frame`, `frame_end = impact_frame + 2`.
6. Bake.

### 8.9 `CF_Debris` (optional, default OFF)

Small chips and dust. Off by default because it multiplies bake time and is a
lighting/comp decision, not a physics one. If enabled, emit from the contact
region using `impact_frame` and `impact_vector`. Mantaflow smoke is explicitly
**out of scope** for v2 — it belongs in a separate pass.

### 8.10 `CF_Export`

`crashforge.export`

Targets Unreal Engine.

- **Deforming body** (anything with Surface Deform): Alembic `.abc`, imports as
  a Geometry Cache.
- **Rigid pieces** (wheels, detached panels): FBX with baked animation — far
  cheaper than a vertex cache.
- **Glass shards**: FBX baked transforms, or leave as a Niagara pass in UE.

Settings that must be written, not defaulted: scale 100 (metres →
centimetres), Forward `-Z`, Up `Y`, `Apply Scalings: FBX All`, and scene fps
matched to the target sequencer fps *before* export.

Warn if separated pieces lack a second material slot for inner faces — they
will import with the paint shader on their interiors.

---

## 9. CONSTRAINT GRAPH

Every constraint is a Blender Empty in `CF_RBWC`. Typical total for a car:
**roughly 25–40**, not 130.

### 9.1 Wheel hinges — 4

| | |
|---|---|
| Type | `HINGE` |
| object1 / object2 | chassis / wheel |
| Axis | the wheel's **thin** bounding-box axis (§12.2) |
| Pivot | wheel centroid |
| `disable_collisions` | **True** |

### 9.2 Wheel motors — 2 (rear-wheel drive default)

| | |
|---|---|
| Type | `MOTOR` |
| object1 / object2 | chassis / wheel |
| Angular motor | enabled; target velocity `omega = (speed_kmh / 3.6) / wheel_radius` |
| Max impulse | scaled from chassis mass; internal, not user-facing |
| `disable_collisions` | **True** |
| Animated | `enabled` keyed False at `impact_frame` (§8.5) |

Two motors rather than four — more stable, and more natural under braking.

### 9.3 Breakable panel constraints — one per detachable panel

| | |
|---|---|
| Type | `FIXED` |
| object1 / object2 | chassis / door, hood, boot, bumper |
| `use_breaking` | **True** |
| `breaking_threshold` | §12.6 |
| `disable_collisions` | **True** |

Holds panels shut until impact, then lets them tear off.

### 9.4 No-collide pairs — one per overlapping neighbour pair

**This is the constraint v1 was missing, and the direct cause of the frame-1
explosion.**

| | |
|---|---|
| Type | `FIXED` |
| object1 / object2 | the two overlapping parts |
| `enabled` | **False** — it must hold nothing |
| `disable_collisions` | **True** — this is its entire purpose |

Generated by `core/pairs.py`: for every pair of rigid parts whose AABBs overlap
(with a small margin), emit a pair. `disable_collisions` applies **only to the
two objects named in that constraint** — which is exactly why one shared
constraint cannot cover a whole car, and why a 130-part rig is unwinnable.

With 12–20 parts this is 15–30 pairs. `O(n²)` at n=20 is trivial.

### 9.5 The barrier — not a constraint, but the most-missed setup

| | |
|---|---|
| Rigid body | PASSIVE, `collision_shape='MESH'` |
| **Collision modifier** | **also required** — the soft body solver cannot see rigid bodies |
| Collision damping | 0.1 |
| Thickness outer | 0.02 |
| Ground plane friction | 0.0 |

---

## 10. PHYSICS VALUES

### 10.1 Baseline preset (proven — do not "improve" it)

| Property | Value | RNA range | Note |
|---|---|---|---|
| `use_goal` | True | — | |
| `goal_default` | **0.8** | [0, 1] | **not 8** — §2.3 |
| `goal_min` | 0.98 | [0, 1] | only meaningful with a vertex group |
| `goal_max` | 1.0 | [0, 1] | |
| `goal_spring` | 0.1 | [0, 0.999] | |
| `goal_friction` | 50 | [0, 50] | max — "goal damping to max" |
| `use_edges` | True | — | |
| `plastic` | **100** | [0, 100] **int** | max — this is what makes dents permanent |
| `bend` | **10** | probe it | **not 110** — §2.3 |
| `mass` | derived | [0, 50000] | |

`core/ranges.py` holds this table together with the ranges.
`clamped(prop, value)` returns the value plus a warning if it had to clamp.
**Every** assignment goes through it. A clamp is surfaced in the UI, never
swallowed.

### 10.2 Crumple zones — the one unproven addition

The source workflow uses **no** weight painting, so the whole car crushes
uniformly like a drinks can. `vertex_group_goal` lets us do better: stiff at
A/B pillars and firewall, soft at bumpers and fenders.

**This is an improvement over the reference, and therefore the most likely
thing to go wrong.** Implement it, but:

- default it **OFF**
- when on, widen `goal_min` to ~0.9 so the weights have room to act
- offer a one-click A/B against the baseline

Ship the baseline working first. Add crumple zones only once §8.6's self-check
passes reliably.

---

## 11. VALIDATION RULES

Derived from the reference workflow's own failure list plus v1's failures.
Each runs at a defined point and has a specific message.

| # | Check | When | Action |
|---|---|---|---|
| V1 | Unit scale == 1.0 | Prep | **Hard stop** — soft body is extremely scale-sensitive |
| V2 | Object scale applied, uniform | Prep | Hard stop; offer to apply |
| V3 | fps and frame range sane; end ≥ 250 | Prep | Warn; auto-extend cache end |
| V4 | `sharp_face` / `custom_normal` removed after joins | Prep | Auto-fix |
| V5 | Part count between 4 and 25 | Prep | **Hard stop above 25** — the v1 explosion guard |
| V6 | No active rigid body uses `MESH` shape | Rig | Auto-fix to `CONVEX_HULL` |
| V7 | Every overlapping pair has a no-collide constraint | Rig | Auto-generate |
| V8 | 3-frame explosion test | Rig | **Hard stop**, name the offending pair |
| V9 | Rigid body world collections contain only expected objects | Rig, Reset | Auto-clean |
| V10 | Baked f-curves exist on every rigid part | Drive | Hard stop |
| V11 | `impact_frame` not at either end of the range | Impact | Hard stop |
| V12 | Motor `enabled` keyed off at impact | Impact | Auto-fix |
| V13 | Barrier has **both** rigid body and Collision modifier | Deform | Auto-fix |
| V14 | Every physics value within RNA range | Deform | Clamp **and warn** |
| V15 | Proxy actually deformed (§8.6 self-check) | Deform | Hard stop with 3 named causes |
| V16 | Auto-smooth modifier above Surface Deform | Bind | Auto-fix by reorder |
| V17 | `is_bound` True on every piece | Bind | Report the failed list |
| V18 | Live vert count == `cf_vhash` | Bind, Glass Sim | Auto-rebind |
| V19 | Particle lifetime reaches `frame_end` | Glass Sim | Auto-fix |
| V20 | Nothing tagged `cf_generated` survives a Reset | Reset | Assert |

---

## 12. AUTO-DETECTION ALGORITHMS

All of this lives in `core/` and is unit-tested against JSON fixtures. No
`bpy` anywhere.

### 12.1 Part classification

Work in the car's local space with the forward axis resolved (§8.1.4).
Normalise all coordinates against the body bounding box so the rules are
scale-free.

1. **Wheels first** (§12.2); remove them from consideration.
2. **Glass** by material (§12.4); remove next.
3. Of what remains, the largest connected mesh by volume is `BODY`.
4. Remaining parts by normalised centroid:
   - forward extreme, low Z → `BUMPER_F`
   - rear extreme, low Z → `BUMPER_R`
   - high Z, forward half, broad and flat → `HOOD`
   - high Z, rear half, broad and flat → `BOOT`
   - lateral extreme (high |x|), mid Z, planar and vertical → `DOOR_L` / `DOOR_R`
   - anything else → `UNKNOWN` — kept rigid and welded to the body
5. Prefer name keywords when present (`door`, `hood`, `bonnet`, `bumper`,
   `wheel`, `tyre`, `glass`, `window`, `windshield`), case-insensitive — but
   **verify against geometry.** Never trust a name alone.
6. Emit a confidence score per part. Anything below threshold appears in the
   one-line confirmation.

### 12.2 Wheel detection

For each candidate part:
- `thin_axis` = the bbox axis with the smallest extent
- `roundness` = ratio of the other two extents (≈1.0 for a wheel)
- `low` = centroid Z within the bottom third of the car bbox
- `score = roundness_score * low_weight * size_plausibility`

Take the top 4 by score; require pairwise lateral symmetry and sizes agreeing
within 15%. Fewer than 4 confident wheels surfaces in the confirmation line
rather than being guessed.

`thin_axis` is the hinge axis for §9.1. Wheel radius = half the mean of the two
non-thin extents.

### 12.3 Forward axis

Longest bbox extent = length axis. Front vs rear: the wheel pair whose centroid
sits nearer a bbox extreme along that axis, combined with the presence of glass
in the upper-forward region. If still ambiguous, ask in the confirmation line.

### 12.4 Glass detection

In priority order:
1. Any material with Principled `Transmission` > 0.5, or blend mode BLEND with
   base-colour alpha < 0.9
2. Name keyword match
3. Thin planar geometry in the upper half of the car bbox

### 12.5 Derived densities

```
car_length   = bbox extent along the forward axis
voxel_size   = car_length / (30 + crumple_detail * 8)     # detail 1..10
shard_cuts   = 2 + shard_density                          # subdivision cuts
```

At `crumple_detail = 5` on a 4.5 m car, `voxel_size ≈ 0.064 m` — roughly a
70-voxel span. Comfortable on 16 GB VRAM / 64 GB RAM. Clamp `voxel_size` so the
proxy cannot exceed ~200k verts, and report when the clamp triggers.

### 12.6 Break thresholds

```
impact_speed_ms = speed_kmh / 3.6
base            = part_mass * impact_speed_ms
threshold       = base * lerp(0.15, 1.2, panel_toughness)
```

Blender's `breaking_threshold` is in impulse units and **needs empirical
calibration on the user's build.** Ship the formula, expose `panel_toughness`,
and log actual break frames in the run report so the constant can be tuned from
real results. Do not pretend this number is exact.

---

## 13. TEST PLAN — runs with no Blender installed

```
python -m pytest tests/ -v
```

**Tier A — pure core (target 100% coverage):**
- `test_classify.py` — golden fixtures: sedan, SUV, van, and a badly-named car
  where every object is `Cube.0NN`. Assert roles.
- `test_wheels.py` — 4 wheels found; 3-wheel and 5-wheel cases degrade
  gracefully rather than guessing.
- `test_pairs.py` — overlapping AABBs produce pairs, disjoint produce none,
  `n` parts never exceed `n*(n-1)/2` pairs.
- `test_impact.py` — synthetic speed curves: clean impact, no impact, impact on
  frame 1, gradual deceleration with no wall. Assert frame and stop conditions.
- `test_ranges.py` — `goal_default=8` clamps to 1.0 **and raises a warning**;
  `plastic=100` passes; `bend=110` clamps and warns. This test exists
  specifically because of the transcription artifacts in §2.3.
- `test_density.py` — voxel size never yields more than 200k verts.
- `test_naming.py` — round-trip name generation and parsing.

**Tier B — import and registration under a stubbed `bpy`:**
Stub `bpy`, `bmesh`, `mathutils` in `tests/stubs/`. Import the add-on for real,
call `register()` then `unregister()`, assert no leaked classes and no
exceptions. This catches the class of error that made v1 unloadable.

**Tier C — real Blender, run by the user, one command:**

```
"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" ^
    --background --python tests/blender_suite.py -- --out cf_report
```

Writes `cf_report.md` and `cf_report.json`; exits non-zero on any critical
failure. Contents: the Stage 0 probe results, then every stage run end-to-end
on a generated stand-in car (box body, four cylinders, two door planes) with
the §11 validations asserted. **Do not use `--factory-startup`** — extensions
will not load.

The user runs Tier C and pastes back `cf_report.md`. Design that report to be
complete enough to debug from on its own.

---

## 14. BUILD ORDER

Build in **risk order**, not numerical order. Every milestone ends with a
passing test.

| M | Deliverable | Done when |
|---|---|---|
| **M0** | Package skeleton, `blender_manifest.toml`, register/unregister, Tier B green | Add-on installs and enables cleanly |
| **M1** | Stage 0 probe + `core/ranges.py` + Tier A range tests | Probe report prints; §2.3 artifacts provably clamp with warnings |
| **M2** | **`CF_Reset`** | The §8.0 assert passes on a deliberately messy file |
| **M3** | `core/` detection modules + all Tier A tests | Tier A fully green with no Blender |
| **M4** | Stage 1 Prep | Classification line correct on a real car |
| **M5** | Stage 2 Rig + explosion test (V8) | Car sits still across frames 1–3 |
| **M6** | Stages 4–5 Drive + Impact | Impact frame matches visual inspection |
| **M7** | Stage 6 Deform | Proxy visibly dents and **stays dented** |
| **M8** | **Stage 7 Bind + Rebind** | 40+ pieces bound in one click; rebind after a topology change |
| **M9** | Stages 3 + 8 Glass | Shards fly with the right velocity on the right frame |
| **M10** | Stage 10 Export, one-button orchestrator, UI polish | Full run from three inputs |

**M2 comes before M4.** Reset must exist before anything creates state, or
every retest is contaminated — which is precisely how v1 wasted an entire
debugging cycle.

**Stop and report to the user after M5 and after M7.** Those are the two points
where the physics is either right or fundamentally wrong, and both need his
eyes on the viewport.

---

## 15. API RISK REGISTER

Ranked. Each has a probe (§6) and a fallback.

| Risk | Impact | Mitigation |
|---|---|---|
| Motor constraint property names differ from expectation | Rig stage dead | Probe names; fall back to enumerating `RigidBodyConstraint.bl_rna.properties` and matching on `motor` |
| `bpy.ops.nla.bake` signature changed in 5.x | Pipeline stops at Drive | Probe; fallback = per-frame `keyframe_insert` from a decomposed `matrix_world` |
| High-speed tunneling through the barrier | Car passes through | ≥60 substeps; V11 catches a missing impact; halve speed and retry once, then report |
| `breaking_threshold` units not as assumed | Panels never break, or break instantly | Log actual break frames; expose `panel_toughness`; calibrate from real runs |
| Soft body ignores the barrier | No deformation at all | V13 forces the Collision modifier; V15 catches the symptom |
| Surface Deform bind fails on pieces outside the proxy | Those pieces don't deform | Report per piece; suggest raising `crumple_detail` so the proxy encloses them |
| Auto-smooth is a GN modifier in 4.1+, and the GN modifier property API changed in 5.2 | Shading corruption or a crash on reorder | Probe what `shade_auto_smooth` adds; reorder by index only; never touch its internals |
| Point cache bake fails in background mode | Tier C can't test physics | Per-cache `ptcache.bake` with explicit override, ordered rigid body → soft body → particles |
| Voxel remesh blows memory on a dense car | Blender hangs | Clamp voxel size to the 200k-vert ceiling and report the clamp |

---

## 16. UI

One panel: `View3D > Sidebar > Crash Forge`.

```
┌─ Crash Forge ───────────────────┐
│  Car      [ ▾ Mustang        ]  │
│  Target   [ ▾ (auto wall)    ]  │
│  Speed    [ 60 km/h          ]  │
│                                 │
│      ╔═══════════════════╗      │
│      ║    CRASH IT       ║      │
│      ╚═══════════════════╝      │
│                                 │
│  ▸ Tuning                       │
│      Crumple Detail   [ 5 ]     │
│      Panel Toughness  [0.5]     │
│      Shard Density    [ 5 ]     │
│      Crumple Zones    [ ] off   │
│  ▸ Stages          (run singly) │
│  ▸ Report                       │
│      Rebind All   /   Reset     │
└─────────────────────────────────┘
```

**Three inputs, one button.** Everything under Tuning has a working default.
Everything under Stages exists for debugging, not normal use. Report shows the
probe results, the last run's warnings, and any clamped values.

Progress goes through `wm.progress_begin/update/end` plus
`self.report({'INFO'}, ...)` per stage, so a long bake never looks frozen.

---

## 17. DEFINITION OF DONE

- Tier A tests green with no Blender installed
- Tier B registration clean, no leaked classes
- Tier C report shows zero CRITICAL failures on the user's machine
- One click on a fresh car model produces: permanent deformation, panels that
  detach on impact, glass breaking on the correct frame, and **no manual
  binding at any point**
- `CF_Reset` returns the file to a state where the `cf_generated` count is zero
- Running the full pipeline twice in a row produces the same result

---

## APPENDIX A — WHAT THIS SPEC DELIBERATELY DOES NOT DO

Listed so they are not re-litigated mid-build:

- **No Cloth modifier.** Cloth is elastic and has no plasticity parameter.
- **No XPBD / Geometry Nodes solver.** Blender 5.2's XPBD solver node is
  genuinely interesting for this problem, but it is experimental and this
  add-on automates a workflow that already works. Revisit for v3.
- **No custom Python solver.** Unnecessary; Soft Body with plasticity is the
  established technique.
- **No simultaneous rigid-body/soft-body simulation.** See §2.1. This is the
  single most important architectural decision in the document.
- **No compound-welded multi-part chassis.** See §1.2.
- **No Mantaflow smoke.** Separate pass, separate tool.
- **No modal WASD drive recorder.** The car is driven by a motor constraint and
  a speed value; interactive driving is a v3 feature at best.
