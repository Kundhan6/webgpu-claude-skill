"""Build the manual-QA .blend for Krish: a small city-street-ish base
scene, duplicated once per StormKit preset with that preset applied to
the copy (§4.6 "Manual QA .blend for Krish").

Usage:
    blender --background --factory-startup --python scripts/build_qa_blend.py -- [output.blend]

(defaults to qa_stormkit.blend at the repo root if no path is given)
"""

import os
import sys

import bpy

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import stormkit  # noqa: E402
from stormkit import presets as sk_presets  # noqa: E402


def build_base_street(scene):
    bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, 0))
    ground = bpy.context.active_object
    ground.name = "QA_Ground"
    mat = bpy.data.materials.new("QA_Asphalt")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.05, 0.05, 0.055, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.8
    ground.data.materials.append(mat)

    for i in range(6):
        height = 3 + (i % 4) * 2
        bpy.ops.mesh.primitive_cube_add(size=1, location=((i - 2.5) * 5, 6, height / 2))
        building = bpy.context.active_object
        building.scale = (2, 2, height / 2)
        building.name = f"QA_Building_{i}"
        mat = bpy.data.materials.new(f"QA_BuildingMat_{i}")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes["Principled BSDF"]
        bsdf.inputs["Base Color"].default_value = (0.5 + 0.05 * i, 0.5, 0.52, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.5
        building.data.materials.append(mat)

    bpy.ops.object.camera_add(location=(0, -12, 3), rotation=(1.4, 0, 0))
    scene.camera = bpy.context.active_object


def main():
    output_path = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv and len(sys.argv) > sys.argv.index("--") + 1 else os.path.join(REPO_ROOT, "qa_stormkit.blend")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    stormkit.register()

    base_scene = bpy.context.scene
    base_scene.name = "QA_Base"
    build_base_street(base_scene)

    for name, _path in sk_presets.list_presets():
        data = sk_presets.load(name)
        scene_copy = base_scene.copy()
        scene_copy.name = f"QA_{data.get('name', name)}"
        # temp_override redirects context.scene for this block without
        # needing a real window — this script runs under --background.
        with bpy.context.temp_override(scene=scene_copy):
            sk_presets.apply_to_scene(bpy.context, data)
            bpy.ops.stormkit.apply_to_scene()

    if bpy.context.window:
        bpy.context.window.scene = base_scene
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(output_path))
    print(f"Saved QA blend to {os.path.abspath(output_path)}")


if __name__ == "__main__":
    main()
