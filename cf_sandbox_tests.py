#!/usr/bin/env python3
"""
Crash Forge - Sandbox Test Suite (NO BLENDER REQUIRED)
======================================================

Runs anywhere plain Python 3 runs. Stubs out bpy/mathutils/bmesh, imports the
add-on for real, exercises register()/unregister(), audits the source for the
specific failure patterns that break Blender add-ons, and unit-tests any pure
logic that has been factored out of the operators.

    python cf_sandbox_tests.py /path/to/crash_forge

Writes cf_sandbox_report.json next to itself. Exit 0 = clean, 1 = FAILs present.

WHAT THIS CANNOT TEST: anything involving the actual physics solvers - momentum
inheritance, tunneling, cloth-vs-rigidbody collision, Cell Fracture. Those need
a real Blender and are covered by crashforge_selftest.py, run separately.
"""

import ast
import importlib
import json
import os
import re
import sys
import types
import traceback

RESULTS = []


def rec(tid, name, group, status, detail="", data=None):
    RESULTS.append({"id": tid, "name": name, "group": group,
                     "status": status, "detail": detail, "data": data or {}})
    mark = {"PASS": " ok ", "FAIL": "FAIL", "WARN": "warn", "SKIP": "skip"}[status]
    print(f"  [{mark}] {tid:5} {name}")
    if detail and status in ("FAIL", "WARN"):
        for line in detail.splitlines():
            print(f"           {line}")


# ==========================================================================
# 1. THE BPY STUB
# ==========================================================================

class Vec:
    """Minimal mathutils.Vector - real arithmetic so integrators can be tested."""
    def __init__(self, v=(0.0, 0.0, 0.0)):
        self.v = [float(x) for x in v]

    def __getitem__(self, i): return self.v[i]
    def __setitem__(self, i, val): self.v[i] = float(val)
    def __len__(self): return len(self.v)
    def __iter__(self): return iter(self.v)
    def __repr__(self): return f"Vec({self.v})"
    def __add__(self, o): return Vec([a + b for a, b in zip(self.v, o.v)])
    def __sub__(self, o): return Vec([a - b for a, b in zip(self.v, o.v)])
    def __mul__(self, s): return Vec([a * s for a in self.v])
    __rmul__ = __mul__
    def copy(self): return Vec(self.v)

    @property
    def length(self): return sum(a * a for a in self.v) ** 0.5

    @property
    def x(self): return self.v[0]
    @x.setter
    def x(self, val): self.v[0] = float(val)
    @property
    def y(self): return self.v[1]
    @y.setter
    def y(self, val): self.v[1] = float(val)
    @property
    def z(self): return self.v[2]
    @z.setter
    def z(self, val): self.v[2] = float(val)

    def normalized(self):
        l = self.length
        return Vec([a / l for a in self.v]) if l else Vec()

    def dot(self, o): return sum(a * b for a, b in zip(self.v, o.v))


class PropDef:
    """Stand-in for a bpy.props.*Property() call. Records its own config."""
    def __init__(self, kind, kwargs):
        self.kind = kind
        self.kwargs = kwargs

    def default_value(self):
        if "default" in self.kwargs:
            return self.kwargs["default"]
        if self.kind == "EnumProperty":
            items = self.kwargs.get("items") or []
            return items[0][0] if items else ""
        return {"BoolProperty": False, "IntProperty": 0, "FloatProperty": 0.0,
                "StringProperty": "", "FloatVectorProperty": Vec(),
                "PointerProperty": None, "CollectionProperty": []}.get(self.kind)

    def __repr__(self): return f"<{self.kind}>"


class Struct:
    """Base for every stubbed bpy type. Property annotations become real attrs."""
    def __init__(self, **kw):
        for cls in reversed(type(self).__mro__):
            for key, val in getattr(cls, "__annotations__", {}).items():
                if isinstance(val, PropDef):
                    setattr(self, key, val.default_value())
        for k, v in kw.items():
            setattr(self, k, v)

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        obj = Struct()
        object.__setattr__(self, name, obj)
        return obj


REGISTRY = []
OPS_CALLS = []


class OpsNS:
    def __init__(self, path=""):
        self._path = path

    def __getattr__(self, name):
        return OpsNS(f"{self._path}.{name}" if self._path else name)

    def __call__(self, *a, **kw):
        OPS_CALLS.append((self._path, kw))
        return {"FINISHED"}

    def poll(self, *a, **kw):
        return True


