"""Entry point for the full KURO suite test run.

Usage:
    blender --background --factory-startup --python tests/run_all.py

Discovers every tests/**/test_*.py file, runs its test_* functions in
isolation (fresh empty scene per test), prints a pass/fail summary, and
exits nonzero if anything failed — this is the single command
scripts/test.sh wraps for the phase gates in the master plan.
"""

import os
import sys

TESTS_ROOT = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TESTS_ROOT)

for path in (REPO_ROOT, TESTS_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from tests import harness  # noqa: E402


def find_test_files():
    files = []
    for dirpath, _dirnames, filenames in os.walk(TESTS_ROOT):
        if os.path.basename(dirpath) == "golden":
            continue
        for fname in sorted(filenames):
            if fname.startswith("test_") and fname.endswith(".py"):
                files.append(os.path.join(dirpath, fname))
    return sorted(files)


def main():
    results = []
    for path in find_test_files():
        module = harness.import_test_module(path, TESTS_ROOT)
        harness.run_module(module, results)

    ok = harness.print_summary(results)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
