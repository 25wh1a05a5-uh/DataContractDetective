
import copy

import pytest

from src.replay_comparison import compare_diagnostics


def make_reports():
    original_diagnostics = {
        "duplicates": {
            "status": "completed",
            "duplicate_count": 0,
            "evidence": "No duplicate records found.",
        },
        "freshness": {
            "status": "completed",
            "age_hours": 8.0,
            "latest_timestamp": "2026-10-15T10:00:00+00:00",
            "is_fresh": True,
            "max_age_hours": 24,
        },
        "schema": {
            "status": "completed",
            "schema_matches": False,
        },
        "missing_values": {
            "status": "completed",
            "missing_cell_count": 1,
        },
        "marks_range": {
            "status": "completed",
            "invalid_count": 2,
        },
    }

    original = {
        "replay_record": {
            "investigation_id": "test-investigation-001",
        },
        "csv_investigation": {
            "diagnostics": original_diagnostics,
        },
    }

    replay = {
        "replay_of_investigation_id": "test-investigation-001",
        "input_matches_original": True,
        "diagnostics": copy.deepcopy(original_diagnostics),
    }

    return original, replay


def test_identical_diagnostics_are_unchanged():
    original, replay = make_reports()

    result = compare_diagnostics(original, replay)

    assert result["summary"]["checks_compared"] == 5
    assert result["summary"]["checks_changed"] == 0
    assert result["summary"]["checks_unchanged"] == 5


def test_changed_diagnostic_field_is_detected():
    original, replay = make_reports()
    replay["diagnostics"]["marks_range"]["invalid_count"] = 3

    result = compare_diagnostics(original, replay)

    assert result["diagnostics"]["marks_range"]["status"] == "changed"
    assert (
        result["diagnostics"]["marks_range"]["changed_fields"]
        ["invalid_count"]["original"]
        == 2
    )
    assert (
        result["diagnostics"]["marks_range"]["changed_fields"]
        ["invalid_count"]["replay"]
        == 3
    )
    assert result["summary"]["checks_changed"] == 1


def test_freshness_age_change_alone_is_not_a_diagnostic_change():
    original, replay = make_reports()
    replay["diagnostics"]["freshness"]["age_hours"] = 9.0

    result = compare_diagnostics(original, replay)

    assert result["diagnostics"]["freshness"]["status"] == "unchanged"
    assert (
        result["diagnostics"]["freshness"]["time_sensitive_values_changed"]
        is True
    )


def test_missing_diagnostic_is_rejected():
    original, replay = make_reports()
    del replay["diagnostics"]["schema"]

    with pytest.raises(ValueError, match="missing diagnostics"):
        compare_diagnostics(original, replay)


def test_non_object_diagnostic_is_rejected():
    original, replay = make_reports()
    replay["diagnostics"]["schema"] = "invalid"

    with pytest.raises(ValueError, match="must be an object"):
        compare_diagnostics(original, replay)
