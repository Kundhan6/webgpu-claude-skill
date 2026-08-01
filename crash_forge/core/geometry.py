"""AABB math, symmetry, roundness (§12). No bpy import.

Everything here is scale- and unit-agnostic — it works equally on raw
world-space bounding boxes or on the [0, 1]-normalised coordinates §12.1
calls for ("Normalise all coordinates against the body bounding box so
the rules are scale-free"). Normalisation itself lives here
(normalize_point) but callers decide when to apply it.
"""
from typing import Sequence

Vec3 = tuple


def extents(bbox_min: Sequence[float], bbox_max: Sequence[float]) -> tuple:
    """(dx, dy, dz) — the box's size along each axis."""
    return tuple(bbox_max[i] - bbox_min[i] for i in range(3))


def centroid(bbox_min: Sequence[float], bbox_max: Sequence[float]) -> tuple:
    return tuple((bbox_min[i] + bbox_max[i]) / 2.0 for i in range(3))


def longest_axis(ext: Sequence[float]) -> int:
    """Index of the longest extent — the car's length/forward axis (§8.1.4, §12.3)."""
    return max(range(3), key=lambda i: ext[i])


def thin_axis(ext: Sequence[float]) -> int:
    """Index of the smallest extent — a wheel's hinge axis (§12.2)."""
    return min(range(3), key=lambda i: ext[i])


def roundness(ext: Sequence[float], thin_axis_index: int) -> float:
    """Ratio (0..1] of the two non-thin extents; ~1.0 for a circular
    cross-section like a wheel, lower for anything elongated (§12.2)."""
    others = [ext[i] for i in range(3) if i != thin_axis_index]
    lo, hi = min(others), max(others)
    if hi <= 0:
        return 0.0
    return lo / hi


def sizes_agree(a: float, b: float, tolerance: float = 0.15) -> bool:
    """True if two magnitudes agree within a fractional `tolerance` of the
    larger one (§12.2: "sizes agreeing within 15%")."""
    a, b = abs(a), abs(b)
    bigger = max(a, b)
    if bigger == 0:
        return True
    return abs(a - b) / bigger <= tolerance


def overlaps(bbox_a_min, bbox_a_max, bbox_b_min, bbox_b_max, margin: float = 0.0) -> bool:
    """AABB overlap test with a small margin (§9.4) — each box is
    expanded by `margin` on every side before testing, so near-touching
    (not just interpenetrating) parts still count as overlapping."""
    for i in range(3):
        a_lo, a_hi = bbox_a_min[i] - margin, bbox_a_max[i] + margin
        b_lo, b_hi = bbox_b_min[i] - margin, bbox_b_max[i] + margin
        if a_hi < b_lo or b_hi < a_lo:
            return False
    return True


def normalize_point(point: Sequence[float], body_min: Sequence[float], body_max: Sequence[float]) -> tuple:
    """Map `point` into the body bbox's frame: 0 at body_min, 1 at
    body_max, on each axis independently (§12.1). A zero-extent axis maps
    everything on it to 0 rather than dividing by zero."""
    body_ext = extents(body_min, body_max)
    return tuple(
        (point[i] - body_min[i]) / body_ext[i] if body_ext[i] != 0 else 0.0
        for i in range(3)
    )


def union_bbox(boxes):
    """(min, max) bounding box enclosing every (bbox_min, bbox_max) pair
    in `boxes`. Used to derive a whole-car bbox from per-part descriptors
    when there's no single "body" bbox yet to normalise against."""
    boxes = list(boxes)
    if not boxes:
        return (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)
    mins = [b[0] for b in boxes]
    maxs = [b[1] for b in boxes]
    out_min = tuple(min(m[i] for m in mins) for i in range(3))
    out_max = tuple(max(m[i] for m in maxs) for i in range(3))
    return out_min, out_max
