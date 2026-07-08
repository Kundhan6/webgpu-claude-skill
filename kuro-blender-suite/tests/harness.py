"""Minimal headless test runner (Blender's Python has no pytest).

Entry point is tests/run_all.py:
    blender --background --factory-startup --python tests/run_all.py
"""

import importlib.util
import os
import sys
import traceback

import bpy


class TestFailure(Exception):
    pass


# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------

def assert_true(condition, message="assertion failed"):
    if not condition:
        raise TestFailure(message)


def assert_equal(a, b, message=None):
    if a != b:
        raise TestFailure(message or f"{a!r} != {b!r}")


def assert_almost_equal(a, b, tol=1e-4, message=None):
    if abs(a - b) > tol:
        raise TestFailure(message or f"{a!r} !~= {b!r} (tol={tol})")


def assert_raises(exc_type, fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except exc_type:
        return
    except Exception as e:
        raise TestFailure(f"expected {exc_type.__name__}, got {type(e).__name__}: {e}")
    raise TestFailure(f"expected {exc_type.__name__} to be raised, nothing was")


# ---------------------------------------------------------------------------
# Isolation + discovery + running
# ---------------------------------------------------------------------------

def reset_blender():
    """Fresh, empty scene before every test — no test may depend on state
    left behind by another (per §2.4)."""
    bpy.ops.wm.read_factory_settings(use_empty=True)


def discover_tests(module):
    """Return [(name, callable), ...] for every top-level `test_*` function
    in `module`."""
    tests = []
    for name in dir(module):
        if name.startswith("test_"):
            fn = getattr(module, name)
            if callable(fn):
                tests.append((name, fn))
    return tests


def run_module(module, results):
    """Run every test_* function in `module`, isolating each with
    reset_blender(). Appends (module_name, test_name, ok, message) to
    `results`. Never raises — one failing test must not abort the suite."""
    mod_name = getattr(module, "__name__", str(module))
    for name, fn in discover_tests(module):
        reset_blender()
        try:
            fn()
            results.append((mod_name, name, True, ""))
            print(f"  PASS  {mod_name}.{name}")
        except Exception as e:
            tb = traceback.format_exc()
            results.append((mod_name, name, False, tb))
            print(f"  FAIL  {mod_name}.{name}: {e}")


def import_test_module(path, package_root):
    """Import a tests/**/test_*.py file as a module by file path, so the
    tests/ tree doesn't need to be pip-installed anywhere."""
    rel = os.path.relpath(path, package_root)
    mod_name = "kuro_tests." + rel[:-3].replace(os.sep, ".")
    spec = importlib.util.spec_from_file_location(mod_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


def print_summary(results):
    total = len(results)
    failed = [r for r in results if not r[2]]
    print("\n" + "=" * 60)
    print(f"KURO test suite: {total - len(failed)}/{total} passed")
    if failed:
        print(f"\n{len(failed)} FAILURE(S):")
        for mod_name, name, _ok, tb in failed:
            print(f"\n--- {mod_name}.{name} ---")
            print(tb)
    print("=" * 60)
    return len(failed) == 0


# ---------------------------------------------------------------------------
# Scene helpers
# ---------------------------------------------------------------------------

def build_preview_scene(material=None):
    """Build a minimal headless preview scene: a UV sphere (with
    `material` assigned if given), a sun lamp, and a camera framing it.
    Returns the mesh object."""
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, location=(0, 0, 0))
    obj = bpy.context.active_object
    if material is not None:
        obj.data.materials.append(material)

    bpy.ops.object.light_add(type="SUN", location=(2, -2, 3))
    bpy.context.active_object.data.energy = 3.0

    bpy.ops.object.camera_add(location=(0, -4, 0), rotation=(1.5708, 0, 0))
    camera = bpy.context.active_object
    bpy.context.scene.camera = camera

    return obj


# ---------------------------------------------------------------------------
# Render-stat verification — this is how the harness "sees" (§2.4)
# ---------------------------------------------------------------------------

def render_stats(scene=None, resolution=128, samples=16, output_path=None):
    """Render `scene` (default: current) at `resolution`x`resolution` on
    Cycles CPU at `samples` samples, then return per-channel pixel stats:
    {mean, std, min, max, channel_means}.

    Used for assertions like "render is not black", "wet material is
    darker than dry", "snow scene has higher luminance". Golden baselines
    are stored as JSON stats (tests/golden/), not pixel-perfect images —
    those are too fragile across Blender versions/GPU vs CPU.
    """
    import numpy as np

    scene = scene or bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    scene.cycles.device = "CPU"
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "OPEN_EXR"
    scene.render.image_settings.color_depth = "32"

    output_path = output_path or "/tmp/kuro_test_render.exr"
    scene.render.filepath = output_path

    bpy.ops.render.render(write_still=True)

    img = bpy.data.images.load(output_path, check_existing=False)
    try:
        w, h = img.size
        pixels = list(img.pixels[:])
        arr = np.array(pixels, dtype=np.float32).reshape(h, w, img.channels)
    finally:
        bpy.data.images.remove(img)

    rgb = arr[:, :, :3]
    return {
        "mean": float(rgb.mean()),
        "std": float(rgb.std()),
        "min": float(rgb.min()),
        "max": float(rgb.max()),
        "channel_means": [float(rgb[:, :, c].mean()) for c in range(3)],
    }
