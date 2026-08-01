"""Tier A (§13) — pure core, no bpy. Covers core.geometry's AABB/symmetry
primitives that classify.py, pairs.py, and density.py are all built on.
"""
from crash_forge.core import geometry


def test_extents_and_centroid():
    assert geometry.extents((0, 0, 0), (2, 4, 6)) == (2, 4, 6)
    assert geometry.centroid((0, 0, 0), (2, 4, 6)) == (1, 2, 3)


def test_longest_and_thin_axis():
    ext = (4.5, 1.8, 1.2)  # a car: long on X, narrow on Z
    assert geometry.longest_axis(ext) == 0
    assert geometry.thin_axis(ext) == 2


def test_roundness_of_a_disc_like_wheel():
    # thin on Y (the hinge axis), roughly equal X/Z like a wheel viewed side-on
    ext = (0.65, 0.2, 0.65)
    assert geometry.thin_axis(ext) == 1
    r = geometry.roundness(ext, thin_axis_index=1)
    assert r == 1.0


def test_roundness_of_an_elongated_box_is_low():
    ext = (4.0, 0.3, 1.0)  # a door: thin on Y, but X and Z very different
    r = geometry.roundness(ext, thin_axis_index=1)
    assert r < 0.3


def test_sizes_agree_within_tolerance():
    assert geometry.sizes_agree(1.0, 1.1, tolerance=0.15) is True
    assert geometry.sizes_agree(1.0, 1.3, tolerance=0.15) is False


def test_sizes_agree_both_zero():
    assert geometry.sizes_agree(0.0, 0.0) is True


def test_overlaps_true_for_interpenetrating_boxes():
    assert geometry.overlaps((0, 0, 0), (1, 1, 1), (0.5, 0.5, 0.5), (1.5, 1.5, 1.5)) is True


def test_overlaps_false_for_disjoint_boxes():
    assert geometry.overlaps((0, 0, 0), (1, 1, 1), (5, 5, 5), (6, 6, 6)) is False


def test_overlaps_margin_catches_near_touching_boxes():
    a_min, a_max = (0, 0, 0), (1, 1, 1)
    b_min, b_max = (1.05, 0, 0), (2, 1, 1)  # 0.05 gap on X
    assert geometry.overlaps(a_min, a_max, b_min, b_max, margin=0.0) is False
    assert geometry.overlaps(a_min, a_max, b_min, b_max, margin=0.1) is True


def test_normalize_point_maps_body_bbox_to_unit_cube():
    body_min, body_max = (-2, -1, 0), (2, 1, 2)
    assert geometry.normalize_point((-2, -1, 0), body_min, body_max) == (0.0, 0.0, 0.0)
    assert geometry.normalize_point((2, 1, 2), body_min, body_max) == (1.0, 1.0, 1.0)
    assert geometry.normalize_point((0, 0, 1), body_min, body_max) == (0.5, 0.5, 0.5)


def test_normalize_point_zero_extent_axis_does_not_divide_by_zero():
    body_min, body_max = (0, 0, 0), (0, 2, 2)  # zero extent on X
    result = geometry.normalize_point((5, 1, 1), body_min, body_max)
    assert result[0] == 0.0


def test_union_bbox_encloses_all_parts():
    boxes = [
        ((0, 0, 0), (1, 1, 1)),
        ((-1, 2, 0), (0.5, 3, 1)),
    ]
    out_min, out_max = geometry.union_bbox(boxes)
    assert out_min == (-1, 0, 0)
    assert out_max == (1, 3, 1)


def test_union_bbox_empty_is_zero_box():
    assert geometry.union_bbox([]) == ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
