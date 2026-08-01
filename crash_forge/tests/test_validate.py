"""Tier A (§13) — pure core, no bpy.

Covers core/validate.py: §11's V1, V2, V3, V5, and the added
ambiguous-part-name rule (V21) that moved AmbiguousNoColNameError's
check from Stage 2 Rig's pair generation into Prep, per §3 rule 10.
"""
from crash_forge.core.classify import PartDescriptor
from crash_forge.core.report import Severity, StageResult
from crash_forge.core.validate import (
    MAX_PART_COUNT,
    MIN_FRAME_END,
    MIN_PART_COUNT,
    ObjectScaleInfo,
    SceneMeta,
    run_prep_validations,
    validate_frame_range,
    validate_no_ambiguous_part_names,
    validate_object_scale,
    validate_part_count,
    validate_unit_scale,
)


def _part(name):
    return PartDescriptor(
        name=name, bbox_min=(0, 0, 0), bbox_max=(1, 1, 1), centroid=(0.5, 0.5, 0.5), vert_count=10,
    )


def _clean_meta(**overrides):
    defaults = dict(unit_scale=1.0, fps=24.0, frame_start=1, frame_end=300, object_scales=())
    defaults.update(overrides)
    return SceneMeta(**defaults)


# --- V1: unit scale -------------------------------------------------------


def test_v1_unit_scale_1_0_passes_clean():
    result = StageResult()
    validate_unit_scale(_clean_meta(unit_scale=1.0), result)
    assert result.ok
    assert result.errors == []


def test_v1_unit_scale_not_1_0_is_a_hard_stop():
    result = StageResult()
    validate_unit_scale(_clean_meta(unit_scale=0.01), result)
    assert not result.ok
    assert any(e.severity == Severity.CRITICAL and "V1" in e.message for e in result.errors)


# --- V2: object scale applied + uniform -----------------------------------


def test_v2_applied_uniform_scale_passes_clean():
    result = StageResult()
    meta = _clean_meta(object_scales=(ObjectScaleInfo("Door_L", applied=True, uniform=True),))
    offenders = validate_object_scale(meta, result)
    assert result.ok
    assert offenders == []


def test_v2_unapplied_scale_is_a_hard_stop_and_names_the_object():
    result = StageResult()
    meta = _clean_meta(object_scales=(ObjectScaleInfo("Hood", applied=False, uniform=True),))
    offenders = validate_object_scale(meta, result)
    assert not result.ok
    assert offenders == ["Hood"]
    assert any("Hood" in e.message for e in result.errors)


def test_v2_non_uniform_scale_is_a_hard_stop():
    result = StageResult()
    meta = _clean_meta(object_scales=(ObjectScaleInfo("Bumper_F", applied=True, uniform=False),))
    offenders = validate_object_scale(meta, result)
    assert not result.ok
    assert offenders == ["Bumper_F"]


def test_v2_reports_every_offender_not_just_the_first():
    result = StageResult()
    meta = _clean_meta(object_scales=(
        ObjectScaleInfo("A", applied=False, uniform=True),
        ObjectScaleInfo("B", applied=True, uniform=True),
        ObjectScaleInfo("C", applied=True, uniform=False),
    ))
    offenders = validate_object_scale(meta, result)
    assert offenders == ["A", "C"]


# --- V3: fps and frame range -----------------------------------------------


def test_v3_frame_end_at_minimum_passes_unextended():
    result = StageResult()
    frame_end = validate_frame_range(_clean_meta(frame_end=MIN_FRAME_END), result)
    assert frame_end == MIN_FRAME_END
    assert result.ok
    assert result.warnings == []


def test_v3_frame_end_below_minimum_warns_and_auto_extends():
    result = StageResult()
    frame_end = validate_frame_range(_clean_meta(frame_end=100), result)
    assert frame_end == MIN_FRAME_END
    assert result.ok  # a warning, not a hard stop
    assert any("V3" in str(n) for n in result.warnings)


