"""Overlapping-neighbour pair generation (§9.4). No bpy import.

This is the constraint v1 was missing, and the direct cause of the
frame-1 explosion (§1.2): `disable_collisions` on a rigid body constraint
only applies to *that constraint's two objects*, so every overlapping
pair needs its own no-collide constraint. At 12–20 parts (§3 rule 7) this
is O(n²) and trivially cheap — the bug was never the algorithm, it was
running it on 130 parts instead of 20.
"""
from itertools import combinations

from .geometry import overlaps


def generate_pairs(parts, margin: float = 0.0):
    """For every pair of parts whose AABBs overlap (expanded by `margin`),
    emit a pair. `parts`: iterable of objects with `.name`, `.bbox_min`,
    `.bbox_max` (e.g. classify.PartDescriptor). Returns a list of
    (name_a, name_b) tuples, each part named at most once per pair, and
    never both (a, b) and (b, a) for the same pair.

    For n parts this never exceeds n*(n-1)/2 pairs (§13) — combinations()
    already guarantees that structurally, since it enumerates each
    unordered pair exactly once.
    """
    parts = list(parts)
    result = []
    for a, b in combinations(parts, 2):
        if overlaps(a.bbox_min, a.bbox_max, b.bbox_min, b.bbox_max, margin=margin):
            result.append((a.name, b.name))
    return result
