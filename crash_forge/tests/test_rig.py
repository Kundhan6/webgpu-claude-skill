"""Tier A (§13) — pure core, no bpy.

Stage 2 Rig (§8.2, §9, M5): build_rig_plan()'s constraint-graph decisions,
and the 3-frame explosion test's comparison math (§8.2 step 5 / V8).
bl/rig.py and ops/rig.py themselves are Tier C only (real bpy calls, real
frame stepping) — see CLAUDE.md's M5 report for the Blender verification
steps; nothing here can substitute for that.
"""
import dataclasses

import pytest

from crash_forge.core.classify import PartDescriptor, PartRole, classify, detect_forward_axis
from crash_forge.core.rig import (
    MAX_RIGID_PARTS,
    RigPlanError,
    build_connectivity_edges,
    build_rig_plan,
    check_connectivity,
    check_explosion,
)
from tests.car_fixture_builder import load_fixture

_SPEED_KMH = 60.0
_PANEL_TOUGHNESS = 0.5


def _classify_sedan():
    parts = load_fixture("sedan")
    forward_axis = detect_forward_axis(parts)
    classification = classify(parts, forward_axis)
    roles = {name: c.role for name, c in classification.items()}
    return parts, roles


def _build_sedan_plan():
    parts, roles = _classify_sedan()
    plan = build_rig_plan(parts, roles, speed_kmh=_SPEED_KMH, panel_toughness=_PANEL_TOUGHNESS)
    return parts, roles, plan


# --- build_rig_plan(): structure -----------------------------------------


def test_chassis_is_the_body_part():
    _, _, plan = _build_sedan_plan()
    assert plan.chassis == "Body"


def test_every_wheel_gets_a_hinge():
    _, roles, plan = _build_sedan_plan()
    wheel_names = {n for n, r in roles.items() if r in (
        PartRole.WHEEL_FL, PartRole.WHEEL_FR, PartRole.WHEEL_RL, PartRole.WHEEL_RR,
    )}
    assert len(wheel_names) == 4
    assert {h.wheel for h in plan.hinges} == wheel_names
    assert all(h.chassis == "Body" for h in plan.hinges)


def test_only_rear_wheels_get_motors():
    """§9.2: "Two motors rather than four" — rear-wheel drive default."""
    _, roles, plan = _build_sedan_plan()
    rear_names = {n for n, r in roles.items() if r in (PartRole.WHEEL_RL, PartRole.WHEEL_RR)}
    assert len(plan.motors) == 2
    assert {m.wheel for m in plan.motors} == rear_names


def test_hinge_and_motor_axis_is_the_wheel_thin_axis():
    """The sedan fixture's wheels are thin along Y (bbox_min/max span
    only 0.2 on Y, the full wheel_radius*2 on X and Z) — the hinge/motor
    axis must be 1 (Y), not guessed as the forward or vertical axis."""
    _, _, plan = _build_sedan_plan()
    assert all(h.axis == 1 for h in plan.hinges)
    assert all(m.axis == 1 for m in plan.motors)


def test_breakable_panels_are_doors_hood_boot_bumpers():
    _, _, plan = _build_sedan_plan()
    breakable_panels = {b.panel for b in plan.breaks if b.breakable}
    assert breakable_panels == {"Door_L", "Door_R", "Hood", "Boot", "Bumper_F", "Bumper_R"}
    assert all(b.chassis == "Body" for b in plan.breaks)


def test_glass_gets_its_own_rigid_body_and_a_non_breakable_attachment():
    """Glass gets a rigid body (§8.2 step 1) but §9 names no constraint
    that attaches it to anything -- a real gap the connectivity check
    caught: without an attachment, every glass panel was its own
    disconnected island. It gets the same FIXED chassis<->panel
    constraint every breakable panel gets, just with breakable=False --
    it must never detach as a whole panel through this mechanism (it
    shatters later, via a completely different one, §8.8)."""
    _, _, plan = _build_sedan_plan()
    glass_names = {"Glass_Windshield", "Glass_Rear"}
    rigid_names = set(plan.rigid_part_names)
    assert glass_names <= rigid_names

    glass_breaks = {b.panel: b for b in plan.breaks if b.panel in glass_names}
    assert set(glass_breaks) == glass_names
    for b in glass_breaks.values():
        assert b.breakable is False
        assert b.chassis == "Body"


