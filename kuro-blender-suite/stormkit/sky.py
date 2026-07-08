"""Sky & Sun subsystem — §4.2.1.

Builds a tagged Nishita sky in the scene World, syncs a tagged Sun lamp to
it, and blends toward flat overcast grey as scene.stormkit.overcast rises.
Everything is wired with drivers at build() time — no per-frame Python
(ground rule #8). build()/teardown() are both idempotent.

NOTE on API confidence: ShaderNodeTexSky.sky_type='NISHITA' and its
sun_elevation/sun_rotation float properties are long-standing, stable
Blender API (the same pattern the bundled "Sun Position" add-on uses).
The unified Mix node ('ShaderNodeMix', data_type='RGBA', sockets
Factor/A/B/Result) reflects the 3.4+ node-mix unification and is expected
to still be current on 5.1.2, but was written without a live Blender to
confirm against (no `blender` binary in this dev container — see
DECISIONS.md). Run scripts/introspect.py on the target Blender before
trusting it blindly, per ground rule #2.
"""

import json
import math

import bpy

from kuro_core import nodeutils

ADDON_ID = "stormkit:sky"

SKY_NODE_NAME = "SK_SkyTexture"
BACKGROUND_NODE_NAME = "SK_Background"
MIX_NODE_NAME = "SK_OvercastMix"
GREY_NODE_NAME = "SK_OvercastGrey"
SUN_OBJECT_NAME = "SK_Sun"
ORIGINAL_SURFACE_PROP = "kuro_sky_original_surface"


def _ensure_world(context):
    scene = context.scene
    if scene.world is None:
        scene.world = bpy.data.worlds.new("World")
    world = scene.world
    if not world.use_nodes:
        world.use_nodes = True
    return world


def _find_world_output(tree):
    outputs = [n for n in tree.nodes if n.bl_idname == "ShaderNodeOutputWorld"]
    for node in outputs:
        if getattr(node, "is_active_output", True):
            return node
    if outputs:
        return outputs[0]
    return tree.nodes.new("ShaderNodeOutputWorld")


def _rewire_output(tree, world, output, source_node, source_socket):
    """Reroute World Output's Surface input to `source_node.outputs[source_socket]`,
    recording whatever fed it before (once, on first build) so a full
    StormKit removal can put it back."""
    surface = output.inputs["Surface"]
    if ORIGINAL_SURFACE_PROP not in world:
        existing = next((link for link in tree.links if link.to_socket == surface), None)
        if existing is not None:
            record = {
                "had_link": True,
                "from_node": existing.from_node.name,
                "from_socket": existing.from_socket.name,
            }
        else:
            record = {"had_link": False}
        world[ORIGINAL_SURFACE_PROP] = json.dumps(record)

    for link in list(tree.links):
        if link.to_socket == surface:
            tree.links.remove(link)
    tree.links.new(source_node.outputs[source_socket], surface)


def restore_original_output(world):
    """Reverse `_rewire_output` — used by the full "Remove StormKit" sweep."""
    if world is None or ORIGINAL_SURFACE_PROP not in world:
        return
    tree = world.node_tree
    output = _find_world_output(tree)
    surface = output.inputs["Surface"]
    record = json.loads(world[ORIGINAL_SURFACE_PROP])

    for link in list(tree.links):
        if link.to_socket == surface:
            tree.links.remove(link)
    if record.get("had_link"):
        from_node = tree.nodes.get(record["from_node"])
        from_socket = from_node.outputs.get(record["from_socket"]) if from_node else None
        if from_socket is not None:
            tree.links.new(from_socket, surface)
    del world[ORIGINAL_SURFACE_PROP]


def _ensure_sun_object(context):
    obj = bpy.data.objects.get(SUN_OBJECT_NAME)
    if obj is None:
        light_data = bpy.data.lights.new(SUN_OBJECT_NAME, type="SUN")
        obj = bpy.data.objects.new(SUN_OBJECT_NAME, light_data)
        context.scene.collection.objects.link(obj)
    obj[nodeutils.ADDON_PROP] = ADDON_ID
    obj.data[nodeutils.ADDON_PROP] = ADDON_ID
    return obj


def _clear_drivers(datablock, *data_paths):
    for path in data_paths:
        try:
            datablock.driver_remove(path)
        except Exception:
            pass