def build_bpy():
    bpy = types.ModuleType("bpy")

    # --- bpy.types: unknown types materialise on demand
    class TypesModule(types.ModuleType):
        def __getattr__(self, name):
            if name.startswith("__"):
                raise AttributeError(name)
            new = type(name, (Struct,), {})
            setattr(self, name, new)
            return new

    t = TypesModule("bpy.types")
    for base in ("Operator", "Panel", "PropertyGroup", "AddonPreferences",
                 "UIList", "Menu", "Header", "Object", "Scene", "Mesh",
                 "Material", "Collection", "ID", "Node"):
        setattr(t, base, type(base, (Struct,), {}))
    bpy.types = t

    # --- bpy.props
    props = types.ModuleType("bpy.props")
    for kind in ("BoolProperty", "IntProperty", "FloatProperty", "StringProperty",
                 "EnumProperty", "PointerProperty", "CollectionProperty",
                 "FloatVectorProperty", "IntVectorProperty", "BoolVectorProperty"):
        props.__dict__[kind] = (lambda k: (lambda **kw: PropDef(k, kw)))(kind)
    bpy.props = props

    # --- bpy.utils
    utils = types.ModuleType("bpy.utils")

    def register_class(cls):
        if cls in REGISTRY:
            raise RuntimeError(f"already registered: {cls.__name__}")
        REGISTRY.append(cls)

    def unregister_class(cls):
        if cls not in REGISTRY:
            raise RuntimeError(f"not registered: {cls.__name__}")
        REGISTRY.remove(cls)

    utils.register_class = register_class
    utils.unregister_class = unregister_class
    utils.previews = types.SimpleNamespace(new=lambda: {}, remove=lambda x: None)
    utils.user_resource = lambda *a, **k: "/tmp"
    bpy.utils = utils

    # --- misc
    bpy.ops = OpsNS()
    bpy.app = types.SimpleNamespace(version=(5, 1, 2), version_string="5.1.2",
                                     binary_path="", background=True,
                                     handlers=types.SimpleNamespace(
                                         depsgraph_update_post=[],
                                         frame_change_post=[], load_post=[]),
                                     timers=types.SimpleNamespace(
                                         register=lambda *a, **k: None))
    bpy.data = types.SimpleNamespace(filepath="", objects=[], collections=[],
                                      meshes=[], materials=[], scenes=[])
    bpy.path = types.SimpleNamespace(
        abspath=lambda p, **k: p.replace("//", "/tmp/unsaved/"))
    bpy.context = Struct(scene=Struct(), selected_objects=[], active_object=None,
                          view_layer=Struct(), preferences=Struct(addons={}),
                          mode="OBJECT", window_manager=Struct())

    # --- mathutils / bmesh / addon_utils
    mu = types.ModuleType("mathutils")
    mu.Vector = Vec
    mu.Matrix = type("Matrix", (Struct,), {"Identity": staticmethod(lambda n: Struct())})
    mu.Euler = type("Euler", (Struct,), {})
    mu.Quaternion = type("Quaternion", (Struct,), {})
    bvh = types.ModuleType("mathutils.bvhtree")
    bvh.BVHTree = type("BVHTree", (Struct,), {
        "FromObject": staticmethod(lambda *a, **k: Struct(overlap=lambda o: []))})
    mu.bvhtree = bvh
    geo = types.ModuleType("mathutils.geometry")
    mu.geometry = geo

    bm = types.ModuleType("bmesh")
    bm.new = lambda: Struct(verts=[], edges=[], faces=[])
    bm.from_edit_mesh = lambda m: Struct(verts=[], edges=[], faces=[])
    bm.update_edit_mesh = lambda m: None
    bm.ops = OpsNS()

    au = types.ModuleType("addon_utils")
    au.modules = lambda: []
    au.check = lambda n: (False, False)
    au.enable = lambda *a, **k: None

    bpy_extras = types.ModuleType("bpy_extras")
    bpy_extras.view3d_utils = types.ModuleType("bpy_extras.view3d_utils")
    bpy_extras.io_utils = types.ModuleType("bpy_extras.io_utils")
    bpy_extras.io_utils.ExportHelper = type("ExportHelper", (Struct,), {})
    bpy_extras.io_utils.ImportHelper = type("ImportHelper", (Struct,), {})

    gpu = types.ModuleType("gpu")
    gpu.shader = types.SimpleNamespace(from_builtin=lambda n: Struct())
    gpu_extras = types.ModuleType("gpu_extras")
    gpu_extras.batch = types.ModuleType("gpu_extras.batch")
    gpu_extras.batch.batch_for_shader = lambda *a, **k: Struct()

    blf = types.ModuleType("blf")
    blf.position = blf.size = blf.draw = blf.color = lambda *a, **k: None

    for mod in (bpy, props, utils, t, mu, bvh, geo, bm, au, bpy_extras,
                bpy_extras.view3d_utils, bpy_extras.io_utils, gpu,
                gpu_extras, gpu_extras.batch, blf):
        sys.modules[mod.__name__] = mod
    return bpy


