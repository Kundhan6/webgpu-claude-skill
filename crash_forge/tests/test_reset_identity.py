"""Tier B (§13) — stubbed bpy. Locks in that every path which finds
Crash Forge's own generated objects uses identity (obj["cf_generated"] /
obj["cf_uid"]), never a parsed or prefix-matched name.

This matters specifically for CF_Reset's self-check (§8.0, V20: "Nothing
tagged cf_generated survives a Reset"). A generated object can end up
with a name that doesn't start with "CF_" — the user renamed it, some
other tool touched it, or any other reason a bare `name.startswith("CF_")`
guess doesn't hold — and it must still be caught. Before this fix,
bl/scene.py::reset_self_check() checked rigidbody_world membership by
name prefix; an object like this would pass that check as "clean" while
still being a leaked orphan, exactly the failure V20 exists to prevent.
"""


class FakeObj:
    def __init__(self, name, **props):
        self.name = name
        self._props = props

    def get(self, key, default=None):
        return self._props.get(key, default)


class FakeCollection:
    def __init__(self, objects):
        self.objects = objects


class FakeRigidBodyWorld:
    def __init__(self, collection, constraints):
        self.collection = collection
        self.constraints = constraints


class FakeScene:
    def __init__(self, rigidbody_world):
        self.rigidbody_world = rigidbody_world


def test_reset_self_check_catches_a_generated_object_with_an_unparseable_name(stubbed_bpy):
    """A cf_generated object renamed to something that doesn't start with
    "CF_" at all (the extreme case of an "unparseable" name) must still be
    reported as a surviving orphan — identity comes from the cf_generated
    property, not from matching the name."""
    import bpy

    from crash_forge.bl import scene as bl_scene

    renamed_orphan = FakeObj("Totally_Renamed_By_Someone", cf_generated=True)
    bpy.data.objects = []  # nothing leaked in the general bpy.data.objects scan

    rbw = FakeRigidBodyWorld(
        collection=FakeCollection([renamed_orphan]),
        constraints=FakeCollection([]),
    )
    scene = FakeScene(rigidbody_world=rbw)

    problems = bl_scene.reset_self_check(scene)

    assert problems, (
        "a cf_generated object left in rigidbody_world.collection must be "
        "reported even when its name doesn't start with CF_ — V20 depends "
        "on identity, not on a parseable name"
    )
    assert any("Totally_Renamed_By_Someone" in p for p in problems)


def test_reset_self_check_ignores_a_non_generated_object_named_like_cf(stubbed_bpy):
    """The inverse case: an object that merely *looks* generated (starts
    with "CF_") but was never tagged cf_generated must NOT be reported —
    a name-based check would false-positive here and block Reset on
    something it never created."""
    import bpy

    from crash_forge.bl import scene as bl_scene

    lookalike = FakeObj("CF_NotActuallyOurs")  # no cf_generated prop at all
    bpy.data.objects = []

    rbw = FakeRigidBodyWorld(
        collection=FakeCollection([lookalike]),
        constraints=FakeCollection([]),
    )
    scene = FakeScene(rigidbody_world=rbw)

    problems = bl_scene.reset_self_check(scene)

    assert problems == []


def test_reset_self_check_clean_scene_reports_no_problems(stubbed_bpy):
    import bpy

    from crash_forge.bl import scene as bl_scene

    bpy.data.objects = []
    rbw = FakeRigidBodyWorld(collection=FakeCollection([]), constraints=FakeCollection([]))
    scene = FakeScene(rigidbody_world=rbw)

    assert bl_scene.reset_self_check(scene) == []


def test_reset_self_check_handles_no_rigidbody_world(stubbed_bpy):
    """scene.rigidbody_world can legitimately be None (never created).
    Self-check must not crash — only the general bpy.data.objects scan
    applies."""
    import bpy

    from crash_forge.bl import scene as bl_scene

    bpy.data.objects = [FakeObj("Leftover", cf_generated=True)]
    scene = FakeScene(rigidbody_world=None)

    problems = bl_scene.reset_self_check(scene)

    assert any("Leftover" in p for p in problems)
