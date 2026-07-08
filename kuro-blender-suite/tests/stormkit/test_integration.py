"""Cross-cutting §4.6 acceptance tests that don't belong to one subsystem:
preset application on empty vs. populated scenes, full-removal datablock
accounting, handler idempotency across the whole add-on, and the
Apply-to-Scene operator's undo round-trip (ground rule #7).
"""

import bpy

from stormkit import lightning, operators, precipitation, presets as sk_presets, properties, ui, wetness
from tests import harness

ALL_MODULES = (properties, sk_presets, wetness, lightning, precipitation, operators, ui)


def _ensure_registered():
    for module in ALL_MODULES:
        try:
            module.register()
        except ValueError:
            pass  # already registered by an earlier test in this process


def _data_counts():
    return {
        "objects": len(bpy.data.objects),
        "materials": len(bpy.data.materials),
        "node_groups": len(bpy.data.node_groups),
        "lights": len(bpy.data.lights),
        "curves": len(bpy.data.curves),
        "meshes": len(bpy.data.meshes),
        "worlds": len(bpy.data.worlds),
    }


def _populate_scene(context, n_objects=50, n_materials=20):
    materials = []
    for i in range(n_materials):
        mat = bpy.data.materials.new(f"qa_mat_{i}")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes["Principled BSDF"]
        bsdf.inputs["Base Color"].default_value = (i / n_materials, 0.4, 1.0 - i / n_materials, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.2 + 0.6 * (i / n_materials)
        materials.append(mat)

    for i in range(n_objects):
        bpy.ops.mesh.primitive_cube_add(location=(i % 10 * 2.0, i // 10 * 2.0, 0.0))
        obj = bpy.context.active_object
        obj.data.materials.append(materials[i % n_materials])
    return materials


def test_apply_each_preset_on_empty_scene_without_error():
    _ensure_registered()
    context = bpy.context
    for name, _path in sk_presets.list_presets():
        data = sk_presets.load(name)
        sk_presets.apply_to_scene(context, data)
        bpy.ops.stormkit.apply_to_scene()


def test_apply_each_preset_on_populated_scene_without_error():
    _ensure_registered()
    context = bpy.context
    _populate_scene(context, n_objects=50, n_materials=20)

    for name, _path in sk_presets.list_presets():
        data = sk_presets.load(name)
        sk_presets.apply_to_scene(context, data)
        bpy.ops.stormkit.apply_to_scene()

    # every plain-Principled material should have been picked up by wetness
    qa_materials = [m for m in bpy.data.materials if m.name.startswith("qa_mat_")]
    harness.assert_equal(len(qa_materials), 20)


def test_full_remove_restores_datablock_counts():
    _ensure_registered()
    context = bpy.context
    _populate_scene(context, n_objects=50, n_materials=20)
    before = _data_counts()

    data = sk_presets.load("thunderstorm")
    sk_presets.apply_to_scene(context, data)
    bpy.ops.stormkit.apply_to_scene()

    after_apply = _data_counts()
    harness.assert_true(after_apply["objects"] > before["objects"], "expected StormKit to add objects")

    bpy.ops.stormkit.remove_all()
    after_removal = _data_counts()

    harness.assert_equal(after_removal, before)


def test_stormkit_handlers_are_idempotent_across_repeated_enable():
    _ensure_registered()
    lightning.register()
    lightning.register()
    precipitation.register()
    precipitation.register()

    harness.assert_equal(bpy.app.handlers.frame_change_post.count(lightning._on_frame_change), 1)
    harness.assert_equal(bpy.app.handlers.render_pre.count(precipitation._on_render_pre), 1)
    harness.assert_equal(bpy.app.handlers.render_post.count(precipitation._on_render_post), 1)


def test_apply_to_scene_operator_is_undoable():
    _ensure_registered()
    context = bpy.context
    before_objects = {o.name for o in bpy.data.objects}

    bpy.ops.stormkit.apply_to_scene()
    after_objects = {o.name for o in bpy.data.objects}
    harness.assert_true(len(after_objects) > len(before_objects), "expected Apply to Scene to add objects")

    bpy.ops.ed.undo()
    restored_objects = {o.name for o in bpy.data.objects}
    harness.assert_equal(restored_objects, before_objects, "expected undo to restore the pre-apply object set")
