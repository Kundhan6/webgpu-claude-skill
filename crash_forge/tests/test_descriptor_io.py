"""Tier A (§13) — pure core, no bpy.

core/descriptor_io.py is the writer-side half of "one schema, two
producers" (CLAUDE.md's M4 note): tools/dump_car.py and CF_Prep must
write JSON shaped identically so Krish can diff a real dump_car.py run
against what Prep extracted from the same car. This locks the schema key
set to what tools/dump_car.py::_describe() actually produces.
"""
import pytest

from crash_forge.core.classify import PartDescriptor
from crash_forge.core.descriptor_io import (
    dump_part_descriptors,
    load_part_descriptors,
    part_descriptor_from_dict,
    part_descriptor_to_dict,
)

# Exactly the key set tools/dump_car.py::_describe() writes — if either
# side ever drifts, this is the test that should catch it.
DUMP_CAR_SCHEMA_KEYS = {
    "name", "bbox_min", "bbox_max", "centroid", "extents",
    "vert_count", "material_names", "max_transmission", "is_planar",
}


def _sample_part():
    return PartDescriptor(
        name="Door_L",
        bbox_min=(0.0, -1.0, 0.5),
        bbox_max=(2.0, -0.9, 1.4),
        centroid=(1.0, -0.95, 0.95),
        vert_count=512,
        material_names=("Paint_Red", "Trim_Black"),
        max_transmission=0.0,
        is_planar=True,
    )


def test_to_dict_matches_dump_car_schema_key_set_exactly():
    d = part_descriptor_to_dict(_sample_part())
    assert set(d.keys()) == DUMP_CAR_SCHEMA_KEYS


def test_to_dict_derives_extents_from_bbox():
    d = part_descriptor_to_dict(_sample_part())
    assert d["extents"] == pytest.approx([2.0, 0.1, 0.9])


def test_round_trip_preserves_every_stored_field():
    original = _sample_part()
    restored = part_descriptor_from_dict(part_descriptor_to_dict(original))
    assert restored == original


def test_from_dict_ignores_extents_and_rederives_on_next_round_trip():
    """A dump_car.py JSON file *has* "extents" in it (dump_car.py always
    writes it). Loading must accept that key without choking, and the
    next dump must re-derive it fresh rather than ever trusting the
    stored copy — a real car's stored extents disagreeing with
    (bbox_max - bbox_min) should never silently propagate."""
    data = {
        "name": "Hood",
        "bbox_min": [0.0, 0.0, 0.0],
        "bbox_max": [1.0, 2.0, 3.0],
        "centroid": [0.5, 1.0, 1.5],
        "extents": [999.0, 999.0, 999.0],  # deliberately wrong / stale
        "vert_count": 100,
        "material_names": [],
        "max_transmission": 0.0,
        "is_planar": False,
    }
    part = part_descriptor_from_dict(data)
    re_dumped = part_descriptor_to_dict(part)
    assert re_dumped["extents"] == [1.0, 2.0, 3.0]


def test_missing_optional_fields_default_like_dump_car_py_never_omits_them():
    """material_names/max_transmission/is_planar are defensive defaults
    for hand-edited or older JSON — tools/dump_car.py itself always
    writes all of them, so this is a robustness net, not the expected
    shape of a real dump."""
    minimal = {
        "name": "Bumper_F",
        "bbox_min": [0.0, 0.0, 0.0],
        "bbox_max": [1.0, 1.0, 1.0],
        "centroid": [0.5, 0.5, 0.5],
        "vert_count": 10,
    }
    part = part_descriptor_from_dict(minimal)
    assert part.material_names == ()
    assert part.max_transmission == 0.0
    assert part.is_planar is False


def test_dump_part_descriptors_is_a_bare_list_not_wrapped():
    """Unlike original_state (§7.2's schema_version envelope),
    dump_car.py's own output is a bare JSON list — no wrapper object.
    CF_Prep's dump must match that exactly, not invent its own envelope."""
    dumped = dump_part_descriptors([_sample_part()])
    assert isinstance(dumped, list)
    assert len(dumped) == 1
    assert set(dumped[0].keys()) == DUMP_CAR_SCHEMA_KEYS


def test_load_part_descriptors_round_trips_a_whole_list():
    parts = [_sample_part(), PartDescriptor(
        name="Wheel_FL", bbox_min=(1.0, -1.0, 0.0), bbox_max=(1.7, -0.6, 0.7),
        centroid=(1.35, -0.8, 0.35), vert_count=800,
    )]
    loaded = load_part_descriptors(dump_part_descriptors(parts))
    assert loaded == parts
