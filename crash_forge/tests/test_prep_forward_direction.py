"""Tier B (§13) — stubbed bpy (ops/prep.py imports bpy at module level,
so even this pure string-formatting helper needs the stub to import).

§12.3 step 5: "print the resolved direction in the CF_Prep summary line,
e.g. 'forward = -Y (auto)'". Locks in the exact format and the enum-to-
override-value mapping CF_Prep's Car > Forward Direction property drives.
"""


def test_forward_direction_line_matches_the_spec_example_format(stubbed_bpy):
    from crash_forge.ops.prep import _forward_direction_line

    assert _forward_direction_line(forward_axis=1, sign=-1, source="auto") == "forward = -Y (auto)"


def test_forward_direction_line_positive_x_override(stubbed_bpy):
    from crash_forge.ops.prep import _forward_direction_line

    assert _forward_direction_line(forward_axis=0, sign=1, source="override") == "forward = +X (override)"


def test_forward_override_enum_values_map_to_resolve_forward_sign_override_arg(stubbed_bpy):
    from crash_forge.ops.prep import _FORWARD_OVERRIDE_VALUES

    assert _FORWARD_OVERRIDE_VALUES == {'AUTO': None, 'POSITIVE': 1, 'NEGATIVE': -1}
