"""Tier A (§13) — pure core, no bpy.

Synthetic regression coverage for three of the four real-car findings
that landed alongside the forward-sign fix (test_real_car.py covers all
four against the real car itself; this file proves each holds in
isolation, not just for that one car):

  1. Lateral/forward positions are measured from the car's own bbox
     centre, never world origin — audited against the current code
     (already correct; whole_center is union_bbox(all parts), not (0,0,0))
     and locked in here with a car deliberately offset far from the
     origin.
  2. The glass planar/high-Z fallback is skipped once a confirmed
     transmissive material exists anywhere in the scene — and, just as
     importantly, still fires when no glass material exists at all (the
     case the fallback exists for in the first place).
  3. A part whose centroid sits inside a wheel's own bbox is wheel
     hardware (UNKNOWN), never a body panel — plus a divide-by-zero
     audit on a degenerate zero-extent part, since the real caliper data
     that motivated this rule has extents[0] == 0.0 exactly.

Finding 4 (zero doors is a valid, warning-free outcome) has no synthetic
angle beyond what's already true by construction — nothing in classify()
requires a door to exist — so it's only covered against the real car in
test_real_car.py.
"""
import pytest

from crash_forge.core.classify import (
    PartDescriptor,
    PartRole,
    _has_confirmed_glass_material,
    _is_glass,
    _is_wheel_hardware,
    classify,
    detect_forward_axis,
)
from crash_forge.core.geometry import roundness, sizes_agree

from .car_fixture_builder import load_fixture

_OFFSET = (500.0, -300.0, 50.0)


def _shift(part: PartDescriptor, offset=_OFFSET) -> PartDescriptor:
    def shift_point(p):
        return tuple(p[i] + offset[i] for i in range(3))

    return PartDescriptor(
        name=part.name, bbox_min=shift_point(part.bbox_min), bbox_max=shift_point(part.bbox_max),
        centroid=shift_point(part.centroid), vert_count=part.vert_count,
        material_names=part.material_names, max_transmission=part.max_transmission,
        is_planar=part.is_planar,
    )


# --- finding 1: measured from the car's own centre, never world origin ---


def test_wheel_roles_unaffected_by_a_car_far_from_world_origin():
    """The sedan fixture, translated 500/-300/50 units away from the
    origin. If anything computed a lateral/forward split against a fixed
    world-origin threshold instead of the car's own whole_center, this
    offset — far larger than the car itself — would corrupt every wheel
    role. It must classify identically to the un-shifted sedan."""
    original = load_fixture("sedan")
    shifted = [_shift(p) for p in original]

    forward_axis = detect_forward_axis(shifted)
    assert forward_axis == detect_forward_axis(original)

    result = classify(shifted, forward_axis)
    original_result = classify(original, detect_forward_axis(original))

    for part in shifted:
        assert result[part.name].role == original_result[part.name].role, part.name


# --- finding 2: glass-material-present skips the planar/high-Z fallback --


def _high_planar_part(name, max_transmission=0.0):
    """A part shaped exactly like the fallback wants: planar, sitting
    near the very top of the whole scene's bbox."""
    return PartDescriptor(
        name=name, bbox_min=(-0.1, -0.1, 1.9), bbox_max=(0.1, 0.1, 2.0),
        centroid=(0.0, 0.0, 1.95), vert_count=100, is_planar=True,
        max_transmission=max_transmission,
    )


def test_fallback_still_fires_when_no_real_glass_material_exists():
    """The case the fallback exists for: no part anywhere has a
    confirmed transmissive material, so a high, planar part is still the
    best available glass signal."""
    parts = [
        PartDescriptor(name="Body", bbox_min=(-2, -1, 0), bbox_max=(2, 1, 2), centroid=(0, 0, 1), vert_count=1000),
        _high_planar_part("Roof_Panel"),
    ]
    assert _has_confirmed_glass_material(parts) is False
    is_glass, _conf = _is_glass(parts[1], (-2, -1, 0), (2, 1, 2), vertical_axis=2, skip_fallback=False)
    assert is_glass is True


def test_fallback_is_skipped_once_a_confirmed_glass_material_exists_anywhere():
    """Confirmed on a real car: once real glass exists in the scene, a
    high/planar/opaque part (a light-bar housing, in reality) must not
    be guessed into GLASS by the fallback."""
    parts = [
        PartDescriptor(name="Body", bbox_min=(-2, -1, 0), bbox_max=(2, 1, 2), centroid=(0, 0, 1), vert_count=1000),
        PartDescriptor(name="Real_Glass", bbox_min=(1.5, -1, 1), bbox_max=(1.9, 1, 1.8),
                        centroid=(1.7, 0, 1.4), vert_count=200, max_transmission=0.9),
        _high_planar_part("Opaque_Roof_Accessory", max_transmission=0.0),
    ]
    assert _has_confirmed_glass_material(parts) is True

    is_glass, _conf = _is_glass(
        parts[2], (-2, -1, 0), (2, 1, 2), vertical_axis=2,
        skip_fallback=_has_confirmed_glass_material(parts),
    )
    assert is_glass is False


# --- finding 3: wheel hardware by bbox containment, plus a div-by-zero audit --


def _wheel(name, bbox_min, bbox_max, centroid):
    return PartDescriptor(name=name, bbox_min=bbox_min, bbox_max=bbox_max, centroid=centroid, vert_count=800)


