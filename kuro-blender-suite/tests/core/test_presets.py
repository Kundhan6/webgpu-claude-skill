"""Tests for kuro_core.presets — schema validation, corrupt-file handling."""

import os

from kuro_core import presets
from tests import harness

SPEC_SCHEMA = {
    "type": "object",
    "required": {
        "name": {"type": "string"},
        "strength": {"type": "number", "min": 0.0, "max": 1.0},
    },
    "optional": {
        "layers": {
            "type": "array",
            "items": {
                "type": "object",
                "required": {"type": {"type": "string", "enum": ["a", "b"]}},
                "optional": {},
            },
        },
    },
}


def test_validate_accepts_good_spec():
    data = {"name": "Test", "strength": 0.5, "layers": [{"type": "a"}]}
    harness.assert_true(presets.validate(data, SPEC_SCHEMA))


def test_validate_rejects_missing_required_key():
    data = {"strength": 0.5}
    harness.assert_raises(presets.PresetValidationError, presets.validate, data, SPEC_SCHEMA)


def test_validate_rejects_out_of_range_number():
    data = {"name": "Test", "strength": 1.5}
    harness.assert_raises(presets.PresetValidationError, presets.validate, data, SPEC_SCHEMA)


def test_validate_rejects_bad_enum_value():
    data = {"name": "Test", "strength": 0.5, "layers": [{"type": "not_a_or_b"}]}
    harness.assert_raises(presets.PresetValidationError, presets.validate, data, SPEC_SCHEMA)


def test_clamp_numeric():
    harness.assert_equal(presets.clamp_numeric(1.5, 0.0, 1.0), 1.0)
    harness.assert_equal(presets.clamp_numeric(-0.5, 0.0, 1.0), 0.0)
    harness.assert_equal(presets.clamp_numeric(0.5, 0.0, 1.0), 0.5)


def test_save_and_load_roundtrip(tmp_dir="/tmp/kuro_preset_test"):
    os.makedirs(tmp_dir, exist_ok=True)
    path = os.path.join(tmp_dir, "roundtrip.json")
    data = {"name": "Test", "strength": 0.5}
    presets.save_preset(path, data)
    loaded = presets.load_preset(path, schema=SPEC_SCHEMA)
    harness.assert_equal(loaded, data)


def test_load_preset_returns_none_on_corrupt_json(tmp_dir="/tmp/kuro_preset_test"):
    os.makedirs(tmp_dir, exist_ok=True)
    path = os.path.join(tmp_dir, "corrupt.json")
    with open(path, "w") as f:
        f.write("{not valid json")
    loaded = presets.load_preset(path, schema=SPEC_SCHEMA)
    harness.assert_true(loaded is None)


def test_load_preset_returns_none_on_schema_violation(tmp_dir="/tmp/kuro_preset_test"):
    os.makedirs(tmp_dir, exist_ok=True)
    path = os.path.join(tmp_dir, "invalid_schema.json")
    presets.save_preset(path, {"name": "Test"})  # missing 'strength'
    loaded = presets.load_preset(path, schema=SPEC_SCHEMA)
    harness.assert_true(loaded is None)


def test_list_preset_files_user_overrides_builtin():
    builtin_dir = "/tmp/kuro_preset_test/builtin"
    user_dir = "/tmp/kuro_preset_test/user"
    os.makedirs(builtin_dir, exist_ok=True)
    os.makedirs(user_dir, exist_ok=True)
    presets.save_preset(os.path.join(builtin_dir, "clear.json"), {"name": "Clear (builtin)", "strength": 0.1})
    presets.save_preset(os.path.join(user_dir, "clear.json"), {"name": "Clear (user)", "strength": 0.2})

    found = dict(presets.list_preset_files(builtin_dir, user_dir))
    harness.assert_true("clear" in found)
    loaded = presets.load_preset(found["clear"], schema=SPEC_SCHEMA)
    harness.assert_equal(loaded["name"], "Clear (user)")
