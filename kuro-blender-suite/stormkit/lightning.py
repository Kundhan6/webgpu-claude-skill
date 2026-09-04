"""Lightning subsystem — §4.2.6.

Pre-generates a fixed set of bolt curve objects (recursive midpoint
displacement, curve-bevel "skin") plus one flash light. Which bolt is
visible and how bright the flash is at any given frame is a *pure
function* of (frame, per-scene seed, storm_intensity) — see
`lightning_state_at_frame` below — computed via a cheap integer hash, not
a stored schedule. That makes the one frame_change_post handler this
add-on registers truly O(1) (ground rule #8's one allowed exception) and
makes the whole scheduling algorithm trivially unit-testable without
needing to step Blender through hundreds of frames.

"Bake Lightning" converts that same pure function into real keyframes
(via plain `keyframe_insert`, never touching `.action.fcurves` directly —
ground rule #3 calls out the slotted-action API break specifically for
"lightning bake" by name, so this deliberately never manipulates FCurves
by hand) so a render farm doesn't depend on the handler at all.
"""

import random

import bpy

from kuro_core import nodeutils

ADDON_ID = "stormkit:lightning"

BOLT_COUNT = 6
BOLT_NAME_PREFIX = "SK_Bolt"
BOLT_MATERIAL_NAME = "SK_LightningMaterial"
FLASH_LIGHT_NAME = "SK_LightningFlash"
LIGHTNING_SEED_PROP = "kuro_lightning_seed"
MAX_FLASH_ENERGY = 400.0
LOOKBACK_FRAMES = 3
BASE_TRIGGER_PROB = 0.03


# ---------------------------------------------------------------------------
# Pure, deterministic scheduling — no external state, trivially testable.
# ---------------------------------------------------------------------------

def _hash01(*ints):
    h = 2166136261
    for v in ints:
        h = ((h ^ (int(v) & 0xFFFFFFFF)) * 16777619) & 0xFFFFFFFF
    return h / 0xFFFFFFFF


def is_trigger_frame(frame, seed, storm_intensity, base_prob=BASE_TRIGGER_PROB):
    if storm_intensity <= 0.0:
        return False
    return _hash01(frame, seed, 1) < storm_intensity * base_prob


def bolt_index_for_frame(frame, seed, bolt_count=BOLT_COUNT):
    return int(_hash01(frame, seed, 2) * bolt_count) % bolt_count


def lightning_state_at_frame(frame, seed, storm_intensity, bolt_count=BOLT_COUNT):
    """Return (active_bolt_index_or_None, flash_factor 0..1) for `frame`.

    Pure function of its arguments — safe to call from a handler every
    frame with no accumulated state, and safe to call directly from a
    test for any frame without simulating the frames before it.
    """
    if storm_intensity <= 0.0:
        return None, 0.0
    best_index, best_factor = None, 0.0
    for back in range(LOOKBACK_FRAMES):
        f = frame - back
        if is_trigger_frame(f, seed, storm_intensity):
            factor = max(0.0, 1.0 - back / LOOKBACK_FRAMES)
            if factor > best_factor:
                best_factor = factor
                best_index = bolt_index_for_frame(f, seed, bolt_count)
    return best_index, best_factor


# ---------------------------------------------------------------------------
# Scene objects
# ---------------------------------------------------------------------------

def _generate_bolt_points(seed, start, end, iterations=5, displacement=1.2):
    rng = random.Random(seed)
    points = [start, end]
    for _ in range(iterations):
        new_points = [points[0]]
        for i in range(len(points) - 1):
            a, b = points[i], points[i + 1]
            mid = tuple((a[c] + b[c]) / 2.0 for c in range(3))
            offset = (rng.uniform(-1, 1) * displacement, rng.uniform(-1, 1) * displacement, 0.0)
            mid = tuple(mid[c] + offset[c] for c in range(3))
            new_points.append(mid)
            new_points.append(b)
        points = new_points
        displacement *= 0.55
    return points


def _ensure_material():
    mat = bpy.data.materials.get(BOLT_MATERIAL_NAME)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(BOLT_MATERIAL_NAME)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (0.8, 0.87, 1.0, 1.0)
        bsdf.inputs["Emission Color"].default_value = (0.8, 0.87, 1.0, 1.0)
        bsdf.inputs["Emission Strength"].default_value = 25.0
    mat[nodeutils.ADDON_PROP] = ADDON_ID
    return mat


def _bolt_name(i):
    return f"{BOLT_NAME_PREFIX}{i}"


def _ensure_bolts(context):
    mat = _ensure_material()
    bolts = []
    for i in range(BOLT_COUNT):
        name = _bolt_name(i)
        obj = bpy.data.objects.get(name)
        if obj is None:
            curve = bpy.data.curves.new(name, "CURVE")
            curve.dimensions = "3D"
            curve.bevel_depth = 0.03
            curve.bevel_resolution = 1
            start = (0.0, 0.0, 12.0)
            end = ((i - (BOLT_COUNT - 1) / 2.0) * 1.5, 0.0, 0.0)
            points = _generate_bolt_points(seed=i, start=start, end=end)
            spline = curve.splines.new("POLY")
            spline.points.add(len(points) - 1)
            for idx, p in enumerate(points):
                spline.points[idx].co = (p[0], p[1], p[2], 1.0)
            obj = bpy.data.objects.new(name, curve)
            context.scene.collection.objects.link(obj)
        if not obj.data.materials:
            obj.data.materials.append(mat)
        obj.hide_viewport = True
        obj.hide_render = True
        obj[nodeutils.ADDON_PROP] = ADDON_ID
        bolts.append(obj)
    return bolts


