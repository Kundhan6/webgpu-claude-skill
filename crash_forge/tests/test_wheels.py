"""Tier A (§13) — pure core, no bpy.

4 wheels found; 3-wheel and 5-wheel cases degrade gracefully rather than
guessing (§12.2: "Fewer than 4 confident wheels surfaces in the
confirmation line rather than being guessed").

detect_wheels' "bottom third" scoring is relative to the *whole car's*
bbox (matching how classify() actually calls it — step 1, before
anything else is removed), so these tests pass the full part list with
wheels added/removed/resized, not an isolated wheels-only list; a
wheels-only list has no "car" to be in the bottom third of.
"""
from crash_forge.core.classify import PartDescriptor, detect_wheels, find_wheel_hardware_parents
from crash_forge.core.geometry import centroid as bbox_centroid
from crash_forge.core.geometry import union_bbox

from .car_fixture_builder import load_fixture

LATERAL_AXIS = 1
VERTICAL_AXIS = 2


def _detect(parts):
    whole_min, whole_max = union_bbox((p.bbox_min, p.bbox_max) for p in parts)
    center = bbox_centroid(whole_min, whole_max)
    return detect_wheels(parts, lateral_axis=LATERAL_AXIS, vertical_axis=VERTICAL_AXIS, whole_center=center)


def test_four_wheels_found_with_high_confidence():
    car = load_fixture("sedan")
    wheels, confidence = _detect(car)
    assert {p.name for p in wheels} == {"Wheel_FL", "Wheel_FR", "Wheel_RL", "Wheel_RR"}
    assert confidence >= 0.8


def test_three_wheels_degrades_gracefully_not_guessed():
    car = [p for p in load_fixture("sedan") if p.name != "Wheel_RR"]  # one wheel missing
    wheels, confidence = _detect(car)
    assert wheels == []
    assert confidence == 0.0


def test_five_wheels_picks_the_four_real_ones():
    """A 5th wheel-like object (e.g. a roof-mounted spare, not at ground
    level) must not corrupt the real 4 — low_weight in the scoring
    formula suppresses anything outside the bottom third."""
    car = load_fixture("sedan") + [
        PartDescriptor(
            name="Wheel_Spare", bbox_min=(0.0, -1.5, 1.0), bbox_max=(0.7, -1.3, 1.7),
            centroid=(0.35, -1.4, 1.35), vert_count=800,
        )
    ]
    wheels, confidence = _detect(car)
    assert {p.name for p in wheels} == {"Wheel_FL", "Wheel_FR", "Wheel_RL", "Wheel_RR"}
    assert confidence >= 0.8


def test_zero_wheel_candidates_returns_empty_not_a_crash():
    wheels, confidence = _detect([])
    assert wheels == []
    assert confidence == 0.0


def test_non_wheel_shaped_parts_are_not_mistaken_for_wheels():
    car = [p for p in load_fixture("sedan") if p.name in ("Body", "Door_L", "Door_R")]
    wheels, confidence = _detect(car)
    assert wheels == []


def test_asymmetric_sizes_lower_confidence_even_at_four_candidates():
    """Four round, low candidates that don't actually pair up in size
    (one wheel much bigger than the rest) should not be reported with
    full confidence — the mismatch is real information, not noise to
    average away."""
    car = load_fixture("sedan")
    resized = []
    for p in car:
        if p.name == "Wheel_FL":
            cx = (p.bbox_min[0] + p.bbox_max[0]) / 2
            cy = (p.bbox_min[1] + p.bbox_max[1]) / 2
            big_r = 0.6  # well past the 15% size tolerance vs the other three (radius 0.35)
            resized.append(PartDescriptor(
                name=p.name, bbox_min=(cx - big_r, p.bbox_min[1], 0.0), bbox_max=(cx + big_r, p.bbox_max[1], big_r * 2),
                centroid=(cx, cy, big_r), vert_count=p.vert_count,
            ))
        else:
            resized.append(p)

    wheels, confidence = _detect(resized)
    assert {p.name for p in wheels} == {"Wheel_FL", "Wheel_FR", "Wheel_RL", "Wheel_RR"}
    assert confidence < 0.8


# --- find_wheel_hardware_parents() (public since M5) ----------------------
#
# §_is_wheel_hardware's bbox-containment test, exposed as its own signal
# instead of being folded into a blanket UNKNOWN role -- the "M5 rigging
# requirement, noted not built" from the M4.5 session: Stage 2 Rig needs
# to know *which* wheel a caliper/rotor belongs to, to parent it there
# instead of welding it to the body chassis.


def test_hardware_maps_to_the_wheel_that_contains_it():
    car = load_fixture("sedan")
    wheels, _confidence = _detect(car)
    fl = next(w for w in wheels if w.name == "Wheel_FL")
    rl = next(w for w in wheels if w.name == "Wheel_RL")

    caliper_fl = PartDescriptor(name="Caliper_FL", bbox_min=fl.centroid, bbox_max=fl.centroid, centroid=fl.centroid, vert_count=27)
    caliper_rl = PartDescriptor(name="Caliper_RL", bbox_min=rl.centroid, bbox_max=rl.centroid, centroid=rl.centroid, vert_count=27)

    mapping = find_wheel_hardware_parents([caliper_fl, caliper_rl], wheels)

    assert mapping == {"Caliper_FL": "Wheel_FL", "Caliper_RL": "Wheel_RL"}


def test_part_outside_every_wheel_is_not_mapped():
    car = load_fixture("sedan")
    wheels, _confidence = _detect(car)
    body = next(p for p in car if p.name == "Body")

    mapping = find_wheel_hardware_parents([body], wheels)

    assert mapping == {}


def test_no_wheels_gives_no_mapping_not_a_crash():
    caliper = PartDescriptor(name="Caliper", bbox_min=(0, 0, 0), bbox_max=(0, 0, 0), centroid=(0, 0, 0), vert_count=27)
    assert find_wheel_hardware_parents([caliper], []) == {}
