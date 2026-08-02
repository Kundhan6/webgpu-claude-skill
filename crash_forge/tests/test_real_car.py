"""Tier A (§13) — pure core, no bpy.

tests/fixtures/real_car.json — real geometry from a Sketchfab "Crown
Victoria police car" .glb (Blender 5.1.2), dumped by tools/dump_car.py.
Ground truth roles below were hand-confirmed against the raw numbers
(centroids, extents, materials) by the reviewer, not assigned by this
codebase — this file never relabels them; it only asserts classify()
against them.

Every role below is either self-evident (BODY is the one huge part;
WHEEL_* from the artist's own Bk/Ft.L/R naming, cross-checked against
actual centroid positions once the forward-sign bug was understood) or
explained where it isn't (see the four "not obviously any existing role"
parts below). All 13 of 13 parts now classify correctly — the BOOT
rear-quarter fix (core/tuning.py::CLASSIFY_BOOT_REAR_EXTREME) closed the
one remaining miss ("Roof light bar_0", previously tracked here as a
strict xfail; that marker's own strict=True caught the fix working and
forced this file to be updated rather than silently going green).
"""
import pytest

from crash_forge.core.classify import PartRole, classify, detect_forward_axis

from .car_fixture_builder import load_fixture

# Confirmed forward_sign=-1 (nose at -Y) from real numbers: Body extents
# [2.48, 6.70, 1.74] -> Y is the length axis; the cabin (glass centroid
# y=+0.534, interior centroid y=+0.481) sits well behind the body centroid
# (y=+0.083), consistent with a front-engine car (cabin behind the engine
# bay) -- so +Y is rear, nose is -Y. The auto heuristic gets this wrong
# (resolves +1) because this car's glass is a single part spanning the
# whole cabin, not symmetric front+rear glass -- a genuinely different
# failure mode from the "glass at both ends ties to a default" case
# covered in test_forward_sign.py. Both are why an override exists.
REAL_CAR_FORWARD_SIGN = -1

REAL_CAR_EXPECTED_ROLES = {
    "CrownVic.Body_0": PartRole.BODY,
    "windows glass_0": PartRole.GLASS,
    "CrownVic.Wheel.Ft.L_0": PartRole.WHEEL_FL,
    "CrownVic.Wheel.Ft.R_0": PartRole.WHEEL_FR,
    "CrownVic.Wheel.Bk.L_0": PartRole.WHEEL_RL,
    "CrownVic.Wheel.Bk.R_0": PartRole.WHEEL_RR,
    # No PartRole fits an interior shell — §12.1 step 4's "anything else"
    # catch-all. Matches the earlier hand-verification's own "reasonable
    # — no interior role exists" call.
    "interior_0": PartRole.UNKNOWN,
    # Confirmed not glass by material (max_transmission=0.0) — an opaque
    # accessory housing, not a body panel. No dedicated role exists.
    # "Roof light bar_0" sits at fwd=0.465 (46.5% of the way from nose to
    # tail) — comfortably inside the old "rear half" BOOT test, which is
    # exactly why it used to be misclassified as BOOT; CLASSIFY_BOOT_REAR_EXTREME
    # (0.25, "rear quarter") now correctly excludes it. "roof lights_0"
    # never had this problem — its thinnest axis is Y (forward), not Z,
    # so it never matched BOOT's t_axis==vertical_axis requirement either
    # way, at any threshold.
    "Roof light bar_0": PartRole.UNKNOWN,
    "roof lights_0": PartRole.UNKNOWN,
    # Wheel hardware (brake calipers) — confirmed by construction: each
    # one's centroid sits inside its matching wheel's own bbox. Not a
    # door; no dedicated "wheel hardware" role exists, so this is the
    # same "anything else" UNKNOWN fallback as interior_0, applied for a
    # different, now structurally-detected reason (§3 rule 7-adjacent:
    # rigidly welded to the body is the correct downstream behavior for
    # hardware that shouldn't move independently of its wheel).
    "CrownVic.WheelBrake.Bk.L_0": PartRole.UNKNOWN,
    "CrownVic.WheelBrake.Bk.R_0": PartRole.UNKNOWN,
    "CrownVic.WheelBrake.Ft.L_0": PartRole.UNKNOWN,
    "CrownVic.WheelBrake.Ft.R_0": PartRole.UNKNOWN,
}

def _classify_real_car():
    parts = load_fixture("real_car")
    forward_axis = detect_forward_axis(parts)
    return parts, classify(parts, forward_axis, forward_sign_override=REAL_CAR_FORWARD_SIGN)


def test_real_car_forward_axis_detected_as_y():
    parts = load_fixture("real_car")
    assert detect_forward_axis(parts) == 1  # Y, per Body's own extents


def test_real_car_every_part_has_a_ground_truth_entry():
    """Guard against the fixture and the table silently drifting apart —
    a part added to one without the other should fail loudly, not just
    be skipped by the parametrized test below."""
    parts = load_fixture("real_car")
    assert {p.name for p in parts} == set(REAL_CAR_EXPECTED_ROLES.keys())


@pytest.mark.parametrize("part_name", sorted(REAL_CAR_EXPECTED_ROLES))
def test_real_car_part_classifies_correctly(part_name):
    _parts, result = _classify_real_car()
    expected = REAL_CAR_EXPECTED_ROLES[part_name]
    actual = result[part_name].role
    assert actual == expected, f"{part_name}: expected {expected}, got {actual}"


def test_real_car_no_part_classifies_as_a_door():
    """Finding 4: this car has zero separate door meshes. That must be a
    valid, warning-free outcome — nothing in classify() should need doors
    to exist, and (now that the wheel-hardware rule catches the brake
    calipers before the DOOR_L/R lateral-extreme fallback can) nothing on
    this real car should land on DOOR_L/DOOR_R at all."""
    _parts, result = _classify_real_car()
    door_roles = {PartRole.DOOR_L, PartRole.DOOR_R}
    doors = [name for name, c in result.items() if c.role in door_roles]
    assert doors == []


def test_real_car_wheel_hardware_rule_does_not_crash_on_degenerate_zero_extent_parts():
    """Finding 3's other half: the four brake calipers have extents[0]
    exactly 0.0 (27-vert degenerate flat discs). The structural
    wheel-hardware check is a pure bbox containment test (no division),
    so this never even risks the divide-by-zero findings 3 warned about
    — this test exists to keep it that way if the check is ever
    rewritten to use an aspect ratio instead."""
    _parts, result = _classify_real_car()  # must not raise
    for name in ("CrownVic.WheelBrake.Bk.L_0", "CrownVic.WheelBrake.Bk.R_0",
                 "CrownVic.WheelBrake.Ft.L_0", "CrownVic.WheelBrake.Ft.R_0"):
        assert result[name].role == PartRole.UNKNOWN