def test_no_active_rigid_body_ever_uses_mesh_shape():
    """V6: "No active rigid body uses MESH shape" — built correctly from
    the start here, not fixed up after the fact."""
    _, _, plan = _build_sedan_plan()
    for rb in plan.rigid_bodies:
        if rb.body_type == "ACTIVE":
            assert rb.collision_shape == "CONVEX_HULL"


def test_chassis_mass_dominates():
    """§8.2 step 2: "Chassis dominates (~70% of total)." Loose check, not
    an exact percentage — this is tuned-not-verified (core/tuning.py),
    the same status as classify.py's own thresholds."""
    _, _, plan = _build_sedan_plan()
    chassis_mass = next(rb.mass for rb in plan.rigid_bodies if rb.part_name == plan.chassis)
    other_masses = [rb.mass for rb in plan.rigid_bodies if rb.part_name != plan.chassis]
    assert chassis_mass > max(other_masses)
    assert chassis_mass > sum(other_masses) * 0.5


def test_no_collide_pairs_generated_for_overlapping_rigid_parts():
    """§9.4 — the constraint v1 was missing. The sedan's wheels overlap
    the body's bbox margin (they sit right at its edge), so at least one
    pair must exist; every pair's two names must both be rigid parts."""
    _, _, plan = _build_sedan_plan()
    assert len(plan.nocols) > 0
    rigid_names = set(plan.rigid_part_names)
    for nc in plan.nocols:
        assert nc.a in rigid_names
        assert nc.b in rigid_names
        assert nc.a < nc.b  # canonical (sorted) order


def test_breaking_threshold_matches_the_12_6_formula():
    """§12.6: threshold = mass * (speed_kmh/3.6) * lerp(0.15, 1.2, panel_toughness)."""
    parts, roles = _classify_sedan()
    plan = build_rig_plan(parts, roles, speed_kmh=72.0, panel_toughness=0.0)
    door = next(p for p in parts if p.name == "Door_L")
    from crash_forge.core.rig import _mass_for
    expected_mass = _mass_for(door, roles["Door_L"])
    expected = expected_mass * (72.0 / 3.6) * 0.15  # panel_toughness=0.0 -> lerp floor
    actual = next(b.breaking_threshold for b in plan.breaks if b.panel == "Door_L")
    assert actual == pytest.approx(expected)


def test_rigid_part_count_within_budget():
    _, _, plan = _build_sedan_plan()
    assert len(plan.rigid_bodies) <= MAX_RIGID_PARTS


def test_no_body_part_raises():
    parts, roles = _classify_sedan()
    roles = {n: (PartRole.UNKNOWN if r == PartRole.BODY else r) for n, r in roles.items()}
    with pytest.raises(RigPlanError, match="BODY"):
        build_rig_plan(parts, roles, speed_kmh=_SPEED_KMH, panel_toughness=_PANEL_TOUGHNESS)


def test_no_wheels_raises():
    parts, roles = _classify_sedan()
    wheel_roles = (PartRole.WHEEL_FL, PartRole.WHEEL_FR, PartRole.WHEEL_RL, PartRole.WHEEL_RR)
    roles = {n: (PartRole.UNKNOWN if r in wheel_roles else r) for n, r in roles.items()}
    with pytest.raises(RigPlanError, match="wheel"):
        build_rig_plan(parts, roles, speed_kmh=_SPEED_KMH, panel_toughness=_PANEL_TOUGHNESS)