# ==========================================================================
# 2. IMPORT / REGISTER TESTS
# ==========================================================================

def test_import_and_register(pkg_path):
    grp = "register"
    pkg_dir = os.path.dirname(os.path.abspath(pkg_path))
    pkg_name = os.path.basename(os.path.abspath(pkg_path.rstrip("/\\")))
    if pkg_dir not in sys.path:
        sys.path.insert(0, pkg_dir)

    try:
        mod = importlib.import_module(pkg_name)
    except Exception as e:
        rec("R1", "add-on imports with bpy stubbed", grp, "FAIL",
            f"{type(e).__name__}: {e}\n{traceback.format_exc()[-800:]}")
        return None
    rec("R1", "add-on imports with bpy stubbed", grp, "PASS")

    bl_info = getattr(mod, "bl_info", None)
    if not isinstance(bl_info, dict):
        rec("R2", "bl_info present and well-formed", grp, "FAIL", "no bl_info dict")
    else:
        missing = [k for k in ("name", "blender", "version", "category")
                   if k not in bl_info]
        rec("R2", "bl_info present and well-formed", grp,
            "FAIL" if missing else "PASS",
            f"missing keys: {missing}" if missing else "",
            {"bl_info": {k: str(v) for k, v in bl_info.items()}})

    has_reg = callable(getattr(mod, "register", None))
    has_unreg = callable(getattr(mod, "unregister", None))
    rec("R3", "register/unregister defined", grp,
        "PASS" if (has_reg and has_unreg) else "FAIL",
        f"register={has_reg} unregister={has_unreg}")
    if not (has_reg and has_unreg):
        return mod

    REGISTRY.clear()
    try:
        mod.register()
    except Exception as e:
        rec("R4", "register() runs clean", grp, "FAIL",
            f"{type(e).__name__}: {e}\n{traceback.format_exc()[-800:]}")
        return mod
    n_reg = len(REGISTRY)
    rec("R4", "register() runs clean", grp, "PASS", f"{n_reg} classes registered")

    import bpy
    scene_hook = hasattr(bpy.types.Scene, "crashforge")
    obj_hook = hasattr(bpy.types.Object, "crashforge")
    rec("R5", "Scene.crashforge + Object.crashforge attached", grp,
        "PASS" if (scene_hook and obj_hook) else "FAIL",
        f"Scene={scene_hook} Object={obj_hook}")

    try:
        mod.unregister()
    except Exception as e:
        rec("R6", "unregister() runs clean", grp, "FAIL",
            f"{type(e).__name__}: {e}\n{traceback.format_exc()[-800:]}")
        return mod

    leaked = [c.__name__ for c in REGISTRY]
    rec("R6", "unregister() runs clean", grp, "PASS")
    rec("R7", "no class leaks after unregister", grp,
        "PASS" if not leaked else "FAIL",
        f"still registered: {leaked}" if leaked else "", {"leaked": leaked})

    still = [n for n, ok in (("Scene", hasattr(bpy.types.Scene, "crashforge")),
                             ("Object", hasattr(bpy.types.Object, "crashforge"))) if ok]
    rec("R8", "property hooks removed on unregister", grp,
        "PASS" if not still else "FAIL",
        f"leaked hooks on: {still}" if still else "")

    # register -> unregister -> register again (F8 reload survival)
    try:
        mod.register()
        mod.unregister()
        rec("R9", "survives a reload cycle (reg/unreg/reg/unreg)", grp, "PASS")
    except Exception as e:
        rec("R9", "survives a reload cycle (reg/unreg/reg/unreg)", grp, "FAIL",
            f"second cycle failed: {type(e).__name__}: {e}")
    return mod


