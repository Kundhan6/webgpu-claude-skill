"""Tier A (§13) — pure core, no bpy.

test_pairs.py: overlapping AABBs produce pairs, disjoint produce none, n
parts never exceed n*(n-1)/2 pairs. margin_fraction is relative to the
car's own length (§9.4's "a small margin" has no unit) — a fixed-distance
margin would break the moment the car is scaled, so these tests
specifically prove the same relative gap behaves identically at
different absolute scales.
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


def test_margin_fraction_catches_near_touching_parts():
    # Car (union bbox) spans 0..2 on X, so car_length=2; a 5% gap of 0.05
    # needs margin_fraction > 0.025 to close.
    parts = [
        Part("A", (0, 0, 0), (1, 1, 1)),
        Part("B", (1.05, 0, 0), (2, 1, 1)),
    ]
    assert generate_pairs(parts, margin_fraction=0.0) == []
    assert generate_pairs(parts, margin_fraction=0.05) == [("A", "B")]


def test_margin_fraction_is_scale_independent():
    """The same relative gap (5% of car length) must produce the same
    pairing result whether the car is modelled at 1x or 100x scale — a
    fixed-distance margin would only work at one scale."""

    def make_parts(scale):
        gap = 0.05 * scale  # 5% of a 1-unit-long "car" at this scale
        return [
            Part("A", (0, 0, 0), (1 * scale, 1 * scale, 1 * scale)),
            Part("B", (1 * scale + gap, 0, 0), (2 * scale, 1 * scale, 1 * scale)),
        ]

    for scale in (0.01, 1.0, 100.0):
        parts = make_parts(scale)
        assert generate_pairs(parts, margin_fraction=0.0) == [], f"scale={scale}"
        assert generate_pairs(parts, margin_fraction=0.06) == [("A", "B")], f"scale={scale}"


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
    assert pairs == []  # spaced 10 apart, nothing overlaps at the default small margin_fraction


def test_single_part_produces_no_pairs():
    assert generate_pairs([Part("Solo", (0, 0, 0), (1, 1, 1))]) == []


def test_no_parts_produces_no_pairs():
    assert generate_pairs([]) == []
