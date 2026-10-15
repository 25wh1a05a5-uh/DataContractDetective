
import sys
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1] / "src"),
)

from diagnostics import (
    check_duplicates,
    check_freshness,
    compare_schema,
)


def test_duplicate_detection():
    df = pd.DataFrame({
        "student_id": [101, 102, 101],
    })

    result = check_duplicates(df, ["student_id"])

    assert result["status"] == "completed"
    assert result["duplicate_count"] == 2


def test_no_duplicates():
    df = pd.DataFrame({
        "student_id": [101, 102, 103],
    })

    result = check_duplicates(df, ["student_id"])

    assert result["duplicate_count"] == 0


def test_freshness_with_recent_data():
    df = pd.DataFrame({
        "updated_at": ["2026-10-12T10:00:00Z"],
    })

    reference_time = datetime(
        2026, 10, 12, 11, 0,
        tzinfo=timezone.utc,
    )

    result = check_freshness(
        df, "updated_at", 48, now=reference_time
    )

    assert result["status"] == "completed"
    assert result["is_fresh"] is True


def test_schema_matches():
    df = pd.DataFrame({
        "student_id": [101, 102],
        "name": ["A", "B"],
    })

    result = compare_schema(
        df,
        {"student_id": "int64", "name": "str"},
    )

    assert result["schema_matches"] is True


def test_schema_detects_missing_column():
    df = pd.DataFrame({
        "student_id": [101, 102],
    })

    result = compare_schema(
        df,
        {
            "student_id": "int64",
            "grade": "int64",
        },
    )

    assert result["schema_matches"] is False
    assert result["missing_columns"] == ["grade"]



from src.diagnostics import check_missing_values, check_numeric_range


def test_missing_values_detects_empty_cells():
    import pandas as pd

    data = pd.DataFrame({"marks": [85, None, 90]})
    result = check_missing_values(data)

    assert result["missing_cell_count"] == 1


def test_missing_values_when_no_cells_are_empty():
    import pandas as pd

    data = pd.DataFrame({"marks": [85, 90]})
    result = check_missing_values(data)

    assert result["missing_cell_count"] == 0


def test_numeric_range_detects_out_of_range_values():
    import pandas as pd

    data = pd.DataFrame({"marks": [85, 125, -5]})
    result = check_numeric_range(data, "marks")

    assert result["invalid_count"] == 2


def test_numeric_range_when_all_values_are_valid():
    import pandas as pd

    data = pd.DataFrame({"marks": [0, 50, 100]})
    result = check_numeric_range(data, "marks")

    assert result["invalid_count"] == 0

def test_freshness_with_stale_data():
    from datetime import datetime, timezone

    import pandas as pd

    from diagnostics import check_freshness

    data = pd.DataFrame({
        "updated_at": ["2026-10-13T10:00:00Z"]
    })

    now = datetime(2026, 10, 15, 10, 0, tzinfo=timezone.utc)

    result = check_freshness(
        data,
        timestamp_column="updated_at",
        max_age_hours=24,
        now=now,
    )

    assert result["status"] == "completed"
    assert result["is_fresh"] is False
    assert result["age_hours"] == 48.0
    assert result["evidence"] == "Data exceeds the freshness limit."
