"""API introspection helpers — ground rule #2: never guess a bpy API name.

Run this once on the target Blender (5.1.2) before trusting any of the
"written without a live Blender" call-outs in this codebase's docstrings
(kuro_core/compat.py, stormkit/sky.py, stormkit/precipitation.py,
stormkit/wetness.py, stormkit/wind.py) — this dev container has no
`blender` binary, so those were written from documented API knowledge,
not live introspection.

Usage:
    blender --background --factory-startup --python scripts/introspect.py
"""

import bpy


def _section(title):
    print(f"\n=== {title} ===")


def introspect_principled_bsdf():
    _section("Principled BSDF inputs (compare against kuro_core.compat.PRINCIPLED_ALIASES)")
    mat = bpy.data.materials.new("_introspect_tmp_mat")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    for s in bsdf.inputs:
        print(f"  {s.name!r}")
    bpy.data.materials.remove(mat)


def introspect_render_engines():
    _section("Render engine enum (compare against kuro_core.compat.get_cycles/eevee_identifier)")
    items = bpy.context.scene.render.bl_rna.properties["engine"].enum_items
    for item in items:
        print(f"  {item.identifier}")


def introspect_mix_node():
    _section("Unified Mix node sockets by data_type (compare against sky.py/wetness.py/wind.py)")
    mat = bpy.data.materials.new("_introspect_tmp_mix")
    mat.use_nodes = True
    tree = mat.node_tree
    for data_type in ("FLOAT", "VECTOR", "RGBA"):
        node = tree.nodes.new("ShaderNodeMix")
        node.data_type = data_type
        print(f"  data_type={data_type}")
        print(f"    inputs:  {[s.name for s in node.inputs]}")
        print(f"    outputs: {[s.name for s in node.outputs]}")
        tree.nodes.remove(node)
    bpy.data.materials.remove(mat)


def introspect_gn_nodes():
    _section("Geometry Nodes sockets used by stormkit/precipitation.py + wetness.py snow geometry")
    tree = bpy.data.node_groups.new("_introspect_gn", "GeometryNodeTree")
    idnames = (
        "GeometryNodeBoundBox", "GeometryNodeMeshGrid", "GeometryNodeDistributePointsOnFaces",
        "GeometryNodeSetPosition", "GeometryNodeInstanceOnPoints", "GeometryNodeSetMaterial",
        "GeometryNodeMeshCylinder", "GeometryNodeMeshIcoSphere", "GeometryNodeInputSceneTime",
        "GeometryNodeInputIndex", "GeometryNodeInputPosition", "GeometryNodeInputNormal",
        "GeometryNodeExtrudeMesh", "FunctionNodeRandomValue", "FunctionNodeAlignEulerToVector",
    )
    for idname in idnames:
        try:
            node = tree.nodes.new(idname)
            print(f"  {idname}")
            print(f"    inputs:  {[s.name for s in node.inputs]}")
            print(f"    outputs: {[s.name for s in node.outputs]}")
            tree.nodes.remove(node)
        except RuntimeError as e:
            print(f"  {idname}: FAILED to create — {e}")
    bpy.data.node_groups.remove(tree)


def introspect_field_settings():
    _section("Object.field (force field) — compare against stormkit/wind.py")
    obj = bpy.data.objects.new("_introspect_empty", None)
    print(f"  field is None before any type is set: {obj.field is None}")
    obj.field.type = "WIND"
    print(f"  FieldSettings props: {[p.identifier for p in obj.field.bl_rna.properties]}")
    bpy.data.objects.remove(obj)


def introspect_musgrave_and_extensions():
    _section("Feature flags")
    print(f"  ShaderNodeTexMusgrave present: {hasattr(bpy.types, 'ShaderNodeTexMusgrave')}")
    print(f"  bpy.app.version: {bpy.app.version}")


if __name__ == "__main__":
    introspect_principled_bsdf()
    introspect_render_engines()
    introspect_mix_node()
    introspect_gn_nodes()
    introspect_field_settings()
    introspect_musgrave_and_extensions()
    print(
        "\nDone. Diff this output against the docstrings above and "
        "kuro_core/compat.py; record anything that differs in DECISIONS.md."
    )
