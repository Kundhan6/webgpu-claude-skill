"""Stage 2 Rig — pure constraint-graph planning (§8.2, §9). No bpy import.

Builds the full rig as plain data (RigPlan); bl/rig.py's job is only to
walk this plan and make the mechanical bpy calls (§5's core/bl split).

Two kinds of part deliberately do NOT get a real rigid body, to hold the
rig at "12–20 rigid parts, never more" (§3 rule 7) without literally
joining meshes (later stages Surface Deform *every original piece*
individually, §2.2 step 6 — they can't be merged):

- wheel hardware (calipers/rotors — find_wheel_hardware_parents(), the
  M5 rigging requirement flagged, not built, at the end of the M4.5
  session) is parented to its own wheel, not the chassis, so it moves
  with the wheel automatically and needs no rigid body of its own.
- every other UNKNOWN (or otherwise unclassified) part is parented to
  the chassis — "welded to the body", §12.1 step 4 — the same way.

Both are plain object parenting, not a rigid body FIXED constraint. §8.2's
"No part welding" refers specifically to v1's broken FIXED-constraint weld
(§1.1/§1.2: ~130 parts constrained together *and* colliding, which is what
actually exploded). Object parenting is a different mechanism entirely —
it's exactly how a part that "does not need to detach independently"
(§1.2's rule) stays joined without adding to the rigid body budget or the
no-collide pair count.
"""
from dataclasses import dataclass, field
from typing import Optional

from . import tuning
from .classify import PartDescriptor, PartRole, find_wheel_hardware_parents
from .geometry import extents, thin_axis, union_bbox
from .naming import AmbiguousNoColNameError, break_name, hinge_name, motor_name, nocol_name
from .pairs import generate_pairs

_WHEEL_ROLES = (PartRole.WHEEL_FL, PartRole.WHEEL_FR, PartRole.WHEEL_RL, PartRole.WHEEL_RR)
_REAR_WHEEL_ROLES = (PartRole.WHEEL_RL, PartRole.WHEEL_RR)  # §9.2: rear-wheel drive default
_BREAKABLE_ROLES = (
    PartRole.DOOR_L, PartRole.DOOR_R, PartRole.HOOD, PartRole.BOOT,
    PartRole.BUMPER_F, PartRole.BUMPER_R,
)

# §3 rule 7: "12–20 rigid parts. Never more." Not one of Rig's spec-numbered
# V-rules (V6–V9 don't cover part count — V5 already caps *total* scene
# parts at 25, at Prep), but non-negotiable all the same; checked here so a
# car whose every part happens to earn its own rigid body (no wheel
# hardware, no generic UNKNOWN to fold into parenting) still gets refused
# loudly instead of quietly building a 21+-part rig.
MAX_RIGID_PARTS = 20

# §8.2 step 5: "more than 5% of the car's length" is exploding.
EXPLOSION_THRESHOLD_FRACTION = 0.05


class RigPlanError(ValueError):
    """Raised by build_rig_plan() when the classified parts can't be
    rigged at all — no BODY/chassis found, no wheels detected, more than
    MAX_RIGID_PARTS rigid bodies required, or an ambiguous part name
    core/naming.py refuses to embed in a CF_NoCol_ name (Prep's V21
    should already have hard-stopped on this for every *car* part; this
    only additionally guards the user-supplied target/barrier object,
    which V21 never scans)."""


def _density_for_role(role: PartRole) -> float:
    if role == PartRole.BODY:
        return tuning.RIG_DENSITY_BODY
    if role in _WHEEL_ROLES:
        return tuning.RIG_DENSITY_WHEEL
    if role == PartRole.GLASS:
        return tuning.RIG_DENSITY_GLASS
    return tuning.RIG_DENSITY_PANEL  # breakable panels land here


def _bbox_volume(part: PartDescriptor) -> float:
    dx, dy, dz = extents(part.bbox_min, part.bbox_max)
    return max(dx, 0.0) * max(dy, 0.0) * max(dz, 0.0)


def _mass_for(part: PartDescriptor, role: PartRole) -> float:
    return max(_bbox_volume(part) * _density_for_role(role), tuning.RIG_MIN_MASS)


@dataclass(frozen=True)
class RigidBodySpec:
    part_name: str
    body_type: str          # 'ACTIVE' | 'PASSIVE'
    collision_shape: str    # 'CONVEX_HULL' | 'MESH' — never MESH on an ACTIVE body (V6)
    mass: float


