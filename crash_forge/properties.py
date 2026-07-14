"""Crash Forge data model — CrashForgeSceneProps (scene.crashforge) and
CrashForgeObjectProps (object.crashforge), plus the lookup tables later
stages (Rig, Bake) read from to turn enum choices into real simulation
numbers.
"""

import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import PropertyGroup


# (substeps, iterations) for scene.rigidbody_world, keyed by slowmo_amount.
SLOWMO_SUBSTEPS_ITERATIONS = {
    'NORMAL': (20, 10),
    'MODERATE': (40, 30),
    'HEAVY': (60, 50),
}

# (tension, compression, bending) cloth stiffness, keyed by crumple_intensity.
# Placeholder values — tune once you see crumple behavior in Blender.
CRUMPLE_INTENSITY_PARAMS = {
    'SUBTLE': (15.0, 15.0, 0.5),
    'MODERATE': (40.0, 40.0, 2.0),
    'HEAVY': (80.0, 80.0, 8.0),
}

# Shared by CrashForgeObjectProps.material_class and the preferences
# keyword-mapping enum, so the two lists can't drift apart.
MATERIAL_CLASS_ITEMS = (
    ('STEEL', "Steel", "Structural steel body panels and frame"),
    ('GLASS', "Glass", "Windshield and window glass"),
    ('RUBBER', "Rubber", "Tires and rubber trim"),
    ('PLASTIC', "Plastic", "Bumpers, panels, and general plastic"),
    ('TRIM_CHROME', "Trim / Chrome", "Chrome-plated trim pieces"),
    ('CONCRETE', "Concrete", "Environment and road concrete"),
    ('INTERIOR_FABRIC', "Interior Fabric", "Seats, upholstery, cloth and leather"),
)

# kg/m^3. PLASTIC, TRIM_CHROME, and INTERIOR_FABRIC are placeholders —
# tune once mass/rigid-body behavior is visible in Blender.
MATERIAL_DENSITY_KG_M3 = {
    'STEEL': 7850,
    'GLASS': 2500,
    'RUBBER': 1100,
    'PLASTIC': 950,
    'TRIM_CHROME': 1500,
    'CONCRETE': 2400,
    'INTERIOR_FABRIC': 200,
}


def _poll_impact_target(self, obj):
    return obj.type == 'MESH'


class CrashForgeSceneProps(PropertyGroup):
    impact_target: PointerProperty(
        type=bpy.types.Object,
        name="Impact Target",
        description="The object the car collides with",
        poll=_poll_impact_target,
    )
    auto_launch_on_impact: BoolProperty(
        name="Auto-Launch on Impact",
        description="Automatically detect the impact frame after Drive Mode finishes",
        default=True,
    )
    impact_frame: IntProperty(
        name="Impact Frame",
        description="Frame at which the car and impact target first overlap (computed)",
        default=0,
        min=0,
    )
    impact_location: FloatVectorProperty(
        name="Impact Location",
        description="World-space overlap midpoint at the impact frame (computed)",
        size=3,
        subtype='TRANSLATION',
        default=(0.0, 0.0, 0.0),
    )
    impact_speed: FloatProperty(
        name="Impact Speed",
        description="Car speed at impact, from drive-key finite difference (computed); drives dust/debris scaling",
        default=0.0,
        min=0.0,
        subtype='VELOCITY',
        unit='VELOCITY',
    )
    slowmo_amount: EnumProperty(
        name="Slow-Mo Amount",
        description="Rigid body world substeps/iterations for the crash",
        items=(
            ('NORMAL', "Normal", "20 substeps / 10 iterations"),
            ('MODERATE', "Moderate", "40 substeps / 30 iterations"),
            ('HEAVY', "Heavy", "60 substeps / 50 iterations"),
        ),
        default='MODERATE',
    )
    crumple_intensity: EnumProperty(
        name="Crumple Intensity",
        description="Cloth stiffness preset used for deformable crumple",
        items=(
            ('SUBTLE', "Subtle", "Light crumple"),
            ('MODERATE', "Moderate", "Medium crumple"),
            ('HEAVY', "Heavy", "Heavy crumple"),
        ),
        default='MODERATE',
    )
    fracture_falloff_radius: FloatProperty(
        name="Fracture Falloff Radius",
        description="Distance from the fracture origin within which cells are dense (placeholder default — tune to scene scale)",
        default=2.0,
        min=0.0,
        subtype='DISTANCE',
        unit='LENGTH',
    )
    fracture_outer_multiplier: FloatProperty(
        name="Outer Cell Multiplier",
        description="Cell-count reduction factor applied outside the falloff radius",
        default=0.25,
        min=0.0,
        max=1.0,
        subtype='FACTOR',
    )
    shot_name: StringProperty(
        name="Shot Name",
        description="Used to name cache folders on disk",
        default="",
    )
    cache_version: IntProperty(
        name="Cache Version",
        description="Current bake cache version number",
        default=1,
        min=0,
    )


class CrashForgeObjectProps(PropertyGroup):
    role: EnumProperty(
        name="Role",
        description="How this object participates in the crash simulation",
        items=(
            ('RIGID', "Rigid", "Rigid body, no deformation"),
            ('DEFORM', "Deform", "Cloth-based crumple deformation"),
            ('FRACTURE', "Fracture", "Shatters into cell fragments"),
            ('DETACH', "Detach", "Breaks free via rigid body constraints"),
            ('PASSIVE', "Passive", "Static collider, never moves"),
        ),
        default='RIGID',
    )
    crumple_then_shatter: BoolProperty(
        name="Crumple Then Shatter",
        description="Crumple first, then fracture the crumpled shape",
        default=False,
    )
    material_class: EnumProperty(
        name="Material Class",
        description="Drives density, and later, material-based simulation defaults",
        items=MATERIAL_CLASS_ITEMS,
        default='STEEL',
    )
    fracture_origin: FloatVectorProperty(
        name="Fracture Origin",
        description="World-space fracture point; click-to-place or auto-filled from the impact location",
        size=3,
        subtype='TRANSLATION',
        default=(0.0, 0.0, 0.0),
    )
    crashforge_generated: BoolProperty(
        name="Crash Forge Generated",
        description="Marks objects/modifiers created by Crash Forge, enabling a safe wipe on rebuild",
        default=False,
    )
    baked_locked: BoolProperty(
        name="Baked Locked",
        description="Protects this object's bake from being cleared by Rebuild from Tags",
        default=False,
    )


classes = (
    CrashForgeSceneProps,
    CrashForgeObjectProps,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.crashforge = PointerProperty(type=CrashForgeSceneProps)
    bpy.types.Object.crashforge = PointerProperty(type=CrashForgeObjectProps)


def unregister():
    try:
        del bpy.types.Object.crashforge
    except AttributeError:
        pass
    try:
        del bpy.types.Scene.crashforge
    except AttributeError:
        pass
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