def test_class_contracts(mod):
    grp = "contracts"
    import bpy
    REGISTRY.clear()
    try:
        mod.register()
    except Exception:
        rec("C0", "class contract scan", grp, "SKIP", "register() failed above")
        return
    classes = list(REGISTRY)

    ops = [c for c in classes if issubclass(c, bpy.types.Operator)]
    panels = [c for c in classes if issubclass(c, bpy.types.Panel)]

    ids = [getattr(c, "bl_idname", None) for c in ops]
    dupes = {i for i in ids if i and ids.count(i) > 1}
    rec("C1", "operator bl_idnames unique", grp,
        "PASS" if not dupes else "FAIL",
        f"duplicates: {sorted(dupes)}" if dupes else f"{len(ops)} operators")

    bad = [f"{c.__name__}({getattr(c,'bl_idname','<none>')})" for c in ops
           if not re.fullmatch(r"[a-z0-9_]+\.[a-z0-9_]+", str(getattr(c, "bl_idname", "")))]
    rec("C2", "operator bl_idnames match lower.dot convention", grp,
        "PASS" if not bad else "FAIL",
        f"invalid: {bad}" if bad else "")

    noexec = [c.__name__ for c in ops
              if not (hasattr(c, "execute") or hasattr(c, "invoke")
                      or hasattr(c, "modal"))]
    rec("C3", "every operator has execute/invoke/modal", grp,
        "PASS" if not noexec else "FAIL", f"missing: {noexec}" if noexec else "")

    nolabel = [c.__name__ for c in ops if not getattr(c, "bl_label", "")]
    rec("C4", "every operator has bl_label", grp,
        "PASS" if not nolabel else "WARN", f"missing: {nolabel}" if nolabel else "")

    pbad = [c.__name__ for c in panels
            if not (getattr(c, "bl_space_type", None)
                    and getattr(c, "bl_region_type", None))]
    rec("C5", "panels declare space/region type", grp,
        "PASS" if not pbad else "FAIL", f"incomplete: {pbad}" if pbad else
        f"{len(panels)} panels")

    cats = {getattr(c, "bl_category", None) for c in panels} - {None}
    rec("C6", "all panels share one bl_category tab", grp,
        "PASS" if len(cats) <= 1 else "WARN",
        f"categories found: {sorted(cats)}", {"categories": sorted(cats)})

    # enum coverage: every EnumProperty identifier should appear somewhere else
    enums = {}
    for c in classes:
        for key, val in getattr(c, "__annotations__", {}).items():
            if isinstance(val, PropDef) and val.kind == "EnumProperty":
                enums[f"{c.__name__}.{key}"] = [i[0] for i in (val.kwargs.get("items") or [])]
    rec("C7", "enum properties expose items", grp,
        "PASS" if all(v for v in enums.values()) else "WARN",
        "; ".join(f"{k}={v}" for k, v in enums.items()) or "no enums found",
        {"enums": enums})

    try:
        mod.unregister()
    except Exception:
        pass
    return enums


# ==========================================================================
# 3. SOURCE AUDIT - the vulnerability greps
# ==========================================================================

AUDIT = []


def audit(tid, name, severity):
    def wrap(fn):
        AUDIT.append((tid, name, severity, fn))
        return fn
    return wrap


def src_files(root):
    out = {}
    for dirpath, _, files in os.walk(root):
        for f in files:
            if f.endswith(".py"):
                p = os.path.join(dirpath, f)
                rel = os.path.relpath(p, root)
                try:
                    out[rel] = open(p, encoding="utf-8").read()
                except Exception:
                    pass
    return out


@audit("A1", "no direct action.fcurves outside fcurve_compat", "FAIL")
def a1(files):
    hits = [f for f, s in files.items()
            if "fcurve_compat" not in f and re.search(r"\.action\.fcurves|action\.fcurves", s)]
    return (not hits,
            f"direct legacy fcurve access in: {hits} - route through utils/fcurve_compat.py"
            if hits else "")