@dataclass(frozen=True)
class HingeSpec:
    """§9.1: one per wheel."""
    name: str
    chassis: str
    wheel: str
    axis: int       # the wheel's thin bbox axis (§12.2) — the hinge axis
    pivot: tuple     # wheel centroid


@dataclass(frozen=True)
class MotorSpec:
    """§9.2: rear wheels only (rear-wheel drive default)."""
    name: str
    chassis: str
    wheel: str
    axis: int
    pivot: tuple


@dataclass(frozen=True)
class BreakSpec:
    """§9.3 / §12.6: one per breakable panel."""
    name: str
    chassis: str
    panel: str
    breaking_threshold: float


@dataclass(frozen=True)
class NoColSpec:
    """§9.4: one per overlapping rigid-part pair."""
    name: str
    a: str
    b: str


@dataclass(frozen=True)
class RigPlan:
    chassis: str
    car_length: float
    rigid_bodies: tuple = field(default_factory=tuple)
    hinges: tuple = field(default_factory=tuple)
    motors: tuple = field(default_factory=tuple)
    breaks: tuple = field(default_factory=tuple)
    nocols: tuple = field(default_factory=tuple)
    weld_to_chassis: tuple = field(default_factory=tuple)       # non-hardware UNKNOWN/other parts
    wheel_hardware_parent: dict = field(default_factory=dict)   # part name -> its wheel's part name

    @property
    def rigid_part_names(self) -> tuple:
        return tuple(rb.part_name for rb in self.rigid_bodies)


def build_rig_plan(
    descriptors,
    roles: dict,
    *,
    speed_kmh: float,
    panel_toughness: float,
    barrier_name: Optional[str] = None,
) -> RigPlan:
    """§8.2 in full, as pure data.

    `descriptors`: current PartDescriptor list (bl/extract.py, re-extracted
    at Rig time — Prep may have moved origins/geometry since classification
    first ran). If `barrier_name` is given, its descriptor must already be
    included here too.

    `roles`: part name -> PartRole, exactly what CF_Prep wrote to
    `obj["cf_role"]` (§8.1 step 5). Rig trusts that classification, it
    does not re-run classify() — a classification error is a separate,
    already-tracked problem (see CLAUDE.md), not something this stage
    re-derives or silently corrects.

    `barrier_name`: name of a user-supplied target_object already in the
    scene, or None. Auto-creating CF_Barrier when none is supplied is
    §8.4 CF_Drive's job (not built this session, M6+) — Rig only rigs a
    barrier that already exists; with barrier_name=None it builds a
    car-only rig, which is exactly what the 3-frame explosion test needs
    (§8.2 step 5: nothing is driving into anything at rest).
    """
    by_name = {d.name: d for d in descriptors}

    chassis = next((name for name, role in roles.items() if role == PartRole.BODY), None)
    if chassis is None or chassis not in by_name:
        raise RigPlanError("no BODY part found among the classified roles — cannot rig without a chassis")

    whole_min, whole_max = union_bbox([(d.bbox_min, d.bbox_max) for d in descriptors])
    car_length = max(extents(whole_min, whole_max))

    wheel_names = [name for name, role in roles.items() if role in _WHEEL_ROLES and name in by_name]
    if not wheel_names:
        raise RigPlanError("no wheels among the classified roles — cannot build §9.1/§9.2's hinges and motors")
    wheel_descs = [by_name[n] for n in wheel_names]
    wheel_axis = {n: thin_axis(extents(by_name[n].bbox_min, by_name[n].bbox_max)) for n in wheel_names}
    rear_wheel_names = [name for name in wheel_names if roles[name] in _REAR_WHEEL_ROLES]

    breakable_names = [name for name, role in roles.items() if role in _BREAKABLE_ROLES and name in by_name]
    glass_names = [name for name, role in roles.items() if role == PartRole.GLASS and name in by_name]

    unknown_names = [
        name for name, role in roles.items()
        if role not in _WHEEL_ROLES and role != PartRole.BODY
        and role not in _BREAKABLE_ROLES and role != PartRole.GLASS
        and name in by_name
    ]
    unknown_descs = [by_name[n] for n in unknown_names]
    hardware_parent = find_wheel_hardware_parents(unknown_descs, wheel_descs) if wheel_descs else {}
    weld_to_chassis = tuple(n for n in unknown_names if n not in hardware_parent)

    rigid_names = [chassis, *wheel_names, *breakable_names, *glass_names]
    if barrier_name is not None and barrier_name in by_name:
        rigid_names.append(barrier_name)

    if len(rigid_names) > MAX_RIGID_PARTS:
        raise RigPlanError(
            f"{len(rigid_names)} rigid part(s) requested, exceeding the {MAX_RIGID_PARTS}-part "
            f"budget (§3 rule 7): {rigid_names}"
        )

    rigid_bodies = []
    for name in rigid_names:
        if name == barrier_name:
            rigid_bodies.append(RigidBodySpec(name, "PASSIVE", "MESH", 1.0))
            continue
        part = by_name[name]
        role = roles[name]
        rigid_bodies.append(RigidBodySpec(name, "ACTIVE", "CONVEX_HULL", _mass_for(part, role)))

    hinges = tuple(
        HingeSpec(hinge_name(w), chassis, w, wheel_axis[w], by_name[w].centroid)
        for w in wheel_names
    )
    motors = tuple(
        MotorSpec(motor_name(w), chassis, w, wheel_axis[w], by_name[w].centroid)
        for w in rear_wheel_names
    )

    impact_speed_ms = speed_kmh / 3.6
    breaks = []
    for pname in breakable_names:
        mass = _mass_for(by_name[pname], roles[pname])
        base = mass * impact_speed_ms
        threshold = base * (0.15 + (1.2 - 0.15) * panel_toughness)  # §12.6: lerp(0.15, 1.2, panel_toughness)
        breaks.append(BreakSpec(break_name(pname), chassis, pname, threshold))

    physics_parts = [by_name[n] for n in rigid_names]
    nocols = []
    try:
        for a, b in generate_pairs(physics_parts):
            pair_a, pair_b = sorted((a, b))
            nocols.append(NoColSpec(nocol_name(pair_a, pair_b), pair_a, pair_b))
    except AmbiguousNoColNameError as exc:
        raise RigPlanError(str(exc)) from exc

    return RigPlan(
        chassis=chassis,
        car_length=car_length,
        rigid_bodies=tuple(rigid_bodies),
        hinges=hinges,
        motors=motors,
        breaks=tuple(breaks),
        nocols=tuple(nocols),
        weld_to_chassis=weld_to_chassis,
        wheel_hardware_parent=hardware_parent,
    )


