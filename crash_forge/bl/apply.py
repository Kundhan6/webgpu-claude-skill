"""bl/apply.py — core/ decisions -> bpy state (§5). No decisions made
here, only the mechanical bpy calls that carry out what core/ (or the
operator orchestrating a stage) already decided needs to happen.
"""
import bpy


def clean_mesh_shading_attributes(obj) -> bool:
    """§8.1 step 6 / §11 V4: remove sharp_face and custom_normal
    attributes — these are what corrupts shading after joining meshes.
    Data-API only, no bpy.ops (§3 rule 6: no operator where a data call
    exists). Returns True if anything was actually removed."""
    removed = False
    mesh = obj.data
    for attr_name in ("sharp_face", "custom_normal"):
        attr = mesh.attributes.get(attr_name)
        if attr is not None:
            mesh.attributes.remove(attr)
            removed = True
    return removed


def apply_shade_auto_smooth(context, obj) -> bool:
    """§8.1 step 6: re-apply shade-auto-smooth after the attribute
    cleanup above. bpy.ops.object.shade_auto_smooth has no data-API
    equivalent (§6/§15: it's a Geometry Nodes modifier under the hood,
    version-dependent in shape), so this is one of the unavoidable
    bpy.ops calls §3 rule 6 permits — wrapped in temp_override, return
    value checked. Returns True if the operator reported FINISHED."""
    with context.temp_override(object=obj, active_object=obj, selected_objects=[obj]):
        result = bpy.ops.object.shade_auto_smooth()
    return 'FINISHED' in result


def set_origin_to_center_of_mass(context, obj) -> bool:
    """§8.1 step 7: origin_set(type='ORIGIN_CENTER_OF_MASS'). No data-API
    equivalent exists for recomputing an object's origin from its mesh,
    so this is the operator path, wrapped and return-checked per §3 rule
    6. Returns True if the operator reported FINISHED."""
    with context.temp_override(object=obj, active_object=obj, selected_objects=[obj]):
        result = bpy.ops.object.origin_set(type='ORIGIN_CENTER_OF_MASS')
    return 'FINISHED' in result