@audit("A2", "no bpy.ops calls inside draw()", "FAIL")
def a2(files):
    hits = []
    for f, s in files.items():
        try:
            tree = ast.parse(s)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "draw":
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Call):
                        src = ast.unparse(sub.func) if hasattr(ast, "unparse") else ""
                        if src.startswith("bpy.ops"):
                            hits.append(f"{f}:{sub.lineno}")
    return (not hits, f"bpy.ops in draw(): {hits}" if hits else "")


@audit("A3", "draw() does not scan all objects", "WARN")
def a3(files):
    hits = []
    for f, s in files.items():
        try:
            tree = ast.parse(s)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "draw":
                body = ast.unparse(node) if hasattr(ast, "unparse") else ""
                if re.search(r"for .* in (bpy\.data\.objects|context\.scene\.objects"
                             r"|scene\.objects|bpy\.context\.scene\.objects)", body):
                    hits.append(f"{f}:{node.lineno}")
    return (not hits,
            f"full-scene iteration inside draw() at {hits} - cache the six status dots "
            f"in scene props and invalidate from a depsgraph handler" if hits else "")


@audit("A4", "breaking_threshold always paired with use_breaking", "FAIL")
def a4(files):
    hits = [f for f, s in files.items()
            if "breaking_threshold" in s and "use_breaking" not in s]
    return (not hits,
            f"{hits} sets breaking_threshold but never use_breaking=True - "
            f"constraints will never break" if hits else "")


@audit("A5", "collision_margin always paired with use_margin", "FAIL")
def a5(files):
    hits = [f for f, s in files.items()
            if "collision_margin" in s and "use_margin" not in s]
    return (not hits,
            f"{hits} sets collision_margin without use_margin=True - "
            f"the margin is ignored, tunneling defence is a no-op" if hits else "")


@audit("A6", "kinematic keyframes forced to CONSTANT interpolation", "FAIL")
def a6(files):
    rel = {f: s for f, s in files.items() if "rigid_body.kinematic" in s}
    hits = [f for f, s in rel.items() if "CONSTANT" not in s]
    return (not hits,
            f"{hits} keyframes rigid_body.kinematic without setting CONSTANT "
            f"interpolation - a bool interpolated linearly flips at the wrong frame"
            if hits else ("" if rel else "no kinematic keyframing found yet"))


@audit("A7", "impact detection uses sub-frame sampling", "WARN")
def a7(files):
    rel = {f: s for f, s in files.items() if "overlap(" in s or "BVHTree" in s}
    hits = [f for f, s in rel.items() if "subframe" not in s]
    return (not hits,
            f"{hits} does per-frame BVH overlap with no subframe stepping - at 30 m/s "
            f"the car moves 1.25 m/frame, so impact_frame lands late and "
            f"impact_location ends up inside the wall" if hits else "")


@audit("A8", "CLOTH colliders get a COLLISION modifier", "FAIL")
def a8(files):
    rel = {f: s for f, s in files.items() if "'CLOTH'" in s or '"CLOTH"' in s}
    joined = "\n".join(files.values())
    ok = ("COLLISION" in joined)
    return (ok or not rel,
            "cloth crumple is set up but no COLLISION modifier is ever added - "
            "a PASSIVE rigid body does not stop cloth; the hood will pass through "
            "the divider" if rel and not ok else "")


@audit("A9", "relative cache path guarded by a saved-file check", "WARN")
def a9(files):
    rel = {f: s for f, s in files.items() if re.search(r"['\"]//", s)}
    hits = [f for f, s in rel.items() if "filepath" not in s]
    return (not hits,
            f"{hits} uses '//' relative paths without checking bpy.data.filepath - "
            f"on an unsaved file this silently writes to temp and the version "
            f"increment never sees existing caches" if hits else "")


@audit("A10", "to_mesh() paired with to_mesh_clear()", "WARN")
def a10(files):
    hits = [f for f, s in files.items()
            if "to_mesh()" in s and "to_mesh_clear" not in s]
    return (not hits, f"{hits} leaks evaluated meshes - will balloon RAM across "
            f"a 250-frame crush scan" if hits else "")


