"""Node graph builder helpers: create, link, layout, tag.

Also home to the non-destructive inject/eject machinery that StormKit and
RuinFX depend on for wrapping existing materials without corrupting them.
"""

import json

ADDON_PROP = "kuro_addon"
RECORD_PROP = "kuro_inject_records"
SCHEMA_PROP = "kuro_schema_version"


class NodeGraphBuilder:
    """Fluent-ish helper for building a node graph inside a material's node
    tree or a standalone node group tree. Tracks every node it creates so
    `tag_all()` / `auto_layout()` only ever touch nodes from this build pass
    — never someone else's hand-authored nodes sitting in the same tree.
    """

    def __init__(self, tree_owner):
        if hasattr(tree_owner, "node_tree"):
            if not tree_owner.use_nodes:
                tree_owner.use_nodes = True
            self.tree = tree_owner.node_tree
        else:
            self.tree = tree_owner
        self._created = []

    def add(self, node_type, name=None, location=None, **inputs):
        """Create a node of `node_type` (a bl_idname like 'ShaderNodeTexNoise').

        Keyword args are matched against the new node's input sockets by
        name and used to set `default_value`. Raises a clear KeyError
        listing available sockets on mismatch, per ground rule #2 (never
        silently swallow an API-name miss).
        """
        node = self.tree.nodes.new(node_type)
        if name:
            node.name = name
            node.label = name
        if location:
            node.location = location
        for key, value in inputs.items():
            socket = node.inputs.get(key)
            if socket is None:
                raise KeyError(
                    f"Node '{node.name}' ({node_type}) has no input '{key}'. "
                    f"Available inputs: {[s.name for s in node.inputs]}"
                )
            socket.default_value = value
        self._created.append(node)
        return node

    def get_or_add(self, node_type, name, location=None, **inputs):
        """Fetch the existing node named `name` in this tree if present
        (tracking it so tag_all/auto_layout still see it), otherwise
        create it via `add()`. This is what makes subsystem `build()`
        functions idempotent — calling build() twice reuses nodes by name
        instead of duplicating them."""
        existing = self.tree.nodes.get(name)
        if existing is not None:
            self.track(existing)
            return existing
        return self.add(node_type, name=name, location=location, **inputs)

    def track(self, node):
        """Register an externally-fetched/created node so tag_all() and
        auto_layout() include it, without re-creating it."""
        if node not in self._created:
            self._created.append(node)
        return node

    @staticmethod
    def _resolve_socket(collection, ref):
        if isinstance(ref, str):
            return collection.get(ref)
        if isinstance(ref, int):
            return collection[ref] if 0 <= ref < len(collection) else None
        return ref

    def link(self, from_node, from_socket, to_node, to_socket):
        """Link `from_node`'s output socket to `to_node`'s input socket.

        `from_socket`/`to_socket` may be a socket name (str), an integer
        index (needed for nodes like Math whose two inputs are both
        literally named "Value"), or an actual NodeSocket reference.
        """
        out_socket = self._resolve_socket(from_node.outputs, from_socket)
        in_socket = self._resolve_socket(to_node.inputs, to_socket)
        if out_socket is None:
            raise KeyError(
                f"'{from_node.name}' has no output '{from_socket}'. "
                f"Available outputs: {[s.name for s in from_node.outputs]}"
            )
        if in_socket is None:
            raise KeyError(
                f"'{to_node.name}' has no input '{to_socket}'. "
                f"Available inputs: {[s.name for s in to_node.inputs]}"
            )
        return self.tree.links.new(out_socket, in_socket)

    def tag_all(self, addon_id):
        """Stamp every node created by this builder (and the tree itself)
        with the custom property that marks it as KURO-owned, per ground
        rule #5. `addon_id` should be "<addon>:<feature>", e.g.
        "stormkit:wetness"."""
        for node in self._created:
            node[ADDON_PROP] = addon_id
        self.tree[ADDON_PROP] = addon_id

    def auto_layout(self, x_spacing=260, y_spacing=220):
        """Grid-layout nodes by dependency depth (distance from the graph's
        sources) so generated graphs read left-to-right like a hand-built
        one — studios will open these in the shader editor."""
        nodes = self._created or list(self.tree.nodes)
        node_names = {n.name for n in nodes}
        depth = {}

        def compute_depth(node, stack):
            if node.name in depth:
                return depth[node.name]
            if node.name in stack:
                return 0  # defensive cycle guard; shader graphs are DAGs
            stack = stack | {node.name}
            upstream_depths = []
            for inp in node.inputs:
                for link in inp.links:
                    if link.from_node.name in node_names:
                        upstream_depths.append(compute_depth(link.from_node, stack))
            d = (max(upstream_depths) + 1) if upstream_depths else 0
            depth[node.name] = d
            return d

        for node in nodes:
            compute_depth(node, frozenset())

        columns = {}
        for node in nodes:
            columns.setdefault(depth[node.name], []).append(node)

        for col, col_nodes in columns.items():
            for row, node in enumerate(col_nodes):
                node.location = (col * x_spacing, -row * y_spacing)

    @property
    def created_nodes(self):
        return list(self._created)


