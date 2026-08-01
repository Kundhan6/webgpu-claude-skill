"""§3 rule 3 ("core/ imports nothing from bpy, bmesh or mathutils"),
enforced by a test instead of by discipline. Scans every .py file in
core/ via ast (not a text grep, so a docstring saying "No bpy import"
can't accidentally trip a false positive) and fails on any bpy/bmesh/
mathutils import, direct or "from X import Y" style, anywhere in the tree.
"""
import ast
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parent.parent / "core"
FORBIDDEN_MODULES = {"bpy", "bmesh", "mathutils"}


def _imported_top_level_modules(path: Path) -> set:
    tree = ast.parse(path.read_text(), filename=str(path))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:  # level>0 is a relative import within core/
                modules.add(node.module.split(".")[0])
    return modules


def test_core_directory_exists_and_has_files_to_scan():
    """A guard against this whole test file silently passing because
    CORE_DIR resolved to the wrong place and glob found nothing."""
    assert CORE_DIR.is_dir()
    files = list(CORE_DIR.rglob("*.py"))
    assert len(files) >= 8, f"expected at least 8 files under {CORE_DIR}, found {len(files)}"


def test_no_core_file_imports_bpy_bmesh_or_mathutils():
    offenders = {}
    for path in sorted(CORE_DIR.rglob("*.py")):
        forbidden = _imported_top_level_modules(path) & FORBIDDEN_MODULES
        if forbidden:
            offenders[str(path.relative_to(CORE_DIR))] = sorted(forbidden)

    assert not offenders, f"core/ files importing forbidden modules: {offenders}"


def test_ast_scan_actually_detects_a_forbidden_import():
    """A guard against the scanner itself being broken and passing
    everything regardless of content — proves it catches a real case."""
    modules = _imported_top_level_modules_from_source("import bpy\nfrom bmesh import new\n")
    assert modules & FORBIDDEN_MODULES == {"bpy", "bmesh"}


def _imported_top_level_modules_from_source(source: str) -> set:
    tree = ast.parse(source)
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                modules.add(node.module.split(".")[0])
    return modules
