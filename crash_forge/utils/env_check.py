"""Pure, reusable environment-dependency checks.

Kept operator-free so a future panels.py status strip can call the same
functions the Preferences 'Verify Environment' button uses. Every function
guards its own failures and returns a result tuple instead of raising —
callers should never need a try/except around these.
"""

import bpy


def check_cell_fracture():
    """Look for the Cell Fracture add-on under any current naming/namespace.

    Returns (available: bool, message: str).
    """
    try:
        import addon_utils

        candidates = []
        for mod in addon_utils.modules():
            mod_name = getattr(mod, "__name__", "")
            info = addon_utils.module_bl_info(mod) if hasattr(addon_utils, "module_bl_info") else getattr(mod, "bl_info", {})
            display_name = (info or {}).get("name", "")
            if "fracture" in mod_name.lower() or "fracture" in display_name.lower():
                candidates.append(mod_name)

        if not candidates:
            return False, (
                "Cell Fracture not found. Enable it under "
                "Preferences > Add-ons/Extensions (search 'Fracture') before running Rig."
            )

        for mod_name in candidates:
            loaded_default, loaded_state = addon_utils.check(mod_name)
            if loaded_state:
                return True, f"Cell Fracture is enabled ({mod_name})."

        return False, (
            f"Cell Fracture found but not enabled ({', '.join(candidates)}). "
            "Enable it under Preferences > Add-ons/Extensions before running Rig."
        )
    except Exception as exc:
        return False, f"Could not check Cell Fracture availability: {exc}"


def check_mantaflow():
    """Confirm this Blender build was compiled with fluid (Mantaflow) support.

    Returns (available: bool, message: str).
    """
    try:
        available = getattr(bpy.app.build_options, "fluid", True)
        if available:
            return True, "Mantaflow (fluid) support is present in this Blender build."
        return False, (
            "This Blender build was compiled without fluid/Mantaflow support. "
            "The Dust step in Rig will not work."
        )
    except Exception as exc:
        return False, f"Could not check Mantaflow availability: {exc}"


def check_action_api_shape():
    """Detect which Action F-Curve API shape this Blender exposes.

    Returns (shape, message) where shape is one of
    'LAYERED', 'LEGACY', 'MIXED', 'UNKNOWN'.
    """
    try:
        has_layers = hasattr(bpy.types.Action, "layers")
        has_fcurves = hasattr(bpy.types.Action, "fcurves")

        if has_layers and not has_fcurves:
            return 'LAYERED', "Layered/slotted Action API detected (expected on Blender 5.1)."
        if has_fcurves and not has_layers:
            return 'LEGACY', "Legacy Action.fcurves API detected."
        if has_layers and has_fcurves:
            return 'MIXED', "Both layered and legacy Action APIs are present."
        return 'UNKNOWN', "Neither layers nor fcurves found on bpy.types.Action."
    except Exception as exc:
        return 'UNKNOWN', f"Could not inspect Action API shape: {exc}"
