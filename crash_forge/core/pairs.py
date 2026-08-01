"""Overlapping-neighbour pair generation (§9.4). No bpy import.

This is the constraint v1 was missing, and the direct cause of the
frame-1 explosion (§1.2): `disable_collisions` on a rigid body constraint
only applies to *that constraint's two objects*, so every overlapping
pair needs its own no-collide constraint. At 12–20 parts (§3 rule 7) this
is O(n²) and trivially cheap — the bug was never the algorithm, it was
running it on 130 parts instead of 20.
"""
from itertools import combinations

from . import tuning
from .geometry import extents, overlaps, union_bbox


def generate_pairs(parts, margin_fraction: float = tuning.PAIRS_DEFAULT_MARGIN_FRACTION):
    """For every pair of parts whose AABBs overlap (expanded by a margin),
    emit a pair. `parts`: iterable of objects with `.name`, `.bbox_min`,
    `.bbox_max` (e.g. classify.PartDescriptor). Returns a list of
    (name_a, name_b) tuples, each part named at most once per pair, and
    never both (a, b) and (b, a) for the same pair.

    `margin_fraction` is a fraction of the *car's own length* (§9.4 says
    "a small margin" with no number or unit), not a fixed distance — a
    fixed margin breaks the moment the car is scaled: too small for a
    giant truck (misses real touching neighbours), too large for a toy-
    scale model (falsely merges parts that don't actually touch). The
    absolute margin is derived fresh from the union bbox of `parts` on
    every call, so it always tracks whatever's actually passed in.

    For n parts this never exceeds n*(n-1)/2 pairs (§13) — combinations()
    already guarantees that structurally, since it enumerates each
    unordered pair exactly once.
    """
    parts = list(parts)
    if len(parts) < 2:
        return []

    boxes = [(p.bbox_min, p.bbox_max) for p in parts]
    whole_min, whole_max = union_bbox(boxes)
    car_length = max(extents(whole_min, whole_max))
    margin = margin_fraction * car_length

    result = []
    for a, b in combinations(parts, 2):
        if overlaps(a.bbox_min, a.bbox_max, b.bbox_min, b.bbox_max, margin=margin):
            result.append((a.name, b.name))
    return result