def test_more_than_max_rigid_parts_raises():
    """Every part forced into a rigid-body-worthy role — no wheel
    hardware, no generic UNKNOWN to fold into parenting — must still be
    refused past the §3 rule 7 budget rather than silently over-built."""
    body = PartDescriptor(name="Body", bbox_min=(-1, -1, 0), bbox_max=(1, 1, 1), centroid=(0, 0, 0.5), vert_count=100)
    roles = {"Body": PartRole.BODY}
    parts = [body]
    wheel_roles = [PartRole.WHEEL_FL, PartRole.WHEEL_FR, PartRole.WHEEL_RL, PartRole.WHEEL_RR]
    for i, role in enumerate(wheel_roles):
        name = f"Wheel_{i}"
        parts.append(PartDescriptor(name=name, bbox_min=(i, i, 0), bbox_max=(i + 0.3, i + 0.3, 0.3), centroid=(i, i, 0.15), vert_count=10))
        roles[name] = role
    # 20 extra breakable-role parts, each far apart so no-collide pairs
    # don't matter here -- pushes the total rigid count to 25, past MAX_RIGID_PARTS.
    for i in range(20):
        name = f"Panel_{i}"
        offset = 100 + i * 10
        parts.append(PartDescriptor(
            name=name, bbox_min=(offset, 0, 0), bbox_max=(offset + 1, 1, 1),
            centroid=(offset + 0.5, 0.5, 0.5), vert_count=10,
        ))
        roles[name] = PartRole.HOOD
    with pytest.raises(RigPlanError, match="rigid part"):
        build_rig_plan(parts, roles, speed_kmh=_SPEED_KMH, panel_toughness=_PANEL_TOUGHNESS)


# --- structural connectivity (reviewer correction) ------------------------
#
# The 3-frame rest test (zero gravity, nothing driving) can only catch a
# part the solver actively shoves apart -- it cannot catch a part that
# was never attached to anything at all. A wheel with no hinge to the
# chassis sits perfectly still in zero gravity and passes that check
# cleanly. This is a separate, pure-data check: build a graph from every
# constraint plus every parent link, assert one connected component.


def test_a_normally_built_sedan_is_one_connected_component():
    """build_rig_plan() calls check_connectivity() itself and raises if
    disconnected -- a successful call on the sedan fixture is already
    proof, but assert it directly too, not just by absence of an
    exception."""
    parts, roles, plan = _build_sedan_plan()
    result = check_connectivity(plan, roles.keys())
    assert result.ok
    assert result.component_count == 1
    assert result.isolated_parts == ()


def test_dropping_one_hinge_isolates_that_wheel_and_fails():
    """Verify direction 1: remove one edge, the graph must actually
    notice. A wheel with its hinge dropped has *no* other edge to
    anything (wheels don't weld to the body and aren't wheel hardware
    themselves), so it becomes its own single-part island."""
    parts, roles, plan = _build_sedan_plan()
    dropped_wheel = plan.hinges[0].wheel
    broken_plan = dataclasses.replace(plan, hinges=tuple(plan.hinges[1:]))

    result = check_connectivity(broken_plan, roles.keys())

    assert not result.ok
    assert result.component_count == 2
    assert result.isolated_parts == (dropped_wheel,)


def test_restoring_the_dropped_hinge_fixes_connectivity():
    """Verify direction 2: putting the same edge back must actually fix
    it, not just happen to still report ok from a stale assumption."""
    parts, roles, plan = _build_sedan_plan()
    dropped_wheel = plan.hinges[0].wheel
    broken_plan = dataclasses.replace(plan, hinges=tuple(plan.hinges[1:]))
    assert not check_connectivity(broken_plan, roles.keys()).ok  # sanity: it really was broken

    restored_plan = dataclasses.replace(broken_plan, hinges=plan.hinges)
    result = check_connectivity(restored_plan, roles.keys())

    assert result.ok
    assert result.isolated_parts == ()
    assert dropped_wheel in restored_plan.rigid_part_names  # still a rigid part, still connected


