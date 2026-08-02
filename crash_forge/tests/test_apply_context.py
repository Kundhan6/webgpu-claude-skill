"""Tier B (§13) — stubbed bpy.

Locks in the fix for a crash confirmed on a real car (Blender 5.1.2, M4
verification pass): bl/apply.py's operator wrappers relied on
context.temp_override(...) alone to make `obj` the operator's target,
but shade_auto_smooth.poll() (and, by the identical pattern, origin_set)
checks the *real* active object underneath — the override doesn't change
that. Whenever the real active object was a non-mesh (the car's root
Empty — exactly what's selected after a normal "set car_object, click
Prep" run), the operator raised RuntimeError: "poll() failed, context is
incorrect" as an unhandled exception straight out of CF_Prep.execute().

Tier B's bpy stub implements no real operators at all, by design (see
tests/stubs/bpy.py) — these tests can't reproduce the real operator's
poll() logic. What they do lock in is the two things the fix depends on:
  1. the real view_layer selection/active object is actually mutated to
     `obj` before the operator call, not just passed through an override
  2. a RuntimeError from the operator degrades to a returned False,
     never an unhandled exception — and the prior selection is restored
     either way, success or failure
"""
import contextlib


class FakeObj:
    def __init__(self, name):
        self.name = name
        self._selected = False

    def select_get(self):
        return self._selected

    def select_set(self, state):
        self._selected = state


class FakeLayerObjects(list):
    """Mirrors bpy's ViewLayer.objects: an iterable collection that also
    carries `.active` — matches real bpy's shape exactly (`.active`
    lives on the objects collection, not the view layer itself), which
    is what tripped up the first draft of these tests."""

    def __init__(self, objects):
        super().__init__(objects)
        self.active = None


class FakeViewLayer:
    def __init__(self, objects):
        self.objects = FakeLayerObjects(objects)


class FakeContext:
    def __init__(self, view_layer):
        self.view_layer = view_layer

    @contextlib.contextmanager
    def temp_override(self, **kwargs):
        yield


def _install_fake_operator(bpy, name, func):
    """Attach a fake bpy.ops.object.<name> under the stub, which starts
    with an empty bpy.ops (tests/stubs/bpy.py: "no operator exists under
    this stub")."""
    bpy.ops.object = type("_FakeObjectOps", (), {name: staticmethod(func)})()


def test_apply_shade_auto_smooth_sets_the_real_active_object_not_just_the_override(stubbed_bpy):
    """The exact bug: the override alone (active_object=obj) is not
    enough — the fake operator below only succeeds if the *real*
    view_layer active object is the target, proving the fix mutates
    real state rather than trusting the override."""
    import bpy

    from crash_forge.bl import apply as bl_apply

    car_root = FakeObj("CarRoot")  # a non-mesh, the real active object — the crash's precondition
    car_root.select_set(True)
    target = FakeObj("Hood")
    other = FakeObj("Door_L")
    vl = FakeViewLayer([car_root, target, other])
    vl.objects.active = car_root
    ctx = FakeContext(vl)

    calls = []

    def fake_shade_auto_smooth():
        calls.append(vl.objects.active.name)
        if vl.objects.active is not target:
            raise RuntimeError("Operator bpy.ops.object.shade_auto_smooth.poll() failed, context is incorrect")
        return {'FINISHED'}

    _install_fake_operator(bpy, "shade_auto_smooth", fake_shade_auto_smooth)

    ok = bl_apply.apply_shade_auto_smooth(ctx, target)

    assert ok is True
    assert calls == ["Hood"]
    assert target.select_get() is False  # selection restored afterward, not left mutated


def test_apply_shade_auto_smooth_catches_runtime_error_instead_of_raising(stubbed_bpy):
    import bpy

    from crash_forge.bl import apply as bl_apply

    car_root = FakeObj("CarRoot")
    target = FakeObj("Hood")
    vl = FakeViewLayer([car_root, target])
    vl.objects.active = car_root
    ctx = FakeContext(vl)

    def always_fails():
        raise RuntimeError("Operator bpy.ops.object.shade_auto_smooth.poll() failed, context is incorrect")

    _install_fake_operator(bpy, "shade_auto_smooth", always_fails)

    ok = bl_apply.apply_shade_auto_smooth(ctx, target)

    assert ok is False  # never an unhandled exception


def test_apply_shade_auto_smooth_restores_prior_selection_even_on_failure(stubbed_bpy):
    import bpy

    from crash_forge.bl import apply as bl_apply

    car_root = FakeObj("CarRoot")
    car_root.select_set(True)
    target = FakeObj("Hood")
    other = FakeObj("Door_L")
    other.select_set(True)
    vl = FakeViewLayer([car_root, target, other])
    vl.objects.active = car_root
    ctx = FakeContext(vl)

    _install_fake_operator(bpy, "shade_auto_smooth", lambda: (_ for _ in ()).throw(RuntimeError("boom")))

    bl_apply.apply_shade_auto_smooth(ctx, target)

    assert vl.objects.active is car_root
    assert car_root.select_get() is True
    assert other.select_get() is True
    assert target.select_get() is False


def test_set_origin_to_center_of_mass_sets_the_real_active_object(stubbed_bpy):
    """Same fix, same reasoning, applied to the other operator wrapper
    that shared the identical temp_override-only pattern."""
    import bpy

    from crash_forge.bl import apply as bl_apply

    car_root = FakeObj("CarRoot")
    target = FakeObj("Hood")
    vl = FakeViewLayer([car_root, target])
    vl.objects.active = car_root
    ctx = FakeContext(vl)

    calls = []

    def fake_origin_set(type):
        calls.append(vl.objects.active.name)
        if vl.objects.active is not target:
            raise RuntimeError("Operator bpy.ops.object.origin_set.poll() failed, context is incorrect")
        return {'FINISHED'}

    _install_fake_operator(bpy, "origin_set", fake_origin_set)

    ok = bl_apply.set_origin_to_center_of_mass(ctx, target)

    assert ok is True
    assert calls == ["Hood"]


def test_set_origin_to_center_of_mass_catches_runtime_error_instead_of_raising(stubbed_bpy):
    import bpy

    from crash_forge.bl import apply as bl_apply

    car_root = FakeObj("CarRoot")
    target = FakeObj("Hood")
    vl = FakeViewLayer([car_root, target])
    vl.objects.active = car_root
    ctx = FakeContext(vl)

    _install_fake_operator(bpy, "origin_set", lambda type: (_ for _ in ()).throw(RuntimeError("boom")))

    ok = bl_apply.set_origin_to_center_of_mass(ctx, target)

    assert ok is False