def add_group_input(tree, name, socket_type="NodeSocketFloat", default=None,
                     min_value=None, max_value=None):
    """Add an exposed input socket to a node-group's interface (Blender 4.0+
    `NodeTreeInterface` API — the only API on our supported version range)."""
    item = tree.interface.new_socket(name=name, in_out="INPUT", socket_type=socket_type)
    if default is not None:
        item.default_value = default
    if min_value is not None:
        item.min_value = min_value
    if max_value is not None:
        item.max_value = max_value
    return item


def add_group_output(tree, name, socket_type="NodeSocketFloat"):
    return tree.interface.new_socket(name=name, in_out="OUTPUT", socket_type=socket_type)


def _clear_node_tree(tree):
    tree.nodes.clear()
    for item in list(tree.interface.items_tree):
        tree.interface.remove(item)


def ensure_group(name, builder_fn, schema_version=1, tree_type="ShaderNodeTree"):
    """Idempotent node-group creation.

    If a group named `name` already exists AND was built with the current
    `schema_version`, it is returned untouched (re-registering the add-on
    never duplicates groups). If it exists but is stale (older schema
    version) it is cleared and rebuilt in place — every material/modifier
    referencing it picks up the new internals automatically. If it
    doesn't exist yet, it's created fresh as a `tree_type` group
    ("ShaderNodeTree" for material node groups, "GeometryNodeTree" for
    Geometry Nodes modifier groups).

    `builder_fn(tree)` is responsible for declaring the interface sockets
    (via add_group_input/add_group_output) and building the internal node
    graph (typically via NodeGraphBuilder(tree)).
    """
    import bpy

    group = bpy.data.node_groups.get(name)
    if group is not None and group.get(SCHEMA_PROP) == schema_version:
        return group
    if group is None:
        group = bpy.data.node_groups.new(name, tree_type)
    else:
        _clear_node_tree(group)
    builder_fn(group)
    group[SCHEMA_PROP] = schema_version
    return group


# ---------------------------------------------------------------------------
# Non-destructive injection / ejection
# ---------------------------------------------------------------------------

def _socket_default_to_json(socket):
    dv = socket.default_value
    try:
        return list(dv)
    except TypeError:
        return dv


def _apply_json_default(socket, value):
    if not hasattr(socket, "default_value"):
        return
    if hasattr(socket.default_value, "__len__") and isinstance(value, list):
        for i, v in enumerate(value):
            socket.default_value[i] = v
    else:
        socket.default_value = value


