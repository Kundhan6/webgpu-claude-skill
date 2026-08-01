"""PartDescriptor <-> plain-dict JSON, in the exact schema
tools/dump_car.py already writes. No bpy import.

Two independent producers write this schema: tools/dump_car.py (run by
hand inside Blender, geometry and materials only, never guesses at part
roles) and CF_Prep (§8.1, M4 — runs automatically as part of the
pipeline, also classifies). Krish can diff CF_Prep's dump against a
tools/dump_car.py dump of the same car precisely because both use this
one schema — see CLAUDE.md's M4 report for how.

dump_car.py deliberately does not import crash_forge (and crash_forge
does not import it — it must stay a fully standalone script), so this
module cannot reuse its code, only mirror its output shape exactly.
"""
from .classify import PartDescriptor
from .geometry import extents as _extents


def part_descriptor_to_dict(part: PartDescriptor) -> dict:
    """Matches tools/dump_car.py::_describe()'s dict shape key-for-key,
    including "extents" — PartDescriptor doesn't store that field, so
    it's derived here fresh from bbox_min/bbox_max, exactly like
    dump_car.py derives its own copy fresh from the live mesh."""
    return {
        "name": part.name,
        "bbox_min": list(part.bbox_min),
        "bbox_max": list(part.bbox_max),
        "centroid": list(part.centroid),
        "extents": list(_extents(part.bbox_min, part.bbox_max)),
        "vert_count": part.vert_count,
        "material_names": list(part.material_names),
        "max_transmission": part.max_transmission,
        "is_planar": part.is_planar,
    }


def part_descriptor_from_dict(data: dict) -> PartDescriptor:
    """Inverse of part_descriptor_to_dict(). "extents" is accepted (a
    dump_car.py JSON file has it) but ignored on the way in — it's
    derived, not stored, so a round trip re-derives it rather than
    trusting a second copy of the same information to stay consistent."""
    return PartDescriptor(
        name=data["name"],
        bbox_min=tuple(data["bbox_min"]),
        bbox_max=tuple(data["bbox_max"]),
        centroid=tuple(data["centroid"]),
        vert_count=data["vert_count"],
        material_names=tuple(data.get("material_names", ())),
        max_transmission=data.get("max_transmission", 0.0),
        is_planar=data.get("is_planar", False),
    )


def dump_part_descriptors(parts) -> list:
    """A whole PartDescriptor list -> the same bare-list JSON shape
    tools/dump_car.py writes (`json.dump(descriptors, f, indent=2)` — no
    wrapper object, no schema_version envelope; unlike original_state
    (§7.2), dump_car.py's output was never given a version envelope, so
    CF_Prep's writer doesn't invent one either — same schema means same
    shape, not a superset of it)."""
    return [part_descriptor_to_dict(p) for p in parts]


def load_part_descriptors(data: list) -> list:
    """Inverse of dump_part_descriptors() — parses a dump_car.py-shaped
    JSON list back into PartDescriptor objects."""
    return [part_descriptor_from_dict(d) for d in data]
