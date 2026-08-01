"""Tier A (§13) — pure core, no bpy.

Covers core.naming.match_snapshot_records, the identity-resolution logic
CF_Reset's original_state restore (§8.0 step 5) is built on, plus the
schema_version contract (build_snapshot/parse_snapshot) that CF_Prep
(M4, not yet built) must produce. Renaming a part between CF_Prep's
snapshot and CF_Reset must not make that part silently unrestorable —
cf_uid is the fix; these tests prove the fallback and failure-reporting
behavior around it, independent of any bpy object.
"""
from crash_forge.core.naming import (
    build_snapshot,
    match_snapshot_records,
    new_cf_uid,
    parse_snapshot,
)


def test_matches_by_uid_even_when_name_changed():
    records = [{"cf_uid": "uid-1", "name": "Door_L"}]
    live = [("uid-1", "Door_L_renamed")]

    matches, missing = match_snapshot_records(records, live)

    assert matches == {0: 0}
    assert missing == []


def test_falls_back_to_name_when_record_has_no_uid():
    records = [{"cf_uid": None, "name": "Hood"}]
    live = [(None, "Hood")]

    matches, missing = match_snapshot_records(records, live)

    assert matches == {0: 0}
    assert missing == []


def test_falls_back_to_name_when_uid_matches_nothing_live():
    records = [{"cf_uid": "stale-uid", "name": "Bumper_F"}]
    live = [(None, "Bumper_F")]

    matches, missing = match_snapshot_records(records, live)

    assert matches == {0: 0}
    assert missing == []


def test_missing_part_is_reported_not_skipped():
    records = [
        {"cf_uid": "uid-1", "name": "Door_L"},
        {"cf_uid": "uid-2", "name": "Door_R"},
    ]
    live = [("uid-1", "Door_L")]  # Door_R is gone: renamed AND uid lost

    matches, missing = match_snapshot_records(records, live)

    assert matches == {0: 0}
    assert missing == ["Door_R"]


def test_missing_record_falls_back_to_uid_label_when_nameless():
    records = [{"cf_uid": "uid-9", "name": None}]
    live = []

    matches, missing = match_snapshot_records(records, live)

    assert matches == {}
    assert missing == ["uid-9"]


def test_partial_restore_reports_exact_counts():
    records = [{"cf_uid": f"uid-{i}", "name": f"Part_{i}"} for i in range(14)]
    live = [(f"uid-{i}", f"Part_{i}") for i in range(12)]  # last 2 gone

    matches, missing = match_snapshot_records(records, live)

    assert len(matches) == 12
    assert missing == ["Part_12", "Part_13"]


def test_new_cf_uid_generates_distinct_nonempty_ids():
    a = new_cf_uid()
    b = new_cf_uid()
    assert a != b
    assert isinstance(a, str) and len(a) > 0


# --- schema_version contract --------------------------------------------


def test_schema_version_round_trip_preserves_records():
    original_records = [
        {"cf_uid": new_cf_uid(), "name": "Door_L", "matrix_world": None, "parent_uid": None, "parent_name": None},
        {"cf_uid": new_cf_uid(), "name": "Door_R", "matrix_world": None, "parent_uid": None, "parent_name": None},
    ]

    snapshot = build_snapshot(original_records)
    records, error = parse_snapshot(snapshot)

    assert error is None
    assert records == original_records


def test_unrecognised_schema_version_is_refused_not_guessed():
    snapshot = {"schema_version": 999, "records": [{"cf_uid": "x", "name": "Hood"}]}

    records, error = parse_snapshot(snapshot)

    assert records == []
    assert error is not None
    assert "999" in error


def test_missing_schema_version_is_refused():
    snapshot = {"records": []}

    records, error = parse_snapshot(snapshot)

    assert records == []
    assert error is not None


def test_non_dict_snapshot_is_refused():
    records, error = parse_snapshot(["not", "a", "dict"])

    assert records == []
    assert error is not None


def test_snapshot_missing_records_list_is_refused():
    records, error = parse_snapshot({"schema_version": 1})

    assert records == []
    assert error is not None


# --- full round trip: synthetic descriptors -> records -> match -> identity ---


def test_full_round_trip_synthetic_descriptors_to_match_identity():
    """The chain CF_Prep -> snapshot -> CF_Reset must actually run end to
    end, not just each piece in isolation: build synthetic part
    descriptors, turn them into snapshot records the way CF_Prep will,
    round-trip through build_snapshot/parse_snapshot, then match against a
    simulated live scene (one part renamed) and confirm every match
    resolves back to the descriptor with the same cf_uid."""
    descriptors = [
        {"name": "Hood", "cf_uid": new_cf_uid()},
        {"name": "Door_L", "cf_uid": new_cf_uid()},
        {"name": "Bumper_F", "cf_uid": new_cf_uid()},
    ]
    records = [
        {
            "cf_uid": d["cf_uid"],
            "name": d["name"],
            "matrix_world": None,
            "parent_uid": None,
            "parent_name": None,
        }
        for d in descriptors
    ]

    snapshot = build_snapshot(records)
    parsed_records, error = parse_snapshot(snapshot)
    assert error is None
    assert parsed_records == records

    # Simulate the scene later: Hood got renamed (e.g. Blender's ".001"
    # collision suffix); Door_L and Bumper_F are untouched.
    live_objects = [
        (descriptors[0]["cf_uid"], "Hood.001"),
        (descriptors[1]["cf_uid"], "Door_L"),
        (descriptors[2]["cf_uid"], "Bumper_F"),
    ]

    matches, missing = match_snapshot_records(parsed_records, live_objects)

    assert missing == []
    assert len(matches) == len(descriptors)
    for record_idx, live_idx in matches.items():
        assert parsed_records[record_idx]["cf_uid"] == live_objects[live_idx][0]
