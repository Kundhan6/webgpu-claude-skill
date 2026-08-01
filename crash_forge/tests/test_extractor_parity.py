"""Verifies bl/extract.py's tuned constants haven't silently drifted from
tools/dump_car.py's.

tools/dump_car.py and bl/extract.py are two independent producers of the
same JSON schema (core/descriptor_io.py) by design — dump_car.py must
stay a fully standalone script (it does not import crash_forge, and
crash_forge does not import it), so nothing at import time or at runtime
enforces the two agree on a threshold like PLANAR_THIN_RATIO. Krish's M4
verification is a diff between a real dump_car.py run and CF_Prep's own
descriptor dump on the same car — that diff is only meaningful if both
sides actually compute is_planar (and anything else tuned) the same way.

AST-parsed, not a text grep — same reasoning as test_no_bpy.py: a
docstring or comment mentioning a constant's name must not accidentally
satisfy this.
"""
import ast
import tempfile
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DUMP_CAR_PATH = PACKAGE_ROOT / "tools" / "dump_car.py"
EXTRACT_PATH = PACKAGE_ROOT / "bl" / "extract.py"

# Every constant that must stay byte-for-byte identical between the two
# producers. Extend this tuple — don't fork the check below — whenever a
# new shared tuned constant is added to either file.
SHARED_TUNED_CONSTANTS = ("PLANAR_THIN_RATIO",)


def _module_level_constants(path: Path, names) -> dict:
    """Module-level `NAME = <literal>` assignments only — walks
    tree.body (the module's top-level statements), not the full tree, so
    a same-named constant reassigned inside a function or class can't be
    mistaken for the one either module actually uses at import time."""
    tree = ast.parse(path.read_text(), filename=str(path))
    found = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in names:
                found[target.id] = ast.literal_eval(node.value)
    return found


def test_dump_car_and_extract_files_exist():
    """Guard against either path silently resolving to nothing and the
    real checks below vacuously passing on two empty dicts."""
    assert DUMP_CAR_PATH.is_file(), f"expected {DUMP_CAR_PATH} to exist"
    assert EXTRACT_PATH.is_file(), f"expected {EXTRACT_PATH} to exist"


def test_every_shared_tuned_constant_is_defined_in_both_files():
    dump_car_consts = _module_level_constants(DUMP_CAR_PATH, SHARED_TUNED_CONSTANTS)
    extract_consts = _module_level_constants(EXTRACT_PATH, SHARED_TUNED_CONSTANTS)

    missing_from_dump_car = set(SHARED_TUNED_CONSTANTS) - dump_car_consts.keys()
    missing_from_extract = set(SHARED_TUNED_CONSTANTS) - extract_consts.keys()

    assert not missing_from_dump_car, f"tools/dump_car.py is missing: {sorted(missing_from_dump_car)}"
    assert not missing_from_extract, f"bl/extract.py is missing: {sorted(missing_from_extract)}"


def test_shared_tuned_constants_match_between_dump_car_and_extract():
    """The actual parity check: if bl/extract.py's copy of
    PLANAR_THIN_RATIO (or any future name added to
    SHARED_TUNED_CONSTANTS) ever drifts from tools/dump_car.py's, this
    fails at test time — not silently, inside someone's verification
    diff months later."""
    dump_car_consts = _module_level_constants(DUMP_CAR_PATH, SHARED_TUNED_CONSTANTS)
    extract_consts = _module_level_constants(EXTRACT_PATH, SHARED_TUNED_CONSTANTS)

    mismatches = {
        name: {"dump_car.py": dump_car_consts[name], "bl/extract.py": extract_consts[name]}
        for name in SHARED_TUNED_CONSTANTS
        if name in dump_car_consts and name in extract_consts
        and dump_car_consts[name] != extract_consts[name]
    }
    assert not mismatches, f"tools/dump_car.py and bl/extract.py disagree: {mismatches}"


def test_ast_scan_actually_detects_a_real_mismatch():
    """Guard against the scanner itself being broken and passing
    regardless of content — proves it catches real drift, against two
    throwaway files so it doesn't depend on the real pair ever
    disagreeing with itself."""
    with tempfile.TemporaryDirectory() as tmp:
        a = Path(tmp) / "a.py"
        b = Path(tmp) / "b.py"
        a.write_text("SOME_RATIO = 0.15\n")
        b.write_text("SOME_RATIO = 0.20\n")

        value_a = _module_level_constants(a, ("SOME_RATIO",))["SOME_RATIO"]
        value_b = _module_level_constants(b, ("SOME_RATIO",))["SOME_RATIO"]

        assert value_a != value_b
