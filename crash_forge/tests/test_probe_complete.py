"""Tier B (§13) — stubbed bpy, no real Blender needed.

§6's table is a fixed row list. This asserts the probe report has an
entry for every one of them, and that the entry is never left at its
"not run" placeholder — locking shut the bug where four rows (§6's
RigidBodyConstraint props, RigidBodyWorld props, Remesh modifier,
SurfaceDeformModifier checks) were executing but writing nothing to the
report on success, indistinguishable from never having run at all.

Runs under the Tier B stub, where every bpy type/operator is absent by
design — so every row here reports its "missing" outcome, never a real
value. That's the correct behaviour of a stub with no API surface (see
bl/probe.py's own module docstring); what this test locks in is that a
row *always* produces some recorded outcome, success or failure, not that
the outcome itself is a pass on this stub.
"""


def test_probe_report_has_an_entry_for_every_section_6_row(stubbed_bpy):
    from crash_forge.bl import probe

    result = probe.run_probe()
    rows = result.data.get("rows")

    assert rows is not None, "run_probe() did not populate result.data['rows'] at all"
    assert set(rows.keys()) == set(probe.PROBE_ROWS), (
        f"row set mismatch — missing: {set(probe.PROBE_ROWS) - set(rows.keys())}, "
        f"unexpected: {set(rows.keys()) - set(probe.PROBE_ROWS)}"
    )


def test_no_row_is_left_at_its_not_run_placeholder(stubbed_bpy):
    from crash_forge.bl import probe

    result = probe.run_probe()
    rows = result.data["rows"]

    never_checked = [row for row, status in rows.items() if status == "not run"]
    assert never_checked == [], f"these §6 rows never actually ran a check: {never_checked}"


def test_probe_rows_is_a_fixed_list_matching_the_section_6_table_row_count(stubbed_bpy):
    """§6's table has 16 rows. If this drifts, PROBE_ROWS in bl/probe.py
    and this count both need updating together — a mismatch here is the
    signal that happened without the other."""
    from crash_forge.bl.probe import PROBE_ROWS

    assert len(PROBE_ROWS) == 16
    assert len(PROBE_ROWS) == len(set(PROBE_ROWS))  # no duplicate row ids
