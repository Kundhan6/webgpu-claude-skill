"""Tier A (§13) — pure core, no bpy.

Covers core.naming.match_snapshot_records, the identity-resolution logic
CF_Reset's original_state restore (§8.0 step 5) is built on. Renaming a
part between CF_Prep's snapshot and CF_Reset must not make that part
silently unrestorable — cf_uid is the fix; these tests prove the fallback
and failure-reporting behavior around it, independent of any bpy object.
"""
from crash_forge.core.naming import match_snapshot_records, new_cf_uid


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
