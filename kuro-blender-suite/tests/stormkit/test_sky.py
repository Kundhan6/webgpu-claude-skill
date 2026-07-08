"""Tests for stormkit.sky — §4.6 build/idempotency/driver/teardown coverage."""

import bpy

from kuro_core import nodeutils
from stormkit import properties, sky
from tests import harness


def _ensure_registered():
    try:
        properties.register()
    except ValueError:
        pass


def _eval(datablock):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    depsgraph.update()
    return datablock.evaluated_get(depsgraph)


def test_build_creates_nishita_sky_and_tagged_sun():
    _ensure_registered()
    context = bpy.context
    world, sky_node, sun = sky.build(context)

    harness.assert_equal(sky_node.sky_type, "NISHITA")
    harness.assert_equal(sun.name, sky.SUN_OBJECT_NAME)
    harness.assert_equal(sun[nodeutils.ADDON_PROP], sky.ADDON_ID)
    harness.assert_true(sun in list(context.scene.collection.objects))


def test_build_is_idempotent():
    _ensure_registered()
    context = bpy.context
    sky.build(context)
    sky.build(context)

    world = context.scene.world
    sky_nodes = [n for n in world.node_tree.nodes if n.name == sky.SKY_NODE_NAME]
    harness.assert_equal(len(sky_nodes), 1)
    suns = [o for o in bpy.data.objects if o.name == sky.SUN_OBJECT_NAME]
    harness.assert_equal(len(suns), 1)


def test_time_of_day_drives_sun_elevation_higher_at_noon_than_midnight():
    _ensure_registered()
    context = bpy.context
    world, sky_node, sun = sky.build(context)

    context.scene.stormkit.time_of_day = 12.0
    noon_elevation = _eval(world).node_tree.nodes[sky.SKY_NODE_NAME].sun_elevation

    context.scene.stormkit.time_of_day = 0.0
    midnight_elevation = _eval(world).node_tree.nodes[sky.SKY_NODE_NAME].sun_elevation

    harness.assert_true(
        noon_elevation > midnight_elevation,
        f"expected noon elevation ({noon_elevation}) > midnight ({midnight_elevation})",
    )


def test_overcast_dims_sun_energy():
    _ensure_registered()
    context = bpy.context
    world, sky_node, sun = sky.build(context)
    context.scene.stormkit.time_of_day = 12.0

    context.scene.stormkit.overcast = 0.0
    clear_energy = _eval(sun).data.energy

    context.scene.stormkit.overcast = 1.0
    overcast_energy = _eval(sun).data.energy

    harness.assert_true(
        overcast_energy < clear_energy,
        f"expected overcast energy ({overcast_energy}) < clear energy ({clear_energy})",
    )


def test_teardown_restores_original_surface_link():
    _ensure_registered()
    context = bpy.context

    # Simulate a studio's pre-existing hand-built world shader.
    world = bpy.data.worlds.new("World")
    context.scene.world = world
    world.use_nodes = True
    tree = world.node_tree
    custom_bg = tree.nodes.new("ShaderNodeBackground")
    custom_bg.inputs["Color"].default_value = (0.9, 0.1, 0.1, 1.0)
    output = next(n for n in tree.nodes if n.bl_idname == "ShaderNodeOutputWorld")
    tree.links.new(custom_bg.outputs["Background"], output.inputs["Surface"])

    sky.build(context)
    harness.assert_true(output.inputs["Surface"].links[0].from_node.name == sky.BACKGROUND_NODE_NAME)

    sky.teardown(context)
    harness.assert_true(
        output.inputs["Surface"].links[0].from_node == custom_bg,
        "original hand-built background must be restored after teardown",
    )
    harness.assert_true(world.node_tree.nodes.get(sky.SKY_NODE_NAME) is None)
    harness.assert_true(bpy.data.objects.get(sky.SUN_OBJECT_NAME) is None)
