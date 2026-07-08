"""Version guards, socket-name maps, and feature detection.

IMPORTANT — read before touching this file:
Blender's Python API drifts between versions (see BLENDER_ADDON_MASTER_PLAN.md
ground rule #2 and #3). This module was written without a live Blender to
introspect against (the dev container has no `blender` binary). Every lookup
below is written defensively — it tries the documented canonical name first,
then a table of known historical aliases, then falls back to a runtime scan
of the actual sockets/enum-items and raises a clear, actionable error rather
than silently guessing. Before shipping, run `scripts/introspect.py` on the
target Blender (5.1.2) once to confirm the ALIASES table below still matches
reality, and update DECISIONS.md if anything moved.
"""

import bpy

MIN_BLENDER_VERSION = (4, 5, 0)
TARGET_BLENDER_VERSION = (5, 1, 2)


def blender_version():
    return bpy.app.version


def check_min_version():
    """Raise a clear, human-readable error if running on an unsupported Blender.

    Call this at add-on register() time — never let a version mismatch
    surface as a cryptic AttributeError deep in a node builder.
    """
    v = blender_version()
    if v < MIN_BLENDER_VERSION:
        raise RuntimeError(
            f"This add-on requires Blender {'.'.join(map(str, MIN_BLENDER_VERSION))} "
            f"or newer (found {'.'.join(map(str, v))}). Please upgrade Blender."
        )


# ---------------------------------------------------------------------------
# Principled BSDF socket map
# ---------------------------------------------------------------------------
# Canonical name -> known historical aliases (searched in order after the
# canonical name itself). These renames happened in the Blender 4.0
# "Principled BSDF v2" overhaul; kept here so recipes can target either
# a 4.x or a slightly-older 4.x-family file without caring which shipped.
PRINCIPLED_ALIASES = {
    "Base Color": ["Base Color"],
    "Metallic": ["Metallic"],
    "Roughness": ["Roughness"],
    "IOR": ["IOR"],
    "Alpha": ["Alpha"],
    "Normal": ["Normal"],
    "Subsurface Weight": ["Subsurface Weight", "Subsurface"],
    "Subsurface Radius": ["Subsurface Radius"],
    "Subsurface Scale": ["Subsurface Scale"],
    "Transmission Weight": ["Transmission Weight", "Transmission"],
    "Coat Weight": ["Coat Weight", "Clearcoat"],
    "Coat Roughness": ["Coat Roughness", "Clearcoat Roughness"],
    "Sheen Weight": ["Sheen Weight", "Sheen"],
    "Emission Color": ["Emission Color", "Emission"],
    "Emission Strength": ["Emission Strength"],
    "Specular IOR Level": ["Specular IOR Level", "Specular"],
    "Anisotropic": ["Anisotropic"],
}


class SocketResolutionError(RuntimeError):
    pass


def resolve_input_socket(node, canonical_name):
    """Return the NodeSocket on `node` matching `canonical_name`.

    Tries the canonical name, then known aliases, then fails loudly with
    the list of sockets actually present (so the caller can fix the map
    instead of silently building a broken graph).
    """
    candidates = PRINCIPLED_ALIASES.get(canonical_name, [canonical_name])
    for name in candidates:
        socket = node.inputs.get(name)
        if socket is not None:
            return socket
    available = [s.name for s in node.inputs]
    raise SocketResolutionError(
        f"Could not resolve input '{canonical_name}' on node '{node.name}' "
        f"({node.bl_idname}). Tried {candidates}. Available inputs: {available}. "
        f"This usually means the Blender version renamed a socket — update "
        f"kuro_core.compat.PRINCIPLED_ALIASES and note it in DECISIONS.md."
    )


def set_input(node, canonical_name, value):
    """Set `node`'s input matching `canonical_name` to `value`.

    Handles both default_value assignment and linking a value node/socket
    (if `value` is itself a NodeSocket, a link is expected to be made by
    the caller via NodeGraphBuilder.link — this only sets literal defaults).
    """
    socket = resolve_input_socket(node, canonical_name)
    socket.default_value = value
    return socket


# ---------------------------------------------------------------------------
# Feature detection
# ---------------------------------------------------------------------------

def has_musgrave():
    """Musgrave Texture was removed in Blender 4.1. Never build graphs that
    depend on it — this only exists so a build log can note when it's absent
    for informational purposes. Always treat as unavailable."""
    return hasattr(bpy.types, "ShaderNodeTexMusgrave")


_engine_cache = {}


def _scene_engine_enum_items(context=None):
    scene = (context or bpy.context).scene
    prop = scene.render.bl_rna.properties["engine"]
    return prop.enum_items


def get_cycles_identifier(context=None):
    """Return the render-engine identifier string for Cycles.

    Cycles has shipped under the stable identifier 'CYCLES' across every
    Blender version to date, but we still verify it exists in the current
    scene's engine enum rather than assuming — if a future Blender renames
    it, this raises instead of silently mismatching every engine check.
    """
    if "cycles" in _engine_cache:
        return _engine_cache["cycles"]
    items = _scene_engine_enum_items(context)
    for item in items:
        if item.identifier == "CYCLES":
            _engine_cache["cycles"] = "CYCLES"
            return "CYCLES"
    raise SocketResolutionError(
        f"Could not find a 'CYCLES' render engine identifier. Available: "
        f"{[i.identifier for i in items]}. Cycles may be disabled as an add-on."
    )


def get_eevee_identifier(context=None):
    """Return the render-engine identifier string for EEVEE.

    EEVEE's identifier has changed across versions (BLENDER_EEVEE ->
    BLENDER_EEVEE_NEXT and back, per ground rule #3). Rather than hardcode
    either string, scan the live enum for anything containing 'EEVEE' and
    cache the result for this session.
    """
    if "eevee" in _engine_cache:
        return _engine_cache["eevee"]
    items = _scene_engine_enum_items(context)
    matches = [i.identifier for i in items if "EEVEE" in i.identifier.upper()]
    if not matches:
        raise SocketResolutionError(
            f"Could not find an EEVEE render engine identifier. Available: "
            f"{[i.identifier for i in items]}."
        )
    # Prefer the exact legacy name if present, otherwise take the first match.
    chosen = "BLENDER_EEVEE" if "BLENDER_EEVEE" in matches else matches[0]
    _engine_cache["eevee"] = chosen
    return chosen


def is_cycles(context=None):
    context = context or bpy.context
    try:
        return context.scene.render.engine == get_cycles_identifier(context)
    except SocketResolutionError:
        return False


def is_eevee(context=None):
    context = context or bpy.context
    try:
        return context.scene.render.engine == get_eevee_identifier(context)
    except SocketResolutionError:
        return False


def pointiness_supported(context=None):
    """Geometry node's Pointiness output and the Bevel node only evaluate
    meaningfully under Cycles — under EEVEE they exist in the UI but read
    back as flat/zero. 'Supported' here means 'will actually produce a
    useful mask', not 'the node type exists'."""
    return is_cycles(context)


def bevel_node_supported(context=None):
    return is_cycles(context)
