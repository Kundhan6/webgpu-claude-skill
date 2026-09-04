"""JSON preset load/save/validate, namespaced per add-on.

No external dependencies (Blender's Python ships without pip access by
default) — validation is a small hand-rolled schema walker.
"""

import json
import os

import bpy


class PresetValidationError(ValueError):
    pass


def _check_type(value, expected_type, path):
    if expected_type == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise PresetValidationError(f"{path}: expected number, got {type(value).__name__}")
    elif expected_type == "string":
        if not isinstance(value, str):
            raise PresetValidationError(f"{path}: expected string, got {type(value).__name__}")
    elif expected_type == "bool":
        if not isinstance(value, bool):
            raise PresetValidationError(f"{path}: expected bool, got {type(value).__name__}")
    elif expected_type == "array":
        if not isinstance(value, list):
            raise PresetValidationError(f"{path}: expected array, got {type(value).__name__}")
    elif expected_type == "object":
        if not isinstance(value, dict):
            raise PresetValidationError(f"{path}: expected object, got {type(value).__name__}")
    else:
        raise ValueError(f"Unknown schema type '{expected_type}'")


def validate(data, schema, path="root"):
    """Walk `data` against a small hand-rolled `schema` dict:

    {"type": "object", "required": {"name": {"type": "string"}, ...},
     "optional": {...}}
    {"type": "array", "items": {...}}
    {"type": "number", "min": 0, "max": 1}
    {"type": "string", "enum": ["a", "b"]}

    Raises PresetValidationError with a path-qualified message on the
    first mismatch. Never raises anything else — malformed schema usage
    is a programmer error (ValueError), bad data is PresetValidationError.
    """
    _check_type(data, schema["type"], path)

    if schema["type"] == "number":
        if "min" in schema and data < schema["min"]:
            raise PresetValidationError(f"{path}: {data} below minimum {schema['min']}")
        if "max" in schema and data > schema["max"]:
            raise PresetValidationError(f"{path}: {data} above maximum {schema['max']}")

    if schema["type"] == "string" and "enum" in schema:
        if data not in schema["enum"]:
            raise PresetValidationError(f"{path}: '{data}' not in {schema['enum']}")

    if schema["type"] == "object":
        for key, sub_schema in schema.get("required", {}).items():
            if key not in data:
                raise PresetValidationError(f"{path}: missing required key '{key}'")
            validate(data[key], sub_schema, f"{path}.{key}")
        for key, sub_schema in schema.get("optional", {}).items():
            if key in data:
                validate(data[key], sub_schema, f"{path}.{key}")

    if schema["type"] == "array":
        for i, item in enumerate(data):
            validate(item, schema["items"], f"{path}[{i}]")

    return True


def clamp_numeric(value, min_value, max_value):
    return max(min_value, min(max_value, value))


def builtin_presets_dir(addon_module_file):
    """Return the `presets/` folder shipped inside an add-on package,
    given that add-on's `__file__`."""
    return os.path.join(os.path.dirname(addon_module_file), "presets")


def user_presets_dir(addon_id):
    """Return (creating if needed) the per-add-on user preset folder under
    Blender's user scripts resource dir, so user-saved presets survive
    add-on updates."""
    base = bpy.utils.user_resource("SCRIPTS", path=os.path.join("presets", "kuro", addon_id), create=True)
    return base


def list_preset_files(*dirs):
    """Return sorted (name_without_ext, full_path) pairs for every .json
    file across the given directories (later dirs override earlier ones
    on name collision, e.g. user presets shadow built-ins)."""
    found = {}
    for d in dirs:
        if not d or not os.path.isdir(d):
            continue
        for fname in sorted(os.listdir(d)):
            if fname.endswith(".json"):
                found[fname[:-5]] = os.path.join(d, fname)
    return sorted(found.items())


def load_preset(path, schema=None, logger=None):
    """Load and (optionally) schema-validate a preset JSON file.

    Corrupt or invalid presets never crash the caller — they log a
    warning and return None, per ground rule #6 (no silent failures /
    graceful degradation) and §2.3 ("corrupt preset -> skip with warning").
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        if logger:
            logger.warning(f"Skipping unreadable preset '{path}': {e}")
        return None

    if schema is not None:
        try:
            validate(data, schema)
        except PresetValidationError as e:
            if logger:
                logger.warning(f"Skipping invalid preset '{path}': {e}")
            return None

    return data


def save_preset(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