@audit("A11", "heavy operators drop 'UNDO' from bl_options", "WARN")
def a11(files):
    hits = []
    for f, s in files.items():
        if not any(k in f for k in ("rig", "bake", "prep")):
            continue
        for m in re.finditer(r"bl_options\s*=\s*\{([^}]*)\}", s):
            if "UNDO" in m.group(1):
                hits.append(f)
    return (not hits,
            f"{sorted(set(hits))} keeps 'UNDO' on heavy operators - every fracture "
            f"object pushes a full scene snapshot onto the undo stack" if hits else "")


@audit("A12", "no bpy.ops inside loops", "WARN")
def a12(files):
    hits = []
    for f, s in files.items():
        try:
            tree = ast.parse(s)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.For, ast.While)):
                body = ast.unparse(node) if hasattr(ast, "unparse") else ""
                if "bpy.ops." in body:
                    hits.append(f"{f}:{node.lineno}")
    return (not hits, f"bpy.ops inside loops at {hits} - prefer bpy.data API" if hits else "")


@audit("A13", "no bare/silent exception handlers", "WARN")
def a13(files):
    hits = []
    for f, s in files.items():
        try:
            tree = ast.parse(s)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                silent = all(isinstance(b, ast.Pass) for b in node.body)
                if node.type is None or silent:
                    hits.append(f"{f}:{node.lineno}")
    return (not hits, f"swallowed exceptions at {hits}" if hits else "")


@audit("A14", "modal drive operator keys on integer frames", "WARN")
def a14(files):
    rel = {f: s for f, s in files.items() if "modal" in s and "TIMER" in s}
    hits = [f for f, s in rel.items()
            if "keyframe_insert" in s and "frame_current" not in s and "int(" not in s]
    return (not hits,
            f"{hits} inserts keyframes from a TIMER tick without pinning to an "
            f"integer frame - recorded speed becomes machine-load dependent"
            if hits else "")


@audit("A15", "mass not derived from volume alone for thin parts", "WARN")
def a15(files):
    rel = {f: s for f, s in files.items() if "mass_calculate" in s}
    hits = [f for f, s in rel.items()
            if not re.search(r"area|thickness|calc_area", s)]
    return (not hits,
            f"{hits} relies on volume-based mass_calculate - open car panels have no "
            f"enclosed volume and get near-zero mass" if hits else "")


def test_source_audit(root):
    files = src_files(root)
    if not files:
        rec("A0", "source audit", "audit", "SKIP", f"no .py files under {root}")
        return
    rec("A0", "source files found", "audit", "PASS",
        f"{len(files)} modules", {"files": sorted(files)})
    for tid, name, sev, fn in AUDIT:
        try:
            ok, detail = fn(files)
            rec(tid, name, "audit", "PASS" if ok else sev, detail)
        except Exception as e:
            rec(tid, name, "audit", "WARN", f"audit crashed: {e}")


# ==========================================================================
# 4. PURE-LOGIC UNIT TESTS
# ==========================================================================

