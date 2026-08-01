"""Tier A (§13) — pure core, no bpy.

test_pairs.py: overlapping AABBs produce pairs, disjoint produce none, n
parts never exceed n*(n-1)/2 pairs.
"""
from collections import namedtuple

from crash_forge.core.pairs import generate_pairs

# A minimal stand-in for classify.PartDescriptor — pairs.py only needs
# .name/.bbox_min/.bbox_max, so this keeps the test independent of
# classify.py's shape.
Part = namedtuple("Part", ["name", "bbox_min", "bbox_max"])


def test_overlapping_parts_produce_a_pair():
    parts = [
        Part("A", (0, 0, 0), (1, 1, 1)),
        Part("B", (0.5, 0, 0), (1.5, 1, 1)),
    ]
    assert generate_pairs(parts) == [("A", "B")]


def test_disjoint_parts_produce_no_pairs():
    parts = [
        Part("A", (0, 0, 0), (1, 1, 1)),
        Part("B", (10, 10, 10), (11, 11, 11)),
    ]
    assert generate_pairs(parts) == []


def test_margin_catches_near_touching_parts():
    parts = [
        Part("A", (0, 0, 0), (1, 1, 1)),
        Part("B", (1.05, 0, 0), (2, 1, 1)),
    ]
    assert generate_pairs(parts, margin=0.0) == []
    assert generate_pairs(parts, margin=0.1) == [("A", "B")]


def test_each_part_named_at_most_once_per_pair_no_duplicates():
    parts = [
        Part("A", (0, 0, 0), (1, 1, 1)),
        Part("B", (0, 0, 0), (1, 1, 1)),
    ]
    pairs = generate_pairs(parts)
    assert pairs == [("A", "B")]
    assert ("B", "A") not in pairs


def test_pair_count_never_exceeds_n_choose_2():
    # 6 mutually-overlapping parts, all sharing the same box — worst case.
    parts = [Part(f"P{i}", (0, 0, 0), (1, 1, 1)) for i in range(6)]
    pairs = generate_pairs(parts)
    n = len(parts)
    assert len(pairs) <= n * (n - 1) // 2
    assert len(pairs) == n * (n - 1) // 2  # all overlap here, so it's exact


def test_twenty_parts_o_n_squared_is_trivial_and_bounded():
    parts = [Part(f"P{i}", (i * 10, 0, 0), (i * 10 + 1, 1, 1)) for i in range(20)]
    pairs = generate_pairs(parts)
    n = len(parts)
    assert len(pairs) <= n * (n - 1) // 2
    assert pairs == []  # spaced 10 apart, nothing overlaps


def test_single_part_produces_no_pairs():
    assert generate_pairs([Part("Solo", (0, 0, 0), (1, 1, 1))]) == []


def test_no_parts_produces_no_pairs():
    assert generate_pairs([]) == []