def test_v3_zero_fps_is_a_hard_stop():
    result = StageResult()
    frame_end = validate_frame_range(_clean_meta(fps=0.0, frame_end=300), result)
    assert not result.ok
    assert frame_end == 300  # returned unchanged; nothing to extend to


def test_v3_negative_fps_is_a_hard_stop():
    result = StageResult()
    validate_frame_range(_clean_meta(fps=-24.0), result)
    assert not result.ok


def test_v3_frame_start_not_before_frame_end_is_a_hard_stop():
    result = StageResult()
    frame_end = validate_frame_range(_clean_meta(frame_start=300, frame_end=300), result)
    assert not result.ok
    assert frame_end == 300  # unchanged; nothing sane to extend


def test_v3_frame_start_after_frame_end_is_a_hard_stop():
    result = StageResult()
    validate_frame_range(_clean_meta(frame_start=400, frame_end=300), result)
    assert not result.ok


# --- V5: part count 4..25 ---------------------------------------------------


def test_v5_part_count_within_range_passes_clean():
    result = StageResult()
    validate_part_count([_part(f"P{i}") for i in range(10)], result)
    assert result.ok
    assert result.warnings == []


def test_v5_part_count_at_the_25_ceiling_passes():
    result = StageResult()
    validate_part_count([_part(f"P{i}") for i in range(MAX_PART_COUNT)], result)
    assert result.ok


def test_v5_part_count_above_25_is_a_hard_stop():
    result = StageResult()
    validate_part_count([_part(f"P{i}") for i in range(MAX_PART_COUNT + 1)], result)
    assert not result.ok
    assert any("V5" in str(n) for n in result.errors)


def test_v5_part_count_below_4_warns_not_hard_stops():
    result = StageResult()
    validate_part_count([_part(f"P{i}") for i in range(MIN_PART_COUNT - 1)], result)
    assert result.ok
    assert any("V5" in str(n) for n in result.warnings)


# --- added rule: ambiguous "__" part names (was AmbiguousNoColNameError) --


def test_ambiguous_name_check_passes_when_no_part_uses_double_underscore():
    result = StageResult()
    offenders = validate_no_ambiguous_part_names([_part("Door_L"), _part("Body")], result)
    assert result.ok
    assert offenders == []


def test_ambiguous_name_check_hard_stops_and_names_the_offending_object():
    """The exact real-world case this rule exists for: a part named
    Door__L, common on downloaded car models."""
    result = StageResult()
    offenders = validate_no_ambiguous_part_names([_part("Door__L"), _part("Body")], result)
    assert not result.ok
    assert offenders == ["Door__L"]
    messages = [e.message for e in result.errors]
    assert any("Door__L" in m for m in messages)
    assert any("rename" in m.lower() for m in messages)


def test_ambiguous_name_check_reports_every_offending_object():
    result = StageResult()
    offenders = validate_no_ambiguous_part_names(
        [_part("Door__L"), _part("Body"), _part("Window__Rear")], result,
    )
    assert offenders == ["Door__L", "Window__Rear"]


# --- run_prep_validations: full pass ---------------------------------------


def test_run_prep_validations_all_clean_is_ok():
    meta = _clean_meta()
    parts = [_part(f"P{i}") for i in range(6)]
    result = run_prep_validations(meta, parts)
    assert result.ok
    assert result.data["frame_end"] == 300


def test_run_prep_validations_collects_every_hard_stop_in_one_pass():
    """A scene failing V1 AND carrying an ambiguous name must report both
    — not stop accumulating detail after the first hard stop."""
    meta = _clean_meta(unit_scale=100.0)
    parts = [_part("Door__L"), _part("Body")]
    result = run_prep_validations(meta, parts)
    assert not result.ok
    codes = {e.code for e in result.errors}
    assert "V1" in codes
    assert "V21" in codes
