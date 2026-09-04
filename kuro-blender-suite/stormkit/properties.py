"""StormKit's single source of truth: scene.stormkit.

Every subsystem (sky, fog, precipitation, wetness/snow, wind, lightning)
reads ONLY this PropertyGroup. Values propagate to node inputs and object
properties via drivers wired up at "Apply to Scene" time
(kuro_core.nodeutils.add_scene_driver) — never via a per-frame handler.

The one update= callback that exists here (precipitation_type) only
toggles object visibility, which satisfies ground rule #8: update
callbacks may set values, never rebuild graphs.
"""

import bpy
from bpy.props import EnumProperty, FloatProperty, IntProperty, PointerProperty
from bpy.types import PropertyGroup, Scene

PRECIP_KIND_PROP = "kuro_precip_kind"


def _on_precipitation_type_update(self, _context):
    kind = self.precipitation_type
    for obj in bpy.data.objects:
        precip_kind = obj.get(PRECIP_KIND_PROP)
        if precip_kind is None:
            continue
        visible = kind == precip_kind
        obj.hide_viewport = not visible
        obj.hide_render = not visible


class STORMKIT_PG_state(PropertyGroup):
    """See BLENDER_ADDON_MASTER_PLAN.md §4.1 for the field list this
    mirrors exactly."""

    time_of_day: FloatProperty(
        name="Time of Day",
        description="Hour of the day, solar time (0-24)",
        default=12.0, min=0.0, max=24.0,
    )
    overcast: FloatProperty(
        name="Overcast",
        description="0 = clear sky, 1 = fully overcast",
        default=0.0, min=0.0, max=1.0, subtype="FACTOR",
    )
    fog_density: FloatProperty(
        name="Fog Density",
        description="Volumetric ground-fog density",
        default=0.0, min=0.0, max=1.0, subtype="FACTOR",
    )
    fog_height: FloatProperty(
        name="Fog Height",
        description="World-space height (meters) the fog thins out above",
        default=2.0, min=0.01, max=1000.0, unit="LENGTH",
    )
    precipitation_type: EnumProperty(
        name="Precipitation",
        description="Type of falling precipitation",
        items=[
            ("NONE", "None", "No precipitation"),
            ("RAIN", "Rain", "Falling rain"),
            ("SNOW", "Snow", "Falling snow"),
        ],
        default="NONE",
        update=_on_precipitation_type_update,
    )
    precipitation_amount: FloatProperty(
        name="Amount",
        description="Precipitation density, 0-1",
        default=0.5, min=0.0, max=1.0, subtype="FACTOR",
    )
    wind_speed: FloatProperty(
        name="Wind Speed",
        description="Wind speed in meters/second",
        default=0.0, min=0.0, max=50.0, unit="VELOCITY",
    )
    wind_direction: FloatProperty(
        name="Wind Direction",
        description="Compass direction the wind blows toward",
        default=0.0, min=-6.283185, max=6.283185, subtype="ANGLE",
    )
    wetness: FloatProperty(
        name="Wetness",
        description="Global surface wetness: 0 = dry, 1 = soaked",
        default=0.0, min=0.0, max=1.0, subtype="FACTOR",
    )
    snow_cover: FloatProperty(
        name="Snow Cover",
        description="Global snow accumulation on upward-facing surfaces",
        default=0.0, min=0.0, max=1.0, subtype="FACTOR",
    )
    storm_intensity: FloatProperty(
        name="Storm Intensity",
        description="Drives lightning frequency and brightness; 0 = no lightning",
        default=0.0, min=0.0, max=1.0, subtype="FACTOR",
    )
    turbulence: FloatProperty(
        name="Turbulence",
        description="Extra chaotic wind variation applied to precipitation and foliage",
        default=0.0, min=0.0, max=1.0, subtype="FACTOR",
    )
    latitude: FloatProperty(
        name="Latitude",
        description=(
            "Scene location latitude in degrees, used for the sun's solar arc. "
            "Kept per-scene (rather than in add-on preferences) so a driver can "
            "target it directly, and so one .blend can hold shots at different "
            "locations — see DECISIONS.md"
        ),
        default=45.0, min=-90.0, max=90.0,
    )
    transition_frames: IntProperty(
        name="Transition Frames",
        description="When applying a preset, keyframe the change over this many frames instead of snapping instantly (0 = instant)",
        default=0, min=0, max=1000,
    )


classes = (STORMKIT_PG_state,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    Scene.stormkit = PointerProperty(type=STORMKIT_PG_state)


def unregister():
    del Scene.stormkit
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
