
import sys
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "src"),
)

from investigator import investigate


def make_data():
    return pd.DataFrame({
        "student_id": [101, 102, 101],
        "updated_at": [
            "2026-10-10T10:00:00Z",
            "2026-10-10T10:00:00Z",
            "2026-10-10T10:00:00Z",
        ],
        "grade": [80, 90, 80],
    })


def run_investigation(data=None):
    return investigate(
        data if data is not None else make_data(),
        key_columns=["student_id"],
        timestamp_column="updated_at",
        max_age_hours=24,
        expected_schema={
            "student_id": "int64",
            "updated_at": "str",
            "grade": "int64",
        },
        now=datetime(
            2026, 10, 12, 10, 0,
            tzinfo=timezone.utc,
        ),
    )


def test_investigator_detects_multiple_issues():
    result = run_investigation()

    assert result["conclusion"] == "data_quality_issues_detected"
    assert {
        finding["finding"] for finding in result["findings"]
    } == {"duplicates", "freshness"}


def test_evidence_ledger_contains_all_checks():
    result = run_investigation()

    assert len(result["evidence_ledger"]) == 3
    assert {
        item["check"] for item in result["evidence_ledger"]
    } == {"duplicates", "freshness", "schema"}


def test_matching_data_has_no_configured_issues():
    data = pd.DataFrame({
        "student_id": [101, 102, 103],
        "updated_at": [
            "2026-10-12T09:00:00Z",
            "2026-10-12T09:15:00Z",
            "2026-10-12T09:30:00Z",
        ],
        "grade": [80, 90, 85],
    })

    result = run_investigation(data)

    assert result["conclusion"] == "no_configured_issues_detected"
    assert result["findings"] == []


def test_invalid_check_is_reported_as_inconclusive():
    result = investigate(
        make_data(),
        key_columns=["missing_id"],
        timestamp_column="updated_at",
        max_age_hours=24,
        expected_schema={
            "student_id": "int64",
            "updated_at": "str",
            "grade": "int64",
        },
        now=datetime(
            2026, 10, 12, 10, 0,
            tzinfo=timezone.utc,
        ),
    )

    assert result["status"] == "partial"
    assert result["conclusion"] == "inconclusive"
    assert "duplicates" in result["incomplete_checks"]


def test_investigate_hypotheses_handles_conflicting_evidence():
    from investigator import investigate_hypotheses

    result = investigate_hypotheses([
        {
            "name": "Pipeline delay",
            "supporting_evidence": [
                "Latest timestamp is 48 hours old"
            ],
            "contradicting_evidence": [
                "Pipeline logs show a successful recent run"
            ],
        }
    ])

    assert len(result["hypotheses"]) == 1
    assert result["hypotheses"][0]["assessment"] == "conflicted"
    assert result["root_cause_confirmed"] is False


def test_investigate_hypotheses_handles_multiple_hypotheses():
    from investigator import investigate_hypotheses

    result = investigate_hypotheses([
        {
            "name": "Pipeline delay",
            "supporting_evidence": ["Data is stale"],
        },
        {
            "name": "Schema mismatch",
            "supporting_evidence": [],
        },
    ])

    assert len(result["hypotheses"]) == 2
    assert (
        result["hypotheses"][0]["assessment"]
        == "supported_by_available_evidence"
    )
    assert result["hypotheses"][1]["assessment"] == "inconclusive"

