"""Local, offline part tagging — no network, no API key, instant.

Runs first on every Setup. The Claude pass (tagger.py) only sees the parts
this cannot confidently place, which keeps the request small and cheap.
"""

# Name fragment -> (role, material_class). Checked longest-first so
# "windshield" wins over "shield" and "wheel_hub" over "wheel".
NAME_RULES = (
    ("windshield", ('FRACTURE', 'GLASS')),
    ("windscreen", ('FRACTURE', 'GLASS')),
    ("rearglass", ('FRACTURE', 'GLASS')),
    ("sideglass", ('FRACTURE', 'GLASS')),
    ("headlight", ('FRACTURE', 'GLASS')),
    ("taillight", ('FRACTURE', 'GLASS')),
    ("tail_light", ('FRACTURE', 'GLASS')),
    ("head_light", ('FRACTURE', 'GLASS')),
    ("mirror", ('DETACH', 'GLASS')),
    ("window", ('FRACTURE', 'GLASS')),
    ("glass", ('FRACTURE', 'GLASS')),

    ("bumper", ('DETACH', 'PLASTIC')),
    ("spoiler", ('DETACH', 'PLASTIC')),
    ("splitter", ('DETACH', 'PLASTIC')),
    ("grille", ('DETACH', 'TRIM_CHROME')),
    ("grill", ('DETACH', 'TRIM_CHROME')),
    ("badge", ('DETACH', 'TRIM_CHROME')),
    ("emblem", ('DETACH', 'TRIM_CHROME')),
    ("trim", ('DETACH', 'TRIM_CHROME')),
    ("chrome", ('DETACH', 'TRIM_CHROME')),
    ("handle", ('DETACH', 'TRIM_CHROME')),
    ("wiper", ('DETACH', 'RUBBER')),
    ("antenna", ('DETACH', 'PLASTIC')),

    ("hood", ('DEFORM', 'STEEL')),
    ("bonnet", ('DEFORM', 'STEEL')),
    ("fender", ('DEFORM', 'STEEL')),
    ("wing", ('DEFORM', 'STEEL')),
    ("quarter", ('DEFORM', 'STEEL')),
    ("door", ('DEFORM', 'STEEL')),
    ("roof", ('DEFORM', 'STEEL')),
    ("trunk", ('DEFORM', 'STEEL')),
    ("boot", ('DEFORM', 'STEEL')),
    ("tailgate", ('DEFORM', 'STEEL')),
    ("panel", ('DEFORM', 'STEEL')),

    ("chassis", ('PASSIVE', 'STEEL')),
    ("frame", ('PASSIVE', 'STEEL')),
    ("subframe", ('PASSIVE', 'STEEL')),
    ("body", ('PASSIVE', 'STEEL')),
    ("floor", ('PASSIVE', 'STEEL')),
    ("firewall", ('PASSIVE', 'STEEL')),

    ("tyre", ('RIGID', 'RUBBER')),
    ("tire", ('RIGID', 'RUBBER')),
    ("wheel", ('RIGID', 'STEEL')),
    ("rim", ('RIGID', 'STEEL')),
    ("brake", ('RIGID', 'STEEL')),
    ("caliper", ('RIGID', 'STEEL')),
    ("engine", ('RIGID', 'STEEL')),
    ("motor", ('RIGID', 'STEEL')),
    ("exhaust", ('RIGID', 'STEEL')),
    ("suspension", ('RIGID', 'STEEL')),
    ("axle", ('RIGID', 'STEEL')),

    ("seat", ('RIGID', 'INTERIOR_FABRIC')),
    ("dash", ('RIGID', 'PLASTIC')),
    ("steering", ('RIGID', 'PLASTIC')),
    ("wheel_steering", ('RIGID', 'PLASTIC')),
    ("interior", ('RIGID', 'INTERIOR_FABRIC')),
    ("carpet", ('RIGID', 'INTERIOR_FABRIC')),
)

# Sorted longest-first at import so specific names beat generic substrings.
_SORTED_RULES = tuple(sorted(NAME_RULES, key=lambda r: -len(r[0])))

THIN_RATIO = 0.12
SMALL_VOLUME_M3 = 0.01
LARGE_VOLUME_M3 = 1.5


def tag_by_name(obj_name):
    """Return (role, material_class) or None if no name rule matches."""
    lowered = obj_name.lower()
    for fragment, result in _SORTED_RULES:
        if fragment in lowered:
            return result
    return None


def tag_by_material(materials, keywords):
    """Match material slot names against the preferences keyword table."""
    for material in materials:
        if material is None:
            continue
        lowered = material.name.lower()
        for entry in keywords:
            if entry.keyword and entry.keyword.lower() in lowered:
                return entry.material_class
    return None


def tag_by_geometry(dimensions):
    """Fallback shape guess. Returns (role, material_class) — never None."""
    dims = sorted(float(d) for d in dimensions)
    smallest, _, largest = dims
    volume = dims[0] * dims[1] * dims[2]

    if largest > 0 and (smallest / largest) < THIN_RATIO:
        # Thin sheet: body panel territory.
        return ('DEFORM', 'STEEL')
    if volume < SMALL_VOLUME_M3:
        return ('RIGID', 'PLASTIC')
    if volume > LARGE_VOLUME_M3:
        return ('PASSIVE', 'STEEL')
    return ('RIGID', 'STEEL')


def classify(obj, keywords):
    """Full local pass for one object.

    Returns (role, material_class, confident) — `confident` False means the
    Claude pass should get a look at this one.
    """
    material_class = tag_by_material(obj.data.materials, keywords) if obj.data.materials else None

    by_name = tag_by_name(obj.name)
    if by_name is not None:
        role, name_material = by_name
        return role, (material_class or name_material), True

    role, geo_material = tag_by_geometry(obj.dimensions)
    return role, (material_class or geo_material), False
