"""Voxel size / shard count derivation (§12.5). No bpy import.

    car_length   = bbox extent along the forward axis
    voxel_size   = car_length / (30 + crumple_detail * 8)     # detail 1..10
    shard_cuts   = 2 + shard_density                          # subdivision cuts

At crumple_detail=5 on a 4.5 m car, voxel_size ≈ 0.064 m (~70-voxel span).
`clamped_voxel_size` additionally enforces the ~200k-vert ceiling (§12.5,
risk register §15: "Voxel remesh blows memory on a dense car") and
reports when the clamp triggers — going through this the same
never-silently-clamp way core/ranges.py does for physics values, because
a voxel size chosen wrong has the same failure shape: it looks like
nothing went wrong until the bake hangs or the proxy comes out useless.
"""
import math
from dataclasses import dataclass
from typing import Optional

MAX_PROXY_VERTS = 200_000

# Order-of-magnitude estimate only: a voxel remesh's output vertex count
# scales roughly with the remeshed surface area divided by voxel_size², not
# with any exact formula Blender documents — this constant is a documented
# assumption (~2 verts per voxel-sized surface patch) pending calibration
# against a real remesh in Tier C, not a verified physical fact.
ASSUMED_VERTS_PER_VOXEL_AREA = 2.0


@dataclass(frozen=True)
class VoxelSizeResult:
    voxel_size: float
    clamped: bool
    warning: Optional[str] = None


def voxel_size_for_car(car_length: float, crumple_detail: int) -> float:
    """§12.5's base formula, no clamping."""
    return car_length / (30 + crumple_detail * 8)


def shard_cuts(shard_density: int) -> int:
    return 2 + shard_density


def estimate_voxel_vert_count(surface_area: float, voxel_size: float) -> int:
    """Order-of-magnitude vertex-count estimate for a voxel remesh at
    `voxel_size` over a surface of `surface_area` — see
    ASSUMED_VERTS_PER_VOXEL_AREA's caveat above."""
    if voxel_size <= 0:
        return 0
    return int(surface_area / (voxel_size ** 2) * ASSUMED_VERTS_PER_VOXEL_AREA)


def clamped_voxel_size(
    car_length: float,
    crumple_detail: int,
    surface_area: float,
    max_verts: int = MAX_PROXY_VERTS,
) -> VoxelSizeResult:
    """§12.5 voxel_size, clamped upward (coarser) if it would blow past
    `max_verts` on the estimated proxy. Never silently — a clamp always
    carries a warning, same contract as core/ranges.py::clamped()."""
    base = voxel_size_for_car(car_length, crumple_detail)
    if base <= 0 or surface_area <= 0:
        return VoxelSizeResult(base, False, None)

    estimated = estimate_voxel_vert_count(surface_area, base)
    if estimated <= max_verts:
        return VoxelSizeResult(base, False, None)

    # Solve for the voxel_size that puts the estimate exactly at max_verts:
    # verts ~= area / voxel_size^2 * k  =>  voxel_size = sqrt(area * k / max_verts)
    min_voxel_size = math.sqrt(surface_area * ASSUMED_VERTS_PER_VOXEL_AREA / max_verts)
    warning = (
        f"voxel_size {base!r} would produce an estimated {estimated} verts "
        f"(over the {max_verts}-vert ceiling); raised to {min_voxel_size!r}."
    )
    return VoxelSizeResult(min_voxel_size, True, warning)
