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


def _select_only(context, obj):
    """Make `obj` the *real* active/selected object, not just what a
    temp_override presents. Confirmed necessary on a real Blender 5.1.2
    run (M4 verification, real car): shade_auto_smooth.poll() checks the
    actual view_layer active object underneath — temp_override's
    active_object= kwarg is read-only convenience for that one call, it
    does not itself change that. Whenever the *real* active object was a
    non-mesh (the car's root Empty — exactly what's selected after a
    normal "set car_object, click Prep" flow), the operator raised
    RuntimeError: "poll() failed, context is incorrect" as an unhandled
    exception. bl/probe.py's own auto-smooth probe already does this real
    assignment; these two operator wrappers didn't.

    Returns (prev_selected, prev_active) so the caller can restore them —
    a Prep run must not leave the user's viewport selection mutated as a
    side effect (this is also why shade_auto_smooth previously appeared
    to warn about unrelated objects still selected from an earlier step:
    the override's selected_objects=[obj] doesn't flip every other
    object's real .select_get() to False either).
    """
    view_layer = context.view_layer
    prev_active = view_layer.objects.active
    prev_selected = [o for o in view_layer.objects if o.select_get()]

    for o in view_layer.objects:
        o.select_set(False)
    obj.select_set(True)
    view_layer.objects.active = obj

    return prev_selected, prev_active


def _restore_selection(context, prev_selected, prev_active):
    view_layer = context.view_layer
    for o in view_layer.objects:
        o.select_set(o in prev_selected)
    view_layer.objects.active = prev_active


def apply_shade_auto_smooth(context, obj) -> bool:
    """§8.1 step 6: re-apply shade-auto-smooth after the attribute
    cleanup above. bpy.ops.object.shade_auto_smooth has no data-API
    equivalent (§6/§15: it's a Geometry Nodes modifier under the hood,
    version-dependent in shape), so this is one of the unavoidable
    bpy.ops calls §3 rule 6 permits.

    Sets real selection/active state via _select_only() before calling
    the operator (see that function's docstring for why temp_override
    alone isn't enough — confirmed on a real car, not theoretical), and
    always restores the prior selection afterward. Never raises: a
    RuntimeError from the operator is exactly the kind of external-API
    brittleness §3 rule 1 exists to defend against, and degrades to a
    returned False rather than an unhandled traceback — the caller
    (ops/prep.py) is responsible for turning that into a reported, clean
    stage failure (§3 rule 10: fail loud, fail early, never a half-built
    result).

    Returns True if the operator reported FINISHED, False on any
    RuntimeError.
    """
    prev_selected, prev_active = _select_only(context, obj)
    try:
        with context.temp_override(object=obj, active_object=obj, selected_objects=[obj]):
            result = bpy.ops.object.shade_auto_smooth()
    except RuntimeError:
        return False
    finally:
        _restore_selection(context, prev_selected, prev_active)
    return 'FINISHED' in result


def set_origin_to_center_of_mass(context, obj) -> bool:
    """§8.1 step 7: origin_set(type='ORIGIN_CENTER_OF_MASS'). No data-API
    equivalent exists for recomputing an object's origin from its mesh,
    so this is the operator path.

    Same real-selection fix as apply_shade_auto_smooth, and for the same
    reason — this wrapped a bpy.ops call with the identical
    temp_override-only pattern that was confirmed insufficient on a real
    car; even though this specific call didn't crash in that run, it has
    the same latent gap and gets the same fix.

    Returns True if the operator reported FINISHED, False on any
    RuntimeError.
    """
    prev_selected, prev_active = _select_only(context, obj)
    try:
        with context.temp_override(object=obj, active_object=obj, selected_objects=[obj]):
            result = bpy.ops.object.origin_set(type='ORIGIN_CENTER_OF_MASS')
    except RuntimeError:
        return False
    finally:
        _restore_selection(context, prev_selected, prev_active)
    return 'FINISHED' in result