def test_a_second_body_labeled_part_is_orphaned_and_refused():
    """A genuine, currently-reachable gap, not a contrived one:
    build_rig_plan() only ever uses the *first* BODY-role part it finds
    as the chassis (`next(...)`). A second part also labeled BODY (a
    plausible classify() mistake) is excluded from every other bucket
    too -- `role != PartRole.BODY` is carved out of the UNKNOWN
    catch-all on purpose -- so it never gets a rigid body, never gets
    parented, and never gets any edge at all. It becomes a true,
    single-node island: exactly what this check exists to catch instead
    of silently building a rig with a part missing from it entirely."""
    parts, roles = _classify_sedan()
    extra_body = PartDescriptor(
        name="Body_Extra", bbox_min=(200, 200, 0), bbox_max=(201, 201, 1),
        centroid=(200.5, 200.5, 0.5), vert_count=50,
    )
    parts = list(parts) + [extra_body]
    roles = dict(roles)
    roles["Body_Extra"] = PartRole.BODY

    with pytest.raises(RigPlanError, match="connected"):
        build_rig_plan(parts, roles, speed_kmh=_SPEED_KMH, panel_toughness=_PANEL_TOUGHNESS)


def test_connectivity_edges_never_derived_from_nocols():
    """§9.4 no-collide constraints explicitly hold nothing
    (`enabled=False`) -- build_connectivity_edges() must source edges
    only from hinges/motors/breaks/parenting, never `plan.nocols`,
    regardless of how many no-collide pairs happen to exist between
    parts that are *also* structurally connected some other way (the
    sedan's Boot, for instance, legitimately has both: a break
    constraint holding it AND a no-collide pair stopping its overlapping
    convex hull from fighting the chassis' -- both true at once, neither
    proves the other). Checked directly: strip every real structural
    source out of a plan that still has no-collide pairs, and confirm
    zero edges come out."""
    _, _, plan = _build_sedan_plan()
    assert len(plan.nocols) > 0, "the sedan fixture must actually produce no-collide pairs for this test to mean anything"
    stripped = dataclasses.replace(
        plan, hinges=(), motors=(), breaks=(), weld_to_chassis=(), wheel_hardware_parent={},
    )
    assert build_connectivity_edges(stripped) == []


def test_barrier_is_excluded_from_connectivity_not_required_to_connect():
    """The barrier is meant to be its own island -- it's the external
    wall the car collides with, never attached to the car. Confirmed two
    ways: build_rig_plan() doesn't raise even though nothing attaches
    the barrier to anything, and the barrier never appears in
    isolated_parts (because it's outside car_part_names entirely, not
    because the assert was loosened to allow it)."""
    parts, roles = _classify_sedan()
    barrier = PartDescriptor(
        name="Target_Wall", bbox_min=(50, -5, 0), bbox_max=(51, 5, 3),
        centroid=(50.5, 0, 1.5), vert_count=8,
    )
    parts = list(parts) + [barrier]

    plan = build_rig_plan(
        parts, roles, speed_kmh=_SPEED_KMH, panel_toughness=_PANEL_TOUGHNESS, barrier_name="Target_Wall",
    )

    assert "Target_Wall" in plan.rigid_part_names
    result = check_connectivity(plan, roles.keys())  # roles never included the barrier
    assert result.ok
    assert "Target_Wall" not in result.isolated_parts


# --- wheel hardware parenting --------------------------------------------


def test_wheel_hardware_is_parented_to_its_wheel_not_the_chassis():
    parts, roles = _classify_sedan()
    fl_wheel_name = next(n for n, r in roles.items() if r == PartRole.WHEEL_FL)
    # A degenerate (zero-volume) caliper sitting exactly at the sedan's
    # real FL wheel centroid -- containment holds trivially, and this
    # mirrors the real car's confirmed brake-caliper shape (§_is_wheel_
    # hardware's docstring: "extents[0] == 0.0 exactly, 27-vert degenerate
    # flat discs").
    fl_wheel = next(p for p in parts if p.name == fl_wheel_name)
    caliper = PartDescriptor(
        name="Caliper_FL", bbox_min=fl_wheel.centroid, bbox_max=fl_wheel.centroid,
        centroid=fl_wheel.centroid, vert_count=27,
    )
    parts = list(parts) + [caliper]
    roles = dict(roles)
    roles["Caliper_FL"] = PartRole.UNKNOWN

    plan = build_rig_plan(parts, roles, speed_kmh=_SPEED_KMH, panel_toughness=_PANEL_TOUGHNESS)

    assert plan.wheel_hardware_parent.get("Caliper_FL") == fl_wheel_name
    assert "Caliper_FL" not in plan.weld_to_chassis
    assert "Caliper_FL" not in plan.rigid_part_names


