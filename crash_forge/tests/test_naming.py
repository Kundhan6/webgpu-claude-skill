"""Tier A (§13) — pure core, no bpy. Round-trip name generation and parsing
for the full §7.1 table.
"""
from crash_forge.core.naming import (
    BARRIER_NAME,
    PROXY_NAME,
    RBW_COLLECTION_NAME,
    RBWC_COLLECTION_NAME,
    break_name,
    hinge_name,
    motor_name,
    nocol_name,
    parse_cf_name,
)


def test_hinge_round_trip():
    name = hinge_name("Wheel_FL")
    assert name == "CF_Hinge_Wheel_FL"
    parsed = parse_cf_name(name)
    assert parsed.kind == "hinge"
    assert parsed.args == ("Wheel_FL",)


def test_motor_round_trip():
    name = motor_name("Wheel_RL")
    parsed = parse_cf_name(name)
    assert parsed.kind == "motor"
    assert parsed.args == ("Wheel_RL",)


def test_break_round_trip():
    name = break_name("Door_L")
    parsed = parse_cf_name(name)
    assert parsed.kind == "break"
    assert parsed.args == ("Door_L",)


def test_nocol_round_trip():
    name = nocol_name("Door_L", "Body")
    assert name == "CF_NoCol_Door_L__Body"
    parsed = parse_cf_name(name)
    assert parsed.kind == "nocol"
    assert parsed.args == ("Door_L", "Body")


def test_fixed_singleton_names_round_trip():
    assert parse_cf_name(PROXY_NAME).kind == "proxy"
    assert parse_cf_name(BARRIER_NAME).kind == "barrier"
    assert parse_cf_name(RBW_COLLECTION_NAME).kind == "rbw"
    assert parse_cf_name(RBWC_COLLECTION_NAME).kind == "rbwc"


def test_unrecognised_cf_name_parses_as_unknown_not_an_exception():
    parsed = parse_cf_name("CF_SomethingNobodyGenerated")
    assert parsed.kind == "unknown"
    assert parsed.args == ("CF_SomethingNobodyGenerated",)


def test_non_cf_name_parses_as_unknown():
    parsed = parse_cf_name("Door_L")
    assert parsed.kind == "unknown"


def test_nocol_without_separator_parses_as_unknown():
    # Starts with the NoCol prefix but has no "__" split point.
    parsed = parse_cf_name("CF_NoCol_JustOneName")
    assert parsed.kind == "unknown"


def test_nocol_handles_part_names_that_themselves_contain_underscores():
    name = nocol_name("Wheel_FL", "Bumper_F")
    parsed = parse_cf_name(name)
    assert parsed.kind == "nocol"
    assert parsed.args == ("Wheel_FL", "Bumper_F")


def test_generated_names_are_distinguishable_by_kind():
    names = [
        hinge_name("A"), motor_name("A"), break_name("A"), nocol_name("A", "B"),
        PROXY_NAME, BARRIER_NAME, RBW_COLLECTION_NAME, RBWC_COLLECTION_NAME,
    ]
    kinds = {parse_cf_name(n).kind for n in names}
    assert kinds == {"hinge", "motor", "break", "nocol", "proxy", "barrier", "rbw", "rbwc"}