def _wire_drivers(context, world, sky_node, sun_obj):
    scene = context.scene

    _clear_drivers(sky_node, "sun_elevation", "sun_rotation")
    _clear_drivers(sun_obj, "rotation_euler")
    _clear_drivers(sun_obj.data, "energy", "angle")

    # Sky node's virtual sun position: simple solar arc from time_of_day,
    # scaled by latitude (see properties.py for why latitude lives on the
    # scene state rather than add-on preferences).
    fcurve = sky_node.driver_add("sun_elevation")
    driver = fcurve.driver
    driver.type = "SCRIPTED"
    var_t = driver.variables.new()
    var_t.name = "t"
    var_t.type = "SINGLE_PROP"
    var_t.targets[0].id_type = "SCENE"
    var_t.targets[0].id = scene
    var_t.targets[0].data_path = "stormkit.time_of_day"
    var_lat = driver.variables.new()
    var_lat.name = "lat"
    var_lat.type = "SINGLE_PROP"
    var_lat.targets[0].id_type = "SCENE"
    var_lat.targets[0].id = scene
    var_lat.targets[0].data_path = "stormkit.latitude"
    driver.expression = (
        "sin(pi * min(max((t - 6.0) / 12.0, -1.0), 1.0)) "
        "* (pi / 2.0 - abs(radians(lat)) * 0.3)"
    )

    fcurve = sky_node.driver_add("sun_rotation")
    driver = fcurve.driver
    driver.type = "SCRIPTED"
    var_t = driver.variables.new()
    var_t.name = "t"
    var_t.type = "SINGLE_PROP"
    var_t.targets[0].id_type = "SCENE"
    var_t.targets[0].id = scene
    var_t.targets[0].data_path = "stormkit.time_of_day"
    driver.expression = "(t / 24.0) * 2.0 * pi - pi"

    # Sun object follows the sky node's virtual sun so both stay in sync
    # without duplicating the solar-arc math.
    fcurve = sun_obj.driver_add("rotation_euler", 0)
    driver = fcurve.driver
    driver.type = "SCRIPTED"
    var_e = driver.variables.new()
    var_e.name = "e"
    var_e.type = "SINGLE_PROP"
    var_e.targets[0].id_type = "WORLD"
    var_e.targets[0].id = world
    var_e.targets[0].data_path = f'node_tree.nodes["{SKY_NODE_NAME}"].sun_elevation'
    driver.expression = "pi / 2.0 - e"

    fcurve = sun_obj.driver_add("rotation_euler", 2)
    driver = fcurve.driver
    driver.type = "SCRIPTED"
    var_a = driver.variables.new()
    var_a.name = "a"
    var_a.type = "SINGLE_PROP"
    var_a.targets[0].id_type = "WORLD"
    var_a.targets[0].id = world
    var_a.targets[0].data_path = f'node_tree.nodes["{SKY_NODE_NAME}"].sun_rotation'
    driver.expression = "a"

    # Direct light falls off with sin(elevation) and dims/softens with overcast.
    fcurve = sun_obj.data.driver_add("energy")
    driver = fcurve.driver
    driver.type = "SCRIPTED"
    var_e = driver.variables.new()
    var_e.name = "e"
    var_e.type = "SINGLE_PROP"
    var_e.targets[0].id_type = "WORLD"
    var_e.targets[0].id = world
    var_e.targets[0].data_path = f'node_tree.nodes["{SKY_NODE_NAME}"].sun_elevation'
    var_o = driver.variables.new()
    var_o.name = "o"
    var_o.type = "SINGLE_PROP"
    var_o.targets[0].id_type = "SCENE"
    var_o.targets[0].id = scene
    var_o.targets[0].data_path = "stormkit.overcast"
    driver.expression = "max(0.0, sin(e)) * (1.0 - o * 0.85) * 3.0"

    fcurve = sun_obj.data.driver_add("angle")
    driver = fcurve.driver
    driver.type = "SCRIPTED"
    var_o = driver.variables.new()
    var_o.name = "o"
    var_o.type = "SINGLE_PROP"
    var_o.targets[0].id_type = "SCENE"
    var_o.targets[0].id = scene
    var_o.targets[0].data_path = "stormkit.overcast"
    driver.expression = "radians(0.526) + o * radians(15.0)"

    # World background blend toward flat overcast grey.
    mix = world.node_tree.nodes.get(MIX_NODE_NAME)
    if mix is not None:
        _clear_drivers(mix.inputs["Factor"], "default_value")
        fcurve = mix.inputs["Factor"].driver_add("default_value")
        driver = fcurve.driver
        driver.type = "AVERAGE"
        var_o = driver.variables.new()
        var_o.name = "o"
        var_o.type = "SINGLE_PROP"
        var_o.targets[0].id_type = "SCENE"
        var_o.targets[0].id = scene
        var_o.targets[0].data_path = "stormkit.overcast"


def build(context):
    """Idempotent — safe to call repeatedly (e.g. every 'Apply to Scene')."""
    world = _ensure_world(context)
    tree = world.node_tree
    b = nodeutils.NodeGraphBuilder(tree)

    sky = b.get_or_add("ShaderNodeTexSky", SKY_NODE_NAME)
    sky.sky_type = "NISHITA"

    grey = b.get_or_add("ShaderNodeRGB", GREY_NODE_NAME)
    grey.outputs["Color"].default_value = (0.45, 0.47, 0.52, 1.0)

    mix = b.get_or_add("ShaderNodeMix", MIX_NODE_NAME)
    mix.data_type = "RGBA"

    background = b.get_or_add("ShaderNodeBackground", BACKGROUND_NODE_NAME)

    b.link(sky, "Color", mix, "A")
    b.link(grey, "Color", mix, "B")
    b.link(mix, "Result", background, "Color")

    output = _find_world_output(tree)
    _rewire_output(tree, world, output, background, "Background")

    b.tag_all(ADDON_ID)
    b.auto_layout()

    sun = _ensure_sun_object(context)
    _wire_drivers(context, world, sky, sun)

    return world, sky, sun


def teardown(context):
    """Remove everything this subsystem owns and restore the World's
    original Surface wiring. Part of the full "Remove StormKit" sweep."""
    world = context.scene.world
    if world is not None and world.node_tree is not None:
        nodeutils.eject(world.node_tree, ADDON_ID)  # no-op unless something used inject_between
        restore_original_output(world)
        for name in (SKY_NODE_NAME, GREY_NODE_NAME, MIX_NODE_NAME, BACKGROUND_NODE_NAME):
            node = world.node_tree.nodes.get(name)
            if node is not None:
                world.node_tree.nodes.remove(node)

    sun = bpy.data.objects.get(SUN_OBJECT_NAME)
    if sun is not None and sun.get(nodeutils.ADDON_PROP) == ADDON_ID:
        light_data = sun.data
        bpy.data.objects.remove(sun, do_unlink=True)
        if light_data is not None and light_data.users == 0:
            bpy.data.lights.remove(light_data)


def register():
    pass


def unregister():
    pass