def test_generic_unknown_part_is_welded_to_chassis():
    parts, roles = _classify_sedan()
    stray = PartDescriptor(
        name="Antenna", bbox_min=(50, 50, 50), bbox_max=(50.1, 50.1, 50.1),
        centroid=(50.05, 50.05, 50.05), vert_count=10,
    )
    parts = list(parts) + [stray]
    roles = dict(roles)
    roles["Antenna"] = PartRole.UNKNOWN

    plan = build_rig_plan(parts, roles, speed_kmh=_SPEED_KMH, panel_toughness=_PANEL_TOUGHNESS)

    assert "Antenna" in plan.weld_to_chassis
    assert "Antenna" not in plan.wheel_hardware_parent
    assert "Antenna" not in plan.rigid_part_names


# --- check_explosion(): §8.2 step 5 / V8 ----------------------------------


def test_car_at_perfect_rest_passes():
    before = {"Body": (0, 0, 0), "Wheel_FL": (1, 1, 0)}
    after = {"Body": (0, 0, 0), "Wheel_FL": (1, 1, 0)}
    result = check_explosion(before, after, "Body", car_length=4.0)
    assert result.ok
    assert result.max_displacement == 0.0
    assert result.offending is None


def test_chassis_settling_under_gravity_does_not_itself_count():
    """A part that moves *with* the chassis (same absolute delta) has
    zero displacement relative to it -- only independent motion counts."""
    before = {"Body": (0, 0, 1.0), "Wheel_FL": (1, 1, 0.5)}
    after = {"Body": (0, 0, 0.99), "Wheel_FL": (1, 1, 0.49)}  # both dropped 0.01 together
    result = check_explosion(before, after, "Body", car_length=4.0)
    assert result.ok
    assert result.max_displacement == pytest.approx(0.0, abs=1e-9)


def test_a_part_flying_off_independently_fails_and_is_named():
    before = {"Body": (0, 0, 0), "Wheel_FL": (1, 1, 0), "Door_L": (-1, 1, 0)}
    after = {"Body": (0, 0, 0), "Wheel_FL": (1, 1, 0), "Door_L": (-1, 5, 0)}  # Door_L shot sideways
    result = check_explosion(before, after, "Body", car_length=4.0)  # 5% of 4.0 = 0.2
    assert not result.ok
    assert result.offending == "Door_L"
    assert result.max_displacement == pytest.approx(4.0)


def test_displacement_exactly_at_threshold_passes():
    car_length = 4.0
    threshold = 0.05 * car_length
    before = {"Body": (0, 0, 0), "Wheel_FL": (0, 0, 0)}
    after = {"Body": (0, 0, 0), "Wheel_FL": (threshold, 0, 0)}
    result = check_explosion(before, after, "Body", car_length)
    assert result.ok


def test_displacement_just_over_threshold_fails():
    car_length = 4.0
    threshold = 0.05 * car_length
    before = {"Body": (0, 0, 0), "Wheel_FL": (0, 0, 0)}
    after = {"Body": (0, 0, 0), "Wheel_FL": (threshold + 1e-6, 0, 0)}
    result = check_explosion(before, after, "Body", car_length)
    assert not result.ok


def test_missing_chassis_raises():
    with pytest.raises(ValueError, match="Body"):
        check_explosion({"Wheel_FL": (0, 0, 0)}, {"Wheel_FL": (0, 0, 0)}, "Body", car_length=4.0)
