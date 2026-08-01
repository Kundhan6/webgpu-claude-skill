"""Tier A (§13) — pure core, no bpy. Voxel size never yields more than
200k estimated verts; shard_cuts derivation.
"""
from crash_forge.core.density import (
    MAX_PROXY_VERTS,
    clamped_voxel_size,
    estimate_voxel_vert_count,
    shard_cuts,
    voxel_size_for_car,
)


def test_voxel_size_matches_spec_worked_example():
    # §12.5: "At crumple_detail=5 on a 4.5m car, voxel_size ≈ 0.064m"
    voxel_size = voxel_size_for_car(car_length=4.5, crumple_detail=5)
    assert abs(voxel_size - 0.0642857) < 1e-4


def test_shard_cuts_formula():
    assert shard_cuts(5) == 7
    assert shard_cuts(1) == 3
    assert shard_cuts(10) == 12


def test_small_car_low_detail_does_not_clamp():
    result = clamped_voxel_size(car_length=4.5, crumple_detail=5, surface_area=20.0)
    assert result.clamped is False
    assert result.warning is None
    assert result.voxel_size == voxel_size_for_car(4.5, 5)


def test_extreme_detail_on_a_huge_car_clamps_and_warns():
    # Very high crumple_detail => very small voxel_size => huge vert count
    # on a large surface area, forcing the ceiling to kick in.
    result = clamped_voxel_size(car_length=50.0, crumple_detail=10, surface_area=50000.0)
    assert result.clamped is True
    assert result.warning is not None
    assert "200" in result.warning or str(MAX_PROXY_VERTS) in result.warning


def test_clamp_never_exceeds_max_verts():
    result = clamped_voxel_size(car_length=50.0, crumple_detail=10, surface_area=50000.0)
    assert result.clamped is True
    estimated = estimate_voxel_vert_count(5000.0, result.voxel_size)
    assert estimated <= MAX_PROXY_VERTS


def test_zero_surface_area_does_not_crash_or_clamp():
    result = clamped_voxel_size(car_length=4.5, crumple_detail=5, surface_area=0.0)
    assert result.clamped is False


def test_estimate_voxel_vert_count_zero_voxel_size_is_zero():
    assert estimate_voxel_vert_count(100.0, 0.0) == 0


def test_voxel_size_increases_with_crumple_detail_decreasing():
    # Higher crumple_detail => finer (smaller) voxel_size.
    coarse = voxel_size_for_car(4.5, crumple_detail=1)
    fine = voxel_size_for_car(4.5, crumple_detail=10)
    assert fine < coarse