# --- §8.2 step 5 / V8: the 3-frame explosion test ---------------------


@dataclass(frozen=True)
class ExplosionCheckResult:
    ok: bool
    max_displacement: float
    threshold: float
    offending: Optional[str] = None


def check_explosion(before: dict, after: dict, chassis_name: str, car_length: float,
                     threshold_fraction: float = EXPLOSION_THRESHOLD_FRACTION) -> ExplosionCheckResult:
    """§8.2 step 5 / V8: "step the scene 3 frames, measure the maximum
    displacement of any part relative to the chassis. If any part moved
    more than 5% of the car's length, the rig is exploding."

    `before`/`after`: part name -> (x, y, z) world position, sampled
    immediately before and after stepping N frames with nothing driving
    the car — every rigid part, chassis included.

    Measures displacement *relative to the chassis*: a chassis that
    itself settles slightly under gravity must not count against every
    other part as if the whole car had flown apart. The threshold is a
    fraction of the car's own length rather than a fixed distance — the
    same reasoning core/pairs.py's own margin uses: a fixed number is
    wrong for a toy car and a truck alike.
    """
    if chassis_name not in before or chassis_name not in after:
        raise ValueError(f"chassis {chassis_name!r} missing from the position samples")

    chassis_delta = tuple(after[chassis_name][i] - before[chassis_name][i] for i in range(3))
    threshold = threshold_fraction * car_length

    worst_name = None
    worst_mag = 0.0
    for name, before_pos in before.items():
        if name == chassis_name or name not in after:
            continue
        part_delta = tuple(after[name][i] - before_pos[i] for i in range(3))
        rel = tuple(part_delta[i] - chassis_delta[i] for i in range(3))
        mag = sum(c * c for c in rel) ** 0.5
        if mag > worst_mag:
            worst_mag = mag
            worst_name = name

    ok = worst_mag <= threshold
    return ExplosionCheckResult(
        ok=ok, max_displacement=worst_mag, threshold=threshold,
        offending=worst_name if not ok else None,
    )