def test_part_with_centroid_inside_a_wheel_bbox_is_wheel_hardware():
    wheel = _wheel("Wheel_FL", (0.3, -0.1, 0.0), (0.7, 0.1, 0.8), (0.5, 0.0, 0.4))
    caliper = PartDescriptor(
        name="Caliper_FL", bbox_min=(0.5, -0.05, 0.2), bbox_max=(0.5, 0.05, 0.6),
        centroid=(0.5, 0.0, 0.4), vert_count=27, is_planar=True,
    )
    assert _is_wheel_hardware(caliper, [wheel]) is True


def test_part_with_centroid_outside_every_wheel_bbox_is_not_wheel_hardware():
    wheel = _wheel("Wheel_FL", (0.3, -0.1, 0.0), (0.7, 0.1, 0.8), (0.5, 0.0, 0.4))
    door = PartDescriptor(
        name="Door_L", bbox_min=(-0.5, -1.1, 0.6), bbox_max=(0.5, -0.9, 1.4),
        centroid=(0.0, -1.0, 1.0), vert_count=500, is_planar=True,
    )
    assert _is_wheel_hardware(door, [wheel]) is False


def test_wheel_hardware_rule_reclassifies_a_caliper_end_to_end():
    """Same shape as the real car's brake calipers: a zero-width
    (extents[0]==0.0) degenerate disc, planar, sitting inside its
    wheel's bbox. Must land on UNKNOWN, not fall through to the
    DOOR_L/R lateral-extreme heuristic the way it did before this rule
    existed."""
    body = PartDescriptor(name="Body", bbox_min=(-2, -1, 0), bbox_max=(2, 1, 2), centroid=(0, 0, 1), vert_count=6000)
    wheels = [
        PartDescriptor(name=f"Wheel_{i}", bbox_min=(x - 0.35, y - 0.1, 0.0), bbox_max=(x + 0.35, y + 0.1, 0.7),
                        centroid=(x, y, 0.35), vert_count=800)
        for i, (x, y) in enumerate([(1.6, -1.0), (1.6, 1.0), (-1.6, -1.0), (-1.6, 1.0)])
    ]
    caliper = PartDescriptor(
        name="Caliper_FL", bbox_min=(1.6, -0.95, 0.2), bbox_max=(1.6, -0.85, 0.5),
        centroid=(1.6, -0.9, 0.35), vert_count=27, is_planar=True,
    )
    parts = [body, caliper] + wheels

    forward_axis = detect_forward_axis(parts)
    result = classify(parts, forward_axis)

    assert result["Caliper_FL"].role == PartRole.UNKNOWN


def test_degenerate_zero_extent_part_does_not_crash_geometry_helpers():
    """Guards the specific concern raised alongside finding 3: the real
    caliper data has extents[0] == 0.0 exactly. Every aspect-ratio /
    thinness calculation these parts could reach must already tolerate
    that (roundness and sizes_agree both explicitly guard hi<=0 /
    bigger==0) rather than raising ZeroDivisionError."""
    zero_extent = (0.0, 0.4, 0.39)  # extents[0] == 0.0, exactly like the real calipers
    assert roundness(zero_extent, thin_axis_index=0) == pytest.approx(0.39 / 0.4)
    assert sizes_agree(0.0, 0.0) is True  # both-zero radii must not raise either
    assert roundness((0.0, 0.0, 0.0), thin_axis_index=0) == 0.0  # every extent zero: no crash


# --- BOOT: rear extremity, not just "rear half" -----------------------


def _sedan_with_extra_part(extra: PartDescriptor):
    return load_fixture("sedan") + [extra]


def test_a_high_planar_part_near_the_middle_of_the_car_is_not_boot():
    """The exact shape of the real bug: a roof-mounted accessory (high Z,
    planar, thin along the vertical axis — indistinguishable from a boot
    lid on those three tests alone) sitting at fwd=0.46 (comfortably
    inside the old "rear half" test, nowhere near a real boot lid's rear
    extremity) must not be classified as BOOT."""
    parts = load_fixture("sedan")
    body = next(p for p in parts if p.name == "Body")
    bx0, bx1 = body.bbox_min[0], body.bbox_max[0]
    fwd_046_x = bx0 + 0.46 * (bx1 - bx0)  # 46% of the way from rear to nose along X

    light_bar_like = PartDescriptor(
        name="Roof_Accessory", bbox_min=(fwd_046_x - 0.3, -0.1, 1.9), bbox_max=(fwd_046_x + 0.3, 0.1, 2.0),
        centroid=(fwd_046_x, 0.0, 1.95), vert_count=500, is_planar=True,
    )
    car = _sedan_with_extra_part(light_bar_like)
    forward_axis = detect_forward_axis(car)

    result = classify(car, forward_axis)

    assert result["Roof_Accessory"].role != PartRole.BOOT


def test_a_high_planar_part_at_the_true_rear_extremity_is_still_boot():
    """The other half of the same fix: a part shaped exactly like the
    sedan fixture's own real Boot (rear-quarter, high, planar, thin
    vertical) must still classify as BOOT — the tightened threshold
    excludes the middle-of-the-car false positive without also excluding
    a genuine boot lid."""
    parts = load_fixture("sedan")
    boot = next(p for p in parts if p.name == "Boot")
    assert classify(parts, detect_forward_axis(parts))["Boot"].role == PartRole.BOOT
    # Sanity: this only means something because Boot is actually
    # positioned near the rear extremity in this fixture, not by luck.
    assert boot.centroid[0] < 0