def _ensure_flash_light(context):
    obj = bpy.data.objects.get(FLASH_LIGHT_NAME)
    if obj is None:
        light_data = bpy.data.lights.new(FLASH_LIGHT_NAME, type="AREA")
        light_data.size = 20.0
        light_data.color = (0.8, 0.85, 1.0)
        light_data.energy = 0.0
        obj = bpy.data.objects.new(FLASH_LIGHT_NAME, light_data)
        context.scene.collection.objects.link(obj)
        obj.location = (0.0, 0.0, 15.0)
    obj[nodeutils.ADDON_PROP] = ADDON_ID
    obj.data[nodeutils.ADDON_PROP] = ADDON_ID
    return obj


def build(context):
    """Idempotent — safe to call repeatedly."""
    scene = context.scene
    if LIGHTNING_SEED_PROP not in scene:
        scene[LIGHTNING_SEED_PROP] = random.randint(0, 2**31 - 1)
    bolts = _ensure_bolts(context)
    flash = _ensure_flash_light(context)
    return bolts, flash


def teardown(context):
    for i in range(BOLT_COUNT):
        obj = bpy.data.objects.get(_bolt_name(i))
        if obj is not None and obj.get(nodeutils.ADDON_PROP) == ADDON_ID:
            curve = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if curve is not None and curve.users == 0:
                bpy.data.curves.remove(curve)

    flash = bpy.data.objects.get(FLASH_LIGHT_NAME)
    if flash is not None and flash.get(nodeutils.ADDON_PROP) == ADDON_ID:
        light_data = flash.data
        bpy.data.objects.remove(flash, do_unlink=True)
        if light_data is not None and light_data.users == 0:
            bpy.data.lights.remove(light_data)

    mat = bpy.data.materials.get(BOLT_MATERIAL_NAME)
    if mat is not None and mat.users == 0:
        bpy.data.materials.remove(mat)

    if LIGHTNING_SEED_PROP in context.scene:
        del context.scene[LIGHTNING_SEED_PROP]


# ---------------------------------------------------------------------------
# Per-frame O(1) handler — the one exception ground rule #8 allows.
# ---------------------------------------------------------------------------

def _hide_all_bolts():
    for i in range(BOLT_COUNT):
        obj = bpy.data.objects.get(_bolt_name(i))
        if obj is not None:
            obj.hide_viewport = True
            obj.hide_render = True


def _show_only(index):
    for i in range(BOLT_COUNT):
        obj = bpy.data.objects.get(_bolt_name(i))
        if obj is None:
            continue
        visible = i == index
        obj.hide_viewport = not visible
        obj.hide_render = not visible


def _set_flash_energy(energy):
    obj = bpy.data.objects.get(FLASH_LIGHT_NAME)
    if obj is not None and obj.data is not None:
        obj.data.energy = energy


def _on_frame_change(scene, _depsgraph=None):
    stormkit = getattr(scene, "stormkit", None)
    intensity = stormkit.storm_intensity if stormkit is not None else 0.0
    if intensity <= 0.0:
        _hide_all_bolts()
        _set_flash_energy(0.0)
        return
    seed = scene.get(LIGHTNING_SEED_PROP, 0)
    index, factor = lightning_state_at_frame(scene.frame_current, seed, intensity)
    if index is None:
        _hide_all_bolts()
    else:
        _show_only(index)
    _set_flash_energy(factor * MAX_FLASH_ENERGY)


def register():
    if _on_frame_change not in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.append(_on_frame_change)


def unregister():
    if _on_frame_change in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.remove(_on_frame_change)


# ---------------------------------------------------------------------------
# Bake to keyframes (farm-safe — no dependency on the handler at render time)
# ---------------------------------------------------------------------------

def bake_lightning(context, frame_start=None, frame_end=None):
    scene = context.scene
    frame_start = scene.frame_start if frame_start is None else frame_start
    frame_end = scene.frame_end if frame_end is None else frame_end
    seed = scene.get(LIGHTNING_SEED_PROP, 0)
    intensity = scene.stormkit.storm_intensity

    bolts = _ensure_bolts(context)
    flash = _ensure_flash_light(context)

    for frame in range(frame_start, frame_end + 1):
        index, factor = lightning_state_at_frame(frame, seed, intensity, len(bolts))
        for i, bolt in enumerate(bolts):
            visible = i == index
            bolt.hide_viewport = not visible
            bolt.hide_render = not visible
            bolt.keyframe_insert("hide_viewport", frame=frame)
            bolt.keyframe_insert("hide_render", frame=frame)
        flash.data.energy = factor * MAX_FLASH_ENERGY
        flash.data.keyframe_insert("energy", frame=frame)

    return frame_end - frame_start + 1
