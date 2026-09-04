"""N-panel UI — View3D > Sidebar > KURO > StormKit. §4.4."""

import bpy

from kuro_core import uiutils
from stormkit import fog, presets as sk_presets

_PanelBase = uiutils.kuro_panel_base


class STORMKIT_PT_main(_PanelBase("stormkit_main", "StormKit")):
    def draw(self, context):
        layout = self.layout
        state = context.scene.stormkit

        col = layout.column(align=True)
        col.label(text="Presets")
        preset_names = sk_presets.list_presets()
        grid = col.grid_flow(row_major=True, columns=2, even_columns=True)
        for key, _path in preset_names:
            display = key.replace("_", " ").title()
            op = grid.operator("stormkit.apply_preset", text=display)
            op.preset_name = key
            op.transition_frames = state.transition_frames

        layout.prop(state, "transition_frames")
        layout.separator()

        col = layout.column(align=True)
        col.prop(state, "time_of_day")
        col.prop(state, "overcast")
        col.prop(state, "precipitation_type")
        col.prop(state, "precipitation_amount")
        col.prop(state, "wetness")
        col.prop(state, "snow_cover")
        col.prop(state, "storm_intensity")

        layout.separator()
        row = layout.row(align=True)
        row.operator("stormkit.apply_to_scene", icon="PLAY")
        row.operator("stormkit.remove_all", icon="TRASH")

        skipped = context.scene.get("kuro_stormkit_last_skipped")
        if skipped:
            uiutils.draw_error_box(
                layout,
                f"{len(skipped)} material(s) skipped (no direct Principled BSDF):\n" + "\n".join(skipped[:5]),
                icon="INFO",
            )


class STORMKIT_PT_sky(_PanelBase("stormkit_sky", "Sky & Sun")):
    bl_parent_id = "KURO_PT_stormkit_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        state = context.scene.stormkit
        col = self.layout.column(align=True)
        col.prop(state, "latitude")
        col.prop(state, "time_of_day")
        col.prop(state, "overcast")


class STORMKIT_PT_fog(_PanelBase("stormkit_fog", "Fog")):
    bl_parent_id = "KURO_PT_stormkit_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        state = context.scene.stormkit
        layout = self.layout
        col = layout.column(align=True)
        col.prop(state, "fog_density")
        col.prop(state, "fog_height")

        if fog.eevee_volumetrics_hint(context) is None:
            uiutils.draw_error_box(
                layout, "Could not verify EEVEE volumetric settings on this Blender\nversion — check Render Properties > Volumetrics.", icon="INFO"
            )


class STORMKIT_PT_precipitation(_PanelBase("stormkit_precip", "Precipitation")):
    bl_parent_id = "KURO_PT_stormkit_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        state = context.scene.stormkit
        col = self.layout.column(align=True)
        col.prop(state, "precipitation_type")
        col.prop(state, "precipitation_amount")
        col.prop(state, "wind_speed")
        col.prop(state, "wind_direction")


class STORMKIT_PT_surface_fx(_PanelBase("stormkit_surface", "Surface FX")):
    bl_parent_id = "KURO_PT_stormkit_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        state = context.scene.stormkit
        layout = self.layout
        col = layout.column(align=True)
        col.prop(state, "wetness")
        col.prop(state, "snow_cover")

        row = layout.row(align=True)
        op_on = row.operator("stormkit.toggle_snow_geometry", text="Add Snow Geometry")
        op_on.enable = True
        op_off = row.operator("stormkit.toggle_snow_geometry", text="Remove Snow Geometry")
        op_off.enable = False
        layout.label(text="Snow Geometry is off by default (performance).", icon="INFO")


class STORMKIT_PT_wind(_PanelBase("stormkit_wind", "Wind")):
    bl_parent_id = "KURO_PT_stormkit_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        state = context.scene.stormkit
        col = self.layout.column(align=True)
        col.prop(state, "wind_speed")
        col.prop(state, "wind_direction")
        col.prop(state, "turbulence")


class STORMKIT_PT_lightning(_PanelBase("stormkit_lightning", "Lightning")):
    bl_parent_id = "KURO_PT_stormkit_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        state = context.scene.stormkit
        layout = self.layout
        layout.prop(state, "storm_intensity")
        layout.operator("stormkit.bake_lightning", icon="RENDER_ANIMATION")


classes = (
    STORMKIT_PT_main,
    STORMKIT_PT_sky,
    STORMKIT_PT_fog,
    STORMKIT_PT_precipitation,
    STORMKIT_PT_surface_fx,
    STORMKIT_PT_wind,
    STORMKIT_PT_lightning,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
