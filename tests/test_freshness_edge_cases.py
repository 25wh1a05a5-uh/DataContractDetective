
"""Edge-case tests for freshness diagnostics."""

import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from diagnostics import check_freshness


def test_freshness_rejects_missing_timestamp_column():
    data = pd.DataFrame({"student_id": [1, 2]})

    result = check_freshness(
        data,
        timestamp_column="updated_at",
        max_age_hours=24,
    )

    assert result["status"] == "invalid_input"
    assert result["evidence"] == "Missing column: updated_at"


def test_freshness_handles_empty_dataset():
    data = pd.DataFrame({"updated_at": []})

    result = check_freshness(
        data,
        timestamp_column="updated_at",
        max_age_hours=24,
    )

    assert result["status"] == "insufficient_data"
    assert result["evidence"] == "No valid timestamps were found."


def test_freshness_handles_only_invalid_timestamps():
    data = pd.DataFrame({
        "updated_at": ["not-a-timestamp", "invalid-date"]
    })

    result = check_freshness(
        data,
        timestamp_column="updated_at",
        max_age_hours=24,
    )

    assert result["status"] == "insufficient_data"
    assert result["evidence"] == "No valid timestamps were found."


def test_freshness_uses_valid_timestamp_when_others_are_invalid():
    data = pd.DataFrame({
        "updated_at": [
            "2026-10-15T09:00:00Z",
            None,
            "not-a-timestamp",
        ]
    })

    fixed_now = datetime(
        2026, 10, 15, 10, 0, tzinfo=timezone.utc
    )

    result = check_freshness(
        data,
        timestamp_column="updated_at",
        max_age_hours=24,
        now=fixed_now,
    )

    assert result["status"] == "completed"
    assert result["is_fresh"] is True
    assert result["age_hours"] == 1.0
    assert result["evidence"] == "Data is within the freshness limit."