def inject_between(tree, target_node, target_socket_name, group_node,
                    group_input_name, group_output_name, addon_id):
    """Splice `group_node` into `tree` on one input socket of `target_node`.

    Whatever currently feeds `target_node.inputs[target_socket_name]`
    (a link, or just a literal default) is rerouted to feed
    `group_node.inputs[group_input_name]` instead, and
    `group_node.outputs[group_output_name]` is wired to the target socket.

    Safe to call repeatedly on the *same* `group_node` for different
    sockets (e.g. Base Color, then Roughness, then Normal, all through one
    shared group instance) — each call appends its own restore record so
    `eject()` can undo them independently and in any order.
    """
    target_socket = target_node.inputs[target_socket_name]
    group_in = group_node.inputs[group_input_name]
    group_out = group_node.outputs[group_output_name]

    record = {
        "target_node": target_node.name,
        "target_socket": target_socket_name,
        "group_input": group_input_name,
        "group_output": group_output_name,
    }

    existing_link = None
    for link in tree.links:
        if link.to_socket == target_socket:
            existing_link = link
            break

    if existing_link is not None:
        record["had_link"] = True
        record["from_node"] = existing_link.from_node.name
        record["from_socket"] = existing_link.from_socket.name
        tree.links.new(existing_link.from_socket, group_in)
        tree.links.remove(existing_link)
    else:
        record["had_link"] = False
        record["default_value"] = _socket_default_to_json(target_socket)
        _apply_json_default(group_in, record["default_value"])

    tree.links.new(group_out, target_socket)

    records = json.loads(group_node.get(RECORD_PROP, "[]"))
    records.append(record)
    group_node[RECORD_PROP] = json.dumps(records)
    group_node[ADDON_PROP] = addon_id
    return record


def add_scene_driver(datablock, data_path, scene_data_path, scene=None):
    """Add a single-variable driver on `datablock.data_path` that mirrors
    `scene.<scene_data_path>` verbatim (type AVERAGE with one variable —
    no expression evaluation needed for a passthrough).

    This is how master sliders (e.g. StormKit's global Wetness) propagate
    to every injected instance across the whole scene: Blender's
    depsgraph re-evaluates the driver only when the source property
    actually changes, so this satisfies ground rule #8 (no per-frame
    Python) without any handler at all.
    """
    import bpy

    scene = scene or bpy.context.scene
    fcurve = datablock.driver_add(data_path)
    driver = fcurve.driver
    driver.type = "AVERAGE"
    var = driver.variables.new()
    var.name = "v"
    var.type = "SINGLE_PROP"
    var.targets[0].id_type = "SCENE"
    var.targets[0].id = scene
    var.targets[0].data_path = scene_data_path
    return fcurve


def eject(tree, addon_id):
    """Reverse every `inject_between()` call tagged `addon_id` (exact match,
    or a "prefix:" match against "prefix:feature"-style ids) inside `tree`.

    Restores each affected target socket to its original link or literal
    default, then removes the tagged group node(s). Returns how many group
    nodes were removed.
    """

    def _matches(tag):
        return tag == addon_id or (tag is not None and tag.startswith(addon_id + ":"))

    removed = 0
    for node in list(tree.nodes):
        tag = node.get(ADDON_PROP)
        if not _matches(tag):
            continue
        records = json.loads(node.get(RECORD_PROP, "[]"))
        for record in records:
            target_node = tree.nodes.get(record["target_node"])
            if target_node is None:
                continue
            target_socket = target_node.inputs.get(record["target_socket"])
            if target_socket is None:
                continue
            for link in list(tree.links):
                if link.to_socket == target_socket:
                    tree.links.remove(link)
            if record["had_link"]:
                from_node = tree.nodes.get(record["from_node"])
                from_socket = (
                    from_node.outputs.get(record["from_socket"]) if from_node else None
                )
                if from_socket is not None:
                    tree.links.new(from_socket, target_socket)
            else:
                _apply_json_default(target_socket, record["default_value"])
        tree.nodes.remove(node)
        removed += 1
    return removed