def test_pure_logic(pkg_name):
    """
    These only run if the maths has been factored out of the operators into
    bpy-free functions. If they SKIP, that is itself the finding: move the
    logic into crash_forge/core/ so it can be tested at all.
    """
    grp = "logic"
    try:
        core = importlib.import_module(f"{pkg_name}.core")
    except Exception:
        rec("L0", "pure-logic core module", grp, "SKIP",
            "no crash_forge/core/ - all maths currently lives inside operators and "
            "cannot be tested without Blender. Extracting the bicycle integrator, "
            "cache versioning, density table and mass estimator into bpy-free "
            "functions is the single change that makes this suite meaningful.")
        return

    rec("L0", "pure-logic core module", grp, "PASS", "core importable without bpy")

    # bicycle integrator: determinism + speed clamp + zero-input drift
    fn = getattr(core, "step_bicycle", None)
    if fn:
        s1 = fn(state={"x": 0, "y": 0, "yaw": 0, "speed": 0}, throttle=1.0,
                 steer=0.0, dt=1 / 24)
        s2 = fn(state={"x": 0, "y": 0, "yaw": 0, "speed": 0}, throttle=1.0,
                 steer=0.0, dt=1 / 24)
        rec("L1", "bicycle integrator is deterministic", grp,
            "PASS" if s1 == s2 else "FAIL", f"{s1} vs {s2}")

        idle = fn(state={"x": 0, "y": 0, "yaw": 0, "speed": 0}, throttle=0.0,
                  steer=1.0, dt=1 / 24)
        drift = abs(idle.get("x", 0)) + abs(idle.get("y", 0))
        rec("L2", "no yaw-induced drift at zero speed", grp,
            "PASS" if drift < 1e-9 else "FAIL",
            f"moved {drift:.6f} m while stationary - steering must scale by speed")
    else:
        rec("L1", "bicycle integrator", grp, "SKIP", "core.step_bicycle not found")

    # cache versioning
    fn = getattr(core, "next_cache_version", None)
    if fn:
        existing = ["shot_v001", "shot_v002", "shot_v004"]
        nxt = fn("shot", existing)
        ok = str(nxt).endswith("005") or nxt == 5
        rec("L3", "cache version never reuses an existing number", grp,
            "PASS" if ok else "FAIL", f"got {nxt} from {existing}, expected 5/005")
    else:
        rec("L3", "cache versioning", grp, "SKIP", "core.next_cache_version not found")

    # density table completeness against the enum
    tbl = getattr(core, "DENSITY", None)
    if isinstance(tbl, dict):
        need = {"STEEL", "GLASS", "RUBBER", "PLASTIC", "TRIM_CHROME",
                "CONCRETE", "INTERIOR_FABRIC"}
        missing = need - set(tbl)
        rec("L4", "density table covers every material_class", grp,
            "PASS" if not missing else "FAIL", f"missing: {sorted(missing)}")
    else:
        rec("L4", "density table", grp, "SKIP", "core.DENSITY not found")

    # slowmo / crumple mapping completeness
    for attr, need, tid in (("SLOWMO", {"NORMAL", "MODERATE", "HEAVY"}, "L5"),
                             ("CRUMPLE", {"SUBTLE", "MODERATE", "HEAVY"}, "L6")):
        tbl = getattr(core, attr, None)
        if isinstance(tbl, dict):
            missing = need - set(tbl)
            rec(tid, f"{attr} mapping covers every enum value", grp,
                "PASS" if not missing else "FAIL", f"missing: {sorted(missing)}")
        else:
            rec(tid, f"{attr} mapping", grp, "SKIP", f"core.{attr} not found")

    # mass estimator sanity for a thin panel
    fn = getattr(core, "estimate_mass", None)
    if fn:
        m = fn(area_m2=1.5, thickness_m=0.0008, density=7850)
        ok = 5.0 < m < 15.0
        rec("L7", "sheet-metal mass estimate lands in a sane range", grp,
            "PASS" if ok else "FAIL",
            f"1.5 m2 x 0.8 mm steel -> {m:.2f} kg (expect ~9.4 kg)")
    else:
        rec("L7", "mass estimator", grp, "SKIP", "core.estimate_mass not found")


# ==========================================================================
# Runner
# ==========================================================================

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    root = os.path.abspath(sys.argv[1].rstrip("/\\"))
    pkg_name = os.path.basename(root)

    print("=" * 68)
    print(f"Crash Forge sandbox tests - {root}")
    print("=" * 68)

    build_bpy()

    print("\n[source audit]")
    test_source_audit(root)

    print("\n[import & register]")
    mod = test_import_and_register(root)

    if mod:
        print("\n[class contracts]")
        test_class_contracts(mod)

    print("\n[pure logic]")
    test_pure_logic(pkg_name)

    fails = [r for r in RESULTS if r["status"] == "FAIL"]
    warns = [r for r in RESULTS if r["status"] == "WARN"]
    skips = [r for r in RESULTS if r["status"] == "SKIP"]

    print("\n" + "=" * 68)
    print(f"{len(RESULTS) - len(fails) - len(warns) - len(skips)} passed | "
          f"{len(fails)} FAIL | {len(warns)} warn | {len(skips)} skip")

    if fails:
        print("\nBlockers:")
        for r in fails:
            print(f"  {r['id']}  {r['name']}")
            if r["detail"]:
                print(f"          {r['detail'].splitlines()[0]}")

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "cf_sandbox_report.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"target": root, "results": RESULTS}, f, indent=2)
    print(f"\nreport: {out}")
    print("\nNOT COVERED (needs real Blender): momentum inheritance, tunneling,")
    print("cloth-vs-rigidbody collision, Cell Fracture, cache sizes.")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
