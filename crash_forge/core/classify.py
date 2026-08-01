"""Part classification from AABB descriptors (§12). No bpy import.

Works entirely in the car's local space, normalising coordinates against
a reference bbox so the rules are scale-free (§12.1). Z is treated as the
vertical axis throughout — matching Blender's Z-up world convention and
§12.1's own "low Z"/"high Z" language — the forward axis is auto-detected
(the longer of X/Y) and the remaining axis is lateral (left/right).

Every tuned-not-verified numeric threshold this module uses (LOW_Z,
HIGH_Z, the forward/lateral "extreme" cutoffs, the wheel score floor, the
glass fallback's Z cutoff) lives in core/tuning.py, not here — see that
module for what "tuned" means and why. WHEEL_SIZE_TOLERANCE is the one
exception: §12.2 gives that value directly ("sizes agreeing within 15%"),
so it's spec-given, not tuned, and stays local.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from . import tuning
from .geometry import centroid as bbox_centroid
from .geometry import extents, normalize_point, roundness, sizes_agree, thin_axis, union_bbox

VERTICAL_AXIS = 2  # Z, per §12.1's own "low Z"/"high Z" language

# §12.2: "sizes agreeing within 15%" — spec-given, not tuned.
WHEEL_SIZE_TOLERANCE = 0.15


class PartRole(Enum):
    BODY = "BODY"
    WHEEL_FL = "WHEEL_FL"
    WHEEL_FR = "WHEEL_FR"
    WHEEL_RL = "WHEEL_RL"
    WHEEL_RR = "WHEEL_RR"
    DOOR_L = "DOOR_L"
    DOOR_R = "DOOR_R"
    HOOD = "HOOD"
    BOOT = "BOOT"
    BUMPER_F = "BUMPER_F"
    BUMPER_R = "BUMPER_R"
    GLASS = "GLASS"
    MIRROR = "MIRROR"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class PartDescriptor:
    name: str
    bbox_min: tuple
    bbox_max: tuple
    centroid: tuple
    vert_count: int
    material_names: tuple = field(default_factory=tuple)
    max_transmission: float = 0.0
    is_planar: bool = False


@dataclass(frozen=True)
class Classification:
    role: PartRole
    confidence: float


# §12.1 step 5: name keyword hints, case-insensitive — never trusted
# alone, only used to nudge confidence when they *agree* with the
# geometric call. "wheel"/"tyre"/"tire" map to None deliberately: wheel
# role assignment is entirely geometry-driven (detect_wheels), a name
# hint has no vote there.
NAME_KEYWORDS = {
    "windshield": PartRole.GLASS,
    "window": PartRole.GLASS,
    "glass": PartRole.GLASS,
    "bonnet": PartRole.HOOD,
    "hood": PartRole.HOOD,
    "bumper": None,  # front/rear is geometry-only; keyword can't disambiguate
    "door": None,  # left/right is geometry-only; keyword can't disambiguate
    "wheel": None,
    "tyre": None,
    "tire": None,
}


def name_hint(name: str) -> Optional[PartRole]:
    lowered = name.lower()
    for keyword, role in NAME_KEYWORDS.items():
        if keyword in lowered:
            return role
    return None


def _bbox_volume(part: PartDescriptor) -> float:
    dx, dy, dz = extents(part.bbox_min, part.bbox_max)
    return max(dx, 0.0) * max(dy, 0.0) * max(dz, 0.0)


def _wheel_radius(part: PartDescriptor) -> float:
    ext = extents(part.bbox_min, part.bbox_max)
    t_axis = thin_axis(ext)
    others = [ext[i] for i in range(3) if i != t_axis]
    return sum(others) / 4.0  # half the mean of the two non-thin extents


def detect_wheels(parts, lateral_axis: int, vertical_axis: int, whole_center,
                   size_tolerance: float = WHEEL_SIZE_TOLERANCE):
    """§12.2. Returns (wheel_parts: list[PartDescriptor], confidence).
    Never pads to 4 by guessing: fewer than 4 plausible candidates returns
    `([], 0.0)` rather than forcing an assignment (§13: "3-wheel and
    5-wheel cases degrade gracefully")."""
    parts = list(parts)
    if not parts:
        return [], 0.0

    boxes = [(p.bbox_min, p.bbox_max) for p in parts]
    whole_min, whole_max = union_bbox(boxes)
    whole_ext = extents(whole_min, whole_max)
    bottom_third = (
        whole_min[vertical_axis] + whole_ext[vertical_axis] / 3.0
        if whole_ext[vertical_axis] else whole_max[vertical_axis]
    )

    scored = []
    for part in parts:
        ext = extents(part.bbox_min, part.bbox_max)
        t_axis = thin_axis(ext)
        round_score = roundness(ext, t_axis)
        low_weight = 1.0 if part.centroid[vertical_axis] <= bottom_third else 0.2
        scored.append((round_score * low_weight, part))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    plausible = [(score, part) for score, part in scored if score > tuning.CLASSIFY_WHEEL_SCORE_FLOOR]

    if len(plausible) < 4:
        return [], 0.0

    top4 = [part for _, part in plausible[:4]]

    radii = [_wheel_radius(p) for p in top4]
    sizes_ok = all(
        sizes_agree(radii[i], radii[j], size_tolerance)
        for i in range(4) for j in range(i + 1, 4)
    )
    right_count = sum(1 for p in top4 if p.centroid[lateral_axis] >= whole_center[lateral_axis])
    symmetric = right_count == 2

    if sizes_ok and symmetric and len(plausible) == 4:
        confidence = 0.9
    elif sizes_ok and symmetric:
        confidence = 0.6  # extra plausible candidates existed beyond the top 4 — some ambiguity
    else:
        confidence = 0.4  # took the top 4 anyway, but they don't validate as two clean pairs

    return top4, confidence


def _assign_wheel_roles(wheel_parts, forward_axis: int, forward_sign: int, lateral_axis: int, whole_center):
    """FL/FR/RL/RR from geometry alone, relative to the whole car's
    centroid (not raw world position, which may be offset from origin).
    Right = positive lateral coordinate; an arbitrary but consistently
    applied convention, documented since "left"/"right" mean nothing
    without one."""
    roles = {}
    for part in wheel_parts:
        rel_forward = (part.centroid[forward_axis] - whole_center[forward_axis]) * forward_sign
        rel_lateral = part.centroid[lateral_axis] - whole_center[lateral_axis]
        is_front = rel_forward >= 0
        is_right = rel_lateral >= 0
        if is_front and is_right:
            roles[part.name] = PartRole.WHEEL_FR
        elif is_front and not is_right:
            roles[part.name] = PartRole.WHEEL_FL
        elif is_right:
            roles[part.name] = PartRole.WHEEL_RR
        else:
            roles[part.name] = PartRole.WHEEL_RL
    return roles


def _is_glass(part: PartDescriptor, whole_min, whole_max, vertical_axis: int):
    """§12.4, in priority order. Only `max_transmission` is available from
    PartDescriptor for the material signal — spec's priority-1 check also
    mentions blend-mode/alpha, which isn't part of this dataclass, so
    that half of priority 1 is out of scope until PartDescriptor grows
    that field."""
    if part.max_transmission > 0.5:
        return True, 0.95
    if name_hint(part.name) == PartRole.GLASS:
        return True, 0.7
    if part.is_planar:
        norm_z = normalize_point(part.centroid, whole_min, whole_max)[vertical_axis]
        if norm_z > tuning.CLASSIFY_GLASS_FALLBACK_HIGH_Z:
            return True, 0.5
    return False, 0.0


def _detect_forward_sign(parts, forward_axis: int, glass_names, whole_center):
    """§12.3 front/rear disambiguation, simplified to its glass signal:
    "the presence of glass in the upper-forward region". Without glass to
    go on, defaults to +1 with low confidence rather than guessing
    harder — this is exactly what should surface in the one-line
    confirmation (§12.1 step 6) rather than being silently trusted."""
    glass_parts = [p for p in parts if p.name in glass_names]
    if not glass_parts:
        return 1, 0.3
    avg_glass_forward = sum(p.centroid[forward_axis] for p in glass_parts) / len(glass_parts)
    sign = 1 if avg_glass_forward >= whole_center[forward_axis] else -1
    return sign, 0.8


def detect_forward_axis(parts) -> int:
    """§12.3: longest bbox extent = length axis, restricted to X/Y since
    Z is always vertical (§12.1)."""
    boxes = [(p.bbox_min, p.bbox_max) for p in parts]
    whole_min, whole_max = union_bbox(boxes)
    ext = extents(whole_min, whole_max)
    return 0 if ext[0] >= ext[1] else 1


def _classify_remaining_part(part, body_min, body_max, forward_axis, forward_sign, lateral_axis, vertical_axis):
    norm = normalize_point(part.centroid, body_min, body_max)
    fwd = norm[forward_axis] if forward_sign == 1 else 1.0 - norm[forward_axis]
    lat = norm[lateral_axis]
    vert = norm[vertical_axis]

    ext = extents(part.bbox_min, part.bbox_max)
    t_axis = thin_axis(ext)

    if fwd >= tuning.CLASSIFY_FORWARD_EXTREME and vert <= tuning.CLASSIFY_LOW_Z:
        return PartRole.BUMPER_F, 0.7
    if fwd <= (1 - tuning.CLASSIFY_FORWARD_EXTREME) and vert <= tuning.CLASSIFY_LOW_Z:
        return PartRole.BUMPER_R, 0.7
    if vert >= tuning.CLASSIFY_HIGH_Z and fwd > 0.5 and part.is_planar and t_axis == vertical_axis:
        return PartRole.HOOD, 0.7
    if vert >= tuning.CLASSIFY_HIGH_Z and fwd <= 0.5 and part.is_planar and t_axis == vertical_axis:
        return PartRole.BOOT, 0.7
    if (lat <= (1 - tuning.CLASSIFY_LATERAL_EXTREME) or lat >= tuning.CLASSIFY_LATERAL_EXTREME) and part.is_planar and t_axis == lateral_axis:
        return (PartRole.DOOR_R if lat >= 0.5 else PartRole.DOOR_L), 0.7
    return PartRole.UNKNOWN, 0.3


def classify(parts, forward_axis: int) -> dict:
    """§12.1's full dispatcher. Returns {part_name: Classification}, every
    input part named exactly once. `forward_axis` is resolved by the
    caller (detect_forward_axis(), or a user override) — this function
    only consumes it, matching the spec's example signature.
    """
    parts = list(parts)
    remaining = {p.name: p for p in parts}
    results = {}

    vertical_axis = VERTICAL_AXIS
    lateral_axis = 3 - forward_axis - vertical_axis

    boxes = [(p.bbox_min, p.bbox_max) for p in parts]
    whole_min, whole_max = union_bbox(boxes)
    whole_center = bbox_centroid(whole_min, whole_max)

    # 1. Wheels first; remove them from consideration.
    wheel_parts, wheel_confidence = detect_wheels(
        list(remaining.values()), lateral_axis, vertical_axis, whole_center,
    )
    for p in wheel_parts:
        del remaining[p.name]

    # 2. Glass by material (or name/geometry fallback); remove next.
    glass_names = []
    for name, part in list(remaining.items()):
        is_glass, conf = _is_glass(part, whole_min, whole_max, vertical_axis)
        if is_glass:
            results[name] = Classification(PartRole.GLASS, conf)
            glass_names.append(name)
            del remaining[name]

    # 3. Of what remains, the largest connected mesh by volume is BODY.
    # (bbox volume is a proxy for "connected mesh volume" — pure
    # descriptors carry no real mesh topology to measure it directly.)
    body_part = None
    if remaining:
        body_name = max(remaining, key=lambda n: _bbox_volume(remaining[n]))
        body_part = remaining.pop(body_name)
        results[body_name] = Classification(PartRole.BODY, 0.9)

    # Forward direction needs to know where glass ended up — hence this
    # runs after step 2, and wheel-role assignment (needing the same
    # direction) runs after this.
    forward_sign, forward_conf = _detect_forward_sign(parts, forward_axis, glass_names, whole_center)

    if wheel_parts:
        wheel_roles = _assign_wheel_roles(wheel_parts, forward_axis, forward_sign, lateral_axis, whole_center)
        for name, role in wheel_roles.items():
            results[name] = Classification(role, min(wheel_confidence, forward_conf))
    # Fewer than 4 confident wheels: those parts fall through to step 4
    # below unclassified as wheels, most likely landing on UNKNOWN.

    # 4. Remaining parts by normalised centroid against the BODY bbox.
    if body_part is not None:
        for name, part in remaining.items():
            role, conf = _classify_remaining_part(
                part, body_part.bbox_min, body_part.bbox_max,
                forward_axis, forward_sign, lateral_axis, vertical_axis,
            )
            hint = name_hint(name)
            if hint is not None and hint == role:
                conf = min(1.0, conf + 0.15)
            results[name] = Classification(role, conf)
    else:
        # No body found at all (e.g. every part got classified as a wheel
        # or glass) — nothing left to normalise against; report low
        # confidence rather than guess.
        for name, part in remaining.items():
            results[name] = Classification(PartRole.UNKNOWN, 0.1)

    return results
