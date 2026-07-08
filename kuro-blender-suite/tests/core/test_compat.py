"""Tests for kuro_core.compat — version gate, socket resolution, engine detection."""

import bpy

from kuro_core import compat
from tests import harness


def test_check_min_version_passes_on_current_blender():
    # This suite only runs on Blender >= MIN_BLENDER_VERSION anyway (see
    # scripts/test.sh), so this should never raise here.
    compat.check_min_version()


def test_resolve_canonical_socket_name():
    mat = bpy.data.materials.new("kuro_test_mat")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    socket = compat.resolve_input_socket(bsdf, "Base Color")
    harness.assert_equal(socket.name, "Base Color")


def test_resolve_missing_socket_raises_clear_error():
    mat = bpy.data.materials.new("kuro_test_mat2")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    harness.assert_raises(compat.SocketResolutionError, compat.resolve_input_socket, bsdf, "Not A Real Socket")


def test_set_input_writes_default_value():
    mat = bpy.data.materials.new("kuro_test_mat3")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    compat.set_input(bsdf, "Roughness", 0.25)
    harness.assert_almost_equal(bsdf.inputs["Roughness"].default_value, 0.25)


def test_engine_identifiers_resolve_without_raising():
    cycles_id = compat.get_cycles_identifier()
    harness.assert_equal(cycles_id, "CYCLES")
    eevee_id = compat.get_eevee_identifier()
    harness.assert_true("EEVEE" in eevee_id.upper(), f"unexpected eevee id: {eevee_id}")


def test_is_cycles_is_eevee_are_mutually_exclusive():
    scene = bpy.context.scene
    scene.render.engine = compat.get_cycles_identifier()
    harness.assert_true(compat.is_cycles())
    harness.assert_true(not compat.is_eevee())

    scene.render.engine = compat.get_eevee_identifier()
    harness.assert_true(compat.is_eevee())
    harness.assert_true(not compat.is_cycles())


def test_pointiness_and_bevel_supported_track_engine():
    scene = bpy.context.scene
    scene.render.engine = compat.get_cycles_identifier()
    harness.assert_true(compat.pointiness_supported())
    harness.assert_true(compat.bevel_node_supported())

    scene.render.engine = compat.get_eevee_identifier()
    harness.assert_true(not compat.pointiness_supported())
    harness.assert_true(not compat.bevel_node_supported())
