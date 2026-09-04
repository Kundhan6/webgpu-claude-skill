"""Tests for stormkit.lightning — pure scheduling function, build/teardown,
handler idempotency (ground rule #6), and bake-to-keyframes."""

import bpy

from kuro_core import nodeutils
from stormkit import lightning, properties
from tests import harness


def _ensure_registered():
    try:
        properties.register()
    except ValueError:
        pass


def test_is_trigger_frame_is_deterministic():
    a = lightning.is_trigger_frame(42, seed=7, storm_intensity=1.0)
    b = lightning.is_trigger_frame(42, seed=7, storm_intensity=1.0)
    harness.assert_equal(a, b)


def test_zero_intensity_never_triggers():
    for frame in range(1, 500):
        harness.assert_true(not lightning.is_trigger_frame(frame, seed=1, storm_intensity=0.0))
    index, factor = lightning.lightning_state_at_frame(100, seed=1, storm_intensity=0.0)
    harness.assert_true(index is None)
    harness.assert_equal(factor, 0.0)


def test_full_intensity_triggers_a_reasonable_fraction_of_frames():
    seed = 123
    triggers = sum(1 for f in range(1, 2000) if lightning.is_trigger_frame(f, seed, 1.0))
    fraction = triggers / 2000
    # BASE_TRIGGER_PROB is 0.03; a hash-based approximation should land
    # within a generous band of that, not exactly on it.
    harness.assert_true(0.01 < fraction < 0.06, f"unexpected trigger fraction: {fraction}")


def test_lightning_state_bolt_index_is_in_range():
    seed = 5
    for frame in range(1, 500):
        index, factor = lightning.lightning_state_at_frame(frame, seed, 1.0)
        if index is not None:
            harness.assert_true(0 <= index < lightning.BOLT_COUNT)
            harness.assert_true(0.0 < factor <= 1.0)


def test_build_creates_all_bolts_and_flash_light():
    _ensure_registered()
    context = bpy.context
    bolts, flash = lightning.build(context)

    harness.assert_equal(len(bolts), lightning.BOLT_COUNT)
    for bolt in bolts:
        harness.assert_equal(bolt[nodeutils.ADDON_PROP], lightning.ADDON_ID)
        harness.assert_true(bolt.hide_viewport and bolt.hide_render)
    harness.assert_equal(flash.data.type, "AREA")
    harness.assert_true(lightning.LIGHTNING_SEED_PROP in context.scene)


def test_build_is_idempotent_and_seed_is_stable():
    _ensure_registered()
    context = bpy.context
    lightning.build(context)
    seed_first = context.scene[lightning.LIGHTNING_SEED_PROP]
    lightning.build(context)
    seed_second = context.scene[lightning.LIGHTNING_SEED_PROP]

    harness.assert_equal(seed_first, seed_second)
    bolt_objs = [o for o in bpy.data.objects if o.name.startswith(lightning.BOLT_NAME_PREFIX)]
    harness.assert_equal(len(bolt_objs), lightning.BOLT_COUNT)


def test_register_unregister_is_idempotent_no_duplicate_handlers():
    lightning.register()
    lightning.register()
    count = bpy.app.handlers.frame_change_post.count(lightning._on_frame_change)
    harness.assert_equal(count, 1)

    lightning.unregister()
    lightning.unregister()
    count = bpy.app.handlers.frame_change_post.count(lightning._on_frame_change)
    harness.assert_equal(count, 0)


def test_on_frame_change_shows_bolt_only_on_a_known_trigger_frame():
    _ensure_registered()
    context = bpy.context
    lightning.build(context)
    context.scene.stormkit.storm_intensity = 1.0
    seed = context.scene[lightning.LIGHTNING_SEED_PROP]

    trigger_frame = next(f for f in range(1, 2000) if lightning.is_trigger_frame(f, seed, 1.0))
    non_trigger_frame = next(
        f for f in range(1, 2000)
        if not any(lightning.is_trigger_frame(f - back, seed, 1.0) for back in range(lightning.LOOKBACK_FRAMES))
    )

    context.scene.frame_current = trigger_frame
    lightning._on_frame_change(context.scene)
    visible_bolts = [o for o in bpy.data.objects if o.name.startswith(lightning.BOLT_NAME_PREFIX) and not o.hide_viewport]
    harness.assert_equal(len(visible_bolts), 1)

    context.scene.frame_current = non_trigger_frame
    lightning._on_frame_change(context.scene)
    visible_bolts = [o for o in bpy.data.objects if o.name.startswith(lightning.BOLT_NAME_PREFIX) and not o.hide_viewport]
    harness.assert_equal(len(visible_bolts), 0)


def test_bake_lightning_inserts_keyframes_across_range():
    _ensure_registered()
    context = bpy.context
    context.scene.stormkit.storm_intensity = 1.0
    lightning.build(context)

    frame_count = lightning.bake_lightning(context, frame_start=1, frame_end=48)
    harness.assert_equal(frame_count, 48)

    flash = bpy.data.objects.get(lightning.FLASH_LIGHT_NAME)
    harness.assert_true(flash.data.animation_data is not None)
    harness.assert_true(flash.data.animation_data.action is not None)


def test_teardown_removes_bolts_flash_and_material():
    _ensure_registered()
    context = bpy.context
    lightning.build(context)
    lightning.teardown(context)

    remaining_bolts = [o for o in bpy.data.objects if o.name.startswith(lightning.BOLT_NAME_PREFIX)]
    harness.assert_equal(len(remaining_bolts), 0)
    harness.assert_true(bpy.data.objects.get(lightning.FLASH_LIGHT_NAME) is None)
    harness.assert_true(bpy.data.materials.get(lightning.BOLT_MATERIAL_NAME) is None)
