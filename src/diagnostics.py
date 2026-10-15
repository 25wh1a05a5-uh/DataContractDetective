
import pandas as pd


def check_duplicates(data, key_columns):
    """Find duplicate records using the specified columns."""

    if data.empty:
        return {
            "status": "insufficient_data",
            "duplicate_count": 0,
            "evidence": "The dataset is empty."
        }

    missing = [col for col in key_columns if col not in data.columns]

    if not key_columns or missing:
        return {
            "status": "invalid_input",
            "duplicate_count": 0,
            "evidence": f"Invalid key columns: {missing}"
        }

    duplicate_mask = data.duplicated(
        subset=key_columns,
        keep=False
    )
    duplicate_rows = data.loc[duplicate_mask]

    return {
        "status": "completed",
        "rows_checked": len(data),
        "key_columns": key_columns,
        "duplicate_count": int(duplicate_mask.sum()),
        "duplicate_rows": duplicate_rows.to_dict(orient="records"),
        "evidence": (
            "Duplicate records detected."
            if duplicate_mask.any()
            else "No duplicate records found."
        )
    }


def check_freshness(data, timestamp_column, max_age_hours, now=None):
    """Check data freshness and report invalid timestamp values."""

    from datetime import datetime, timezone

    if timestamp_column not in data.columns:
        return {
            "status": "invalid_input",
            "evidence": f"Missing column: {timestamp_column}"
        }

    if max_age_hours < 0:
        return {
            "status": "invalid_input",
            "evidence": "max_age_hours cannot be negative."
        }

    current_time = now if now is not None else datetime.now(timezone.utc)

    if current_time.tzinfo is None or current_time.utcoffset() is None:
        return {
            "status": "invalid_input",
            "evidence": "The reference time must include a timezone."
        }

    # Parse mixed timestamp formats and convert invalid values to NaT.
    timestamps = pd.to_datetime(
        data[timestamp_column],
        format="mixed",
        utc=True,
        errors="coerce"
    )

    valid_mask = timestamps.notna()
    valid_timestamps = timestamps[valid_mask]
    invalid_count = int((~valid_mask).sum())

    if valid_timestamps.empty:
        return {
            "status": "insufficient_data",
            "valid_timestamp_count": 0,
            "invalid_timestamp_count": invalid_count,
            "evidence": "No valid timestamps were found."
        }

    latest = valid_timestamps.max()
    age_hours = (
        pd.Timestamp(current_time) - latest
    ).total_seconds() / 3600

    fresh = age_hours <= max_age_hours

    return {
        "status": "completed",
        "latest_timestamp": latest.isoformat(),
        "age_hours": round(age_hours, 2),
        "max_age_hours": max_age_hours,
        "is_fresh": fresh,
        "valid_timestamp_count": int(valid_mask.sum()),
        "invalid_timestamp_count": invalid_count,
        "evidence": (
            "Data is within the freshness limit."
            if fresh
            else "Data exceeds the freshness limit."
        )
    }


def compare_schema(data, expected_schema):
    """Compare actual column names and data types with expectations."""

    if data.empty:
        return {
            "status": "insufficient_data",
            "evidence": "Cannot validate schema with no rows."
        }

    missing_columns = [
        column for column in expected_schema
        if column not in data.columns
    ]
    unexpected_columns = [
        column for column in data.columns
        if column not in expected_schema
    ]

    type_changes = {}

    for column, expected_type in expected_schema.items():
        if column in data.columns:
            actual_type = str(data[column].dtype)

            if actual_type != expected_type:
                type_changes[column] = {
                    "expected": expected_type,
                    "actual": actual_type
                }

    has_drift = bool(
        missing_columns or unexpected_columns or type_changes
    )

    return {
        "status": "completed",
        "schema_matches": not has_drift,
        "missing_columns": missing_columns,
        "unexpected_columns": unexpected_columns,
        "type_changes": type_changes,
        "evidence": (
            "Schema drift detected."
            if has_drift
            else "Schema matches expectations."
        )
    }


def check_missing_values(data):
    """Find missing cells in each column."""

    if data.empty:
        return {
            "status": "insufficient_data",
            "missing_cell_count": 0,
            "missing_by_column": {},
            "evidence": "The dataset is empty."
        }

    missing_by_column = {
        str(column): int(count)
        for column, count in data.isna().sum().items()
        if count > 0
    }
    total_missing = sum(missing_by_column.values())

    return {
        "status": "completed",
        "missing_cell_count": total_missing,
        "missing_by_column": missing_by_column,
        "evidence": (
            f"Found {total_missing} missing cell(s)."
            if total_missing
            else "No missing values found."
        )
    }


def check_numeric_range(data, column, minimum=0, maximum=100):
    """Find numeric values outside an allowed range."""

    if column not in data.columns:
        return {
            "status": "invalid_input",
            "invalid_count": 0,
            "evidence": f"Missing column: {column}"
        }

    if minimum > maximum:
        return {
            "status": "invalid_input",
            "invalid_count": 0,
            "evidence": "Minimum cannot exceed maximum."
        }

    values = pd.to_numeric(data[column], errors="coerce")
    invalid_mask = (
        values.notna()
        & ((values < minimum) | (values > maximum))
    )
    invalid_rows = data.loc[invalid_mask]

    return {
        "status": "completed",
        "column": column,
        "minimum": minimum,
        "maximum": maximum,
        "invalid_count": int(invalid_mask.sum()),
        "invalid_rows": invalid_rows.to_dict(orient="records"),
        "evidence": (
            f"Found {int(invalid_mask.sum())} value(s) outside "
            f"the range {minimum}–{maximum}."
            if invalid_mask.any()
            else f"All numeric values are within {minimum}–{maximum}."
        )
    }
