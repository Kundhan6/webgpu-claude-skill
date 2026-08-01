"""bl/extract.py — bpy objects -> core/ dataclasses (§5's contract). No
decisions made here: core/ decides what a value means, this module only
reads bpy state and hands back plain data.

The PartDescriptor-building logic mirrors tools/dump_car.py's _describe()
closely and on purpose — dump_car.py is deliberately standalone (does not
import crash_forge, and crash_forge does not import it, per its own
docstring), so this is a second, independent copy of the same read
logic, not a shared one. If dump_car.py's extraction logic changes, this
has to change with it by hand, or CF_Prep's dump stops being diffable
against a real dump_car.py run on the same car.
"""
import math

import bpy
from mathutils import Vector

from ..core.classify import PartDescriptor
from ..core.validate import ObjectScaleInfo, SceneMeta

# Mirrors tools/dump_car.py's PLANAR_THIN_RATIO exactly, for the same
# reason as the module docstring above.
PLANAR_THIN_RATIO = 0.15

# obj.scale component tolerance for "is this actually (1,1,1)" / "are
# these three components actually equal" — not a classify.py-style tuned
# threshold, just floating-point slack for values that should be exact.
_SCALE_EPSILON = 1e-4


def _world_bbox(obj):
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    xs = [c.x for c in corners]
    ys = [c.y for c in corners]
    zs = [c.z for c in corners]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


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
    Never raises: any lookup failure just contributes 0.0. Matches
    dump_car.py's own reasoning — the input has been renamed across
    Blender versions ("Transmission" -> "Transmission Weight"), so this
    searches for the substring rather than hardcoding either name."""
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


def _collect_meshes(root):
    seen = {}

    def walk(obj):
        if obj.name not in seen:
            seen[obj.name] = obj
            for child in obj.children:
                walk(child)

    walk(root)
    return [obj for obj in seen.values() if obj.type == "MESH"]


def collect_car_parts(car_object):
    """§8.1: "for every mesh object in the car hierarchy" — the car's
    root object (mesh or not) down to every mesh in its hierarchy.
    Insertion order is stable so downstream output (the classification
    report, the descriptor dump) doesn't reorder run to run on an
    unchanged scene."""
    return _collect_meshes(car_object)


def extract_part_descriptor(obj) -> PartDescriptor:
    bbox_min, bbox_max = _world_bbox(obj)
    centroid = tuple((bbox_min[i] + bbox_max[i]) / 2.0 for i in range(3))
    ext = tuple(bbox_max[i] - bbox_min[i] for i in range(3))
    nonzero_ext = [e for e in ext if e > 0]
    is_planar = bool(nonzero_ext) and (min(ext) / max(ext) < PLANAR_THIN_RATIO if max(ext) > 0 else False)

    try:
        vert_count = len(obj.data.vertices)
    except Exception:
        vert_count = 0

    return PartDescriptor(
        name=obj.name,
        bbox_min=bbox_min,
        bbox_max=bbox_max,
        centroid=centroid,
        vert_count=vert_count,
        material_names=_material_names(obj),
        max_transmission=_max_transmission(obj),
        is_planar=is_planar,
    )


def extract_part_descriptors(parts):
    return [extract_part_descriptor(obj) for obj in parts]


def _isclose(a, b):
    return math.isclose(a, b, abs_tol=_SCALE_EPSILON)


def _object_scale_info(obj) -> ObjectScaleInfo:
    sx, sy, sz = obj.scale.x, obj.scale.y, obj.scale.z
    applied = _isclose(sx, 1.0) and _isclose(sy, 1.0) and _isclose(sz, 1.0)
    uniform = _isclose(sx, sy) and _isclose(sy, sz) and _isclose(sx, sz)
    return ObjectScaleInfo(name=obj.name, applied=applied, uniform=uniform)


def extract_scene_meta(scene, parts) -> SceneMeta:
    """§8.1 step 2's inputs: unit scale, fps, frame range, and per-part
    applied/uniform scale — everything core/validate.py's V1-V3 need, as
    plain data."""
    render = scene.render
    fps = (render.fps / render.fps_base) if render.fps_base else 0.0
    return SceneMeta(
        unit_scale=scene.unit_settings.scale_length,
        fps=fps,
        frame_start=scene.frame_start,
        frame_end=scene.frame_end,
        object_scales=tuple(_object_scale_info(obj) for obj in parts),
    )
