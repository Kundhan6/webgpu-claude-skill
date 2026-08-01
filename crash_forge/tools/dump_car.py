"""dump_car.py — standalone PartDescriptor dumper for a real car.

Not part of the Crash Forge add-on: does NOT import crash_forge, and
crash_forge does not import this. Run it directly inside Blender against
your own car mesh, get back one JSON file shaped exactly like
core.classify.PartDescriptor, and turn that into a real golden fixture by
hand — this script only dumps geometry and material data, it never
guesses at part roles. That labelling is yours to do by reading the JSON
back over.

Usage:
    1. In Blender, select the car's root object (or every part — either
       way, the full hierarchy under whatever's selected is walked, so
       selecting just one root empty/collection-parent is enough).
    2. Scripting tab -> open this file -> Run Script (or ▶).
       Or from a terminal: blender.exe --background --python dump_car.py
       (background mode only works if the .blend was saved with the
       right objects already selected — there's no viewport to select in).
    3. The output path is printed to the console/Info log when it's done.
       Paste that JSON back to have it become a real fixture.

Every material lookup is wrapped in try/except and getattr(): the
Principled BSDF's transmission input has been renamed across Blender
versions (e.g. "Transmission" -> "Transmission Weight"), so this searches
input socket names for the substring "transmission" rather than
hardcoding either one — and any node-tree shape this script doesn't
expect degrades to max_transmission=0.0 instead of crashing the dump.
"""
import json
import os
import tempfile

import bpy
from mathutils import Vector

# A part counts as "planar" if its thinnest world-space bbox dimension is
# below this fraction of its largest — same kind of thin-vs-flat call
# core/classify.py's roundness/thin_axis logic makes, just computed here
# from real geometry instead of a synthetic fixture. Tunable; not from
# the spec.
PLANAR_THIN_RATIO = 0.15


def _world_bbox(obj):
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    xs = [c.x for c in corners]
    ys = [c.y for c in corners]
    zs = [c.z for c in corners]
    bbox_min = (min(xs), min(ys), min(zs))
    bbox_max = (max(xs), max(ys), max(zs))
    return bbox_min, bbox_max


def _material_names(obj):
    try:
        return tuple(
            slot.material.name
            for slot in getattr(obj, "material_slots", [])
            if getattr(slot, "material", None) is not None
        )
    except Exception:
        return ()


def _transmission_of(material):
    """Best-effort Principled BSDF transmission value for one material.
    Never raises: any lookup failure just contributes 0.0."""
    try:
        if material is None or not getattr(material, "use_nodes", False):
            return 0.0
        node_tree = getattr(material, "node_tree", None)
        if node_tree is None:
            return 0.0
        for node in getattr(node_tree, "nodes", []):
            if getattr(node, "type", None) != "BSDF_PRINCIPLED":
                continue
            for socket in getattr(node, "inputs", []):
                name = (getattr(socket, "name", "") or "").lower()
                if "transmission" not in name:
                    continue
                value = getattr(socket, "default_value", None)
                if isinstance(value, (int, float)):
                    return float(value)
    except Exception:
        pass
    return 0.0


def _max_transmission(obj):
    try:
        materials = [slot.material for slot in getattr(obj, "material_slots", [])]
    except Exception:
        return 0.0
    values = [_transmission_of(m) for m in materials if m is not None]
    return max(values) if values else 0.0


def _collect_meshes(roots):
    seen = {}

    def walk(obj):
        if obj.name not in seen:
            seen[obj.name] = obj
            for child in obj.children:
                walk(child)

    for root in roots:
        walk(root)

    return [obj for obj in seen.values() if obj.type == "MESH"]


def _describe(obj):
    bbox_min, bbox_max = _world_bbox(obj)
    extents = tuple(bbox_max[i] - bbox_min[i] for i in range(3))
    centroid = tuple((bbox_min[i] + bbox_max[i]) / 2.0 for i in range(3))

    nonzero_extents = [e for e in extents if e > 0]
    is_planar = bool(nonzero_extents) and (min(extents) / max(extents) < PLANAR_THIN_RATIO if max(extents) > 0 else False)

    try:
        vert_count = len(obj.data.vertices)
    except Exception:
        vert_count = 0

    return {
        "name": obj.name,
        "bbox_min": list(bbox_min),
        "bbox_max": list(bbox_max),
        "centroid": list(centroid),
        "extents": list(extents),
        "vert_count": vert_count,
        "material_names": list(_material_names(obj)),
        "max_transmission": _max_transmission(obj),
        "is_planar": is_planar,
    }


def _output_path():
    if bpy.data.filepath:
        directory = os.path.dirname(bpy.data.filepath)
    else:
        directory = tempfile.gettempdir()
    return os.path.join(directory, "crash_forge_car_dump.json")


def main():
    roots = list(bpy.context.selected_objects)
    if not roots:
        print("dump_car.py: nothing selected — select the car's root object "
              "(or every part) in the viewport first, then run this again.")
        return

    meshes = _collect_meshes(roots)
    if not meshes:
        print(f"dump_car.py: {len(roots)} object(s) selected, but no MESH "
              f"objects found in their hierarchy. Nothing to dump.")
        return

    descriptors = [_describe(obj) for obj in meshes]

    out_path = _output_path()
    with open(out_path, "w") as f:
        json.dump(descriptors, f, indent=2)

    print(f"dump_car.py: wrote {len(descriptors)} part descriptor(s) to {out_path}")


if __name__ == "__main__":
    main()
