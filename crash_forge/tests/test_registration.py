"""Tier B (§13): import the real add-on under a stubbed bpy, register() then
unregister(), assert no leaked classes and no exceptions. This is exactly
the class of error that made v1 unloadable.
"""
import pytest


def test_register_unregister_clean(stubbed_bpy):
    crash_forge = stubbed_bpy
    import bpy  # resolves to tests/stubs/bpy.py once the fixture has run

    assert bpy.registered_classes() == []

    crash_forge.register()
    assert len(bpy.registered_classes()) > 0

    crash_forge.unregister()
    assert bpy.registered_classes() == []


def test_scene_pointer_property_cleaned_up(stubbed_bpy):
    crash_forge = stubbed_bpy
    import bpy

    crash_forge.register()
    assert hasattr(bpy.types.Scene, "crash_forge")

    crash_forge.unregister()
    assert not hasattr(bpy.types.Scene, "crash_forge")


def test_double_register_without_unregister_raises(stubbed_bpy):
    crash_forge = stubbed_bpy

    crash_forge.register()
    try:
        with pytest.raises(ValueError):
            crash_forge.register()
    finally:
        crash_forge.unregister()
