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
parts below classify() should now correctly reach for.
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

# Still open, reported per the reviewer's step-4 ordering rather than
# silently patched with an unrequested new threshold: with the glass-
# fallback skip and the wheel-hardware rule both applied, "Roof light
# bar_0" no longer reads as GLASS -- but it still isn't UNKNOWN either.
# It falls through to _classify_remaining_part() and happens to satisfy
# BOOT's structural test (high Z, planar, thin along the vertical axis,
# and — after the sign fix — correctly in the rear half) purely by
# geometric coincidence: a roof-mounted light bar is, by shape, thin and
# flat like a boot lid. "roof lights_0" narrowly avoids the same fate —
# its thinnest axis is Y (forward), not Z — a difference of 0.078m vs
# 0.082m in this data, not a robust distinction. xfail(strict=True) so
# this stays visible (not silently green) and so it starts failing loudly
# the moment someone fixes it without updating this marker.
_KNOWN_STILL_WRONG = {"Roof light bar_0"}


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


@pytest.mark.parametrize("part_name", sorted(set(REAL_CAR_EXPECTED_ROLES) - _KNOWN_STILL_WRONG))
def test_real_car_part_classifies_correctly(part_name):
    _parts, result = _classify_real_car()
    expected = REAL_CAR_EXPECTED_ROLES[part_name]
    actual = result[part_name].role
    assert actual == expected, f"{part_name}: expected {expected}, got {actual}"


@pytest.mark.xfail(strict=True, reason=(
    "Roof light bar_0 is confirmed not-glass (fixed) but now hits BOOT's "
    "structural test by geometric coincidence (high, planar, thin-along-"
    "vertical, and in the rear half) — not yet fixed, reported per the "
    "reviewer's step-4 ordering rather than patched with an unrequested "
    "new threshold."
))
def test_real_car_roof_light_bar_still_misclassified_as_boot_not_yet_fixed():
    _parts, result = _classify_real_car()
    assert result["Roof light bar_0"].role == PartRole.UNKNOWN


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
