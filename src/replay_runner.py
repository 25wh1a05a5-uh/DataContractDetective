
"""Validate replay records and rerun saved CSV diagnostics."""

import json
import sys
from pathlib import Path

try:
    from .replay_record import calculate_file_sha256
    from .csv_loader import load_csv
    from .diagnostics import (
        check_duplicates,
        check_freshness,
        compare_schema,
        check_missing_values,
        check_numeric_range,
    )
except ImportError:
    from replay_record import calculate_file_sha256
    from csv_loader import load_csv
    from diagnostics import (
        check_duplicates,
        check_freshness,
        compare_schema,
        check_missing_values,
        check_numeric_range,
    )


REQUIRED_CONFIGURATION_KEYS = {
    "freshness_limit_hours",
    "duplicate_key_columns",
    "expected_schema",
    "marks_range",
}

EXPECTED_CHECKS = {
    "duplicates",
    "freshness",
    "schema",
    "missing_values",
    "marks_range",
}


def load_and_validate_replay(replay_path, input_path):
    """Validate saved settings and verify the original CSV fingerprint."""

    replay_path = Path(replay_path)
    input_path = Path(input_path)

    if not replay_path.is_file():
        raise FileNotFoundError(f"Replay record not found: {replay_path}")

    if not input_path.is_file():
        raise FileNotFoundError(f"Input CSV not found: {input_path}")

    try:
        record = json.loads(replay_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("Replay record contains invalid JSON.") from error

    if not isinstance(record, dict):
        raise ValueError("Replay record must be a JSON object.")

    if not record.get("investigation_id"):
        raise ValueError("Replay record is missing its investigation ID.")

    configuration = record.get("configuration")

    if not isinstance(configuration, dict):
        raise ValueError("Replay configuration must be an object.")

    missing_keys = REQUIRED_CONFIGURATION_KEYS - set(configuration)

    if missing_keys:
        raise ValueError(
            "Replay configuration is missing: "
            + ", ".join(sorted(missing_keys))
        )

    checks = record.get("checks_performed")

    if (
        not isinstance(checks, list)
        or any(not isinstance(item, str) for item in checks)
        or set(checks) != EXPECTED_CHECKS
        or len(checks) != len(EXPECTED_CHECKS)
    ):
        raise ValueError(
            "Replay record must list each supported check exactly once."
        )

    expected_hash = record.get("input_sha256")

    if (
        not isinstance(expected_hash, str)
        or len(expected_hash) != 64
        or any(c not in "0123456789abcdefABCDEF" for c in expected_hash)
    ):
        raise ValueError("Replay record has an invalid SHA-256 fingerprint.")

    actual_hash = calculate_file_sha256(input_path)

    if actual_hash.lower() != expected_hash.lower():
        raise ValueError(
            "Input file has changed since the original investigation. "
            "Replay stopped."
        )

    return {
        "record": record,
        "input_path": input_path.resolve(),
        "configuration": configuration,
        "checks_performed": checks,
        "input_sha256": actual_hash,
        "input_matches": True,
    }


def rerun_investigation(replay_path, input_path):
    """Rerun all five diagnostics using the saved configuration."""

    validated = load_and_validate_replay(replay_path, input_path)
    configuration = validated["configuration"]

    marks_config = configuration["marks_range"]

    if not isinstance(marks_config, dict):
        raise ValueError("The saved marks_range setting must be an object.")

    for key in ("column", "minimum", "maximum"):
        if key not in marks_config:
            raise ValueError(f"Saved marks_range is missing '{key}'.")

    loaded = load_csv(validated["input_path"])
    data = loaded["data"]

    diagnostics = {
        "duplicates": check_duplicates(
            data, configuration["duplicate_key_columns"]
        ),
        "freshness": check_freshness(
            data,
            timestamp_column="updated_at",
            max_age_hours=configuration["freshness_limit_hours"],
        ),
        "schema": compare_schema(
            data, configuration["expected_schema"]
        ),
        "missing_values": check_missing_values(data),
        "marks_range": check_numeric_range(
            data,
            marks_config["column"],
            minimum=marks_config["minimum"],
            maximum=marks_config["maximum"],
        ),
    }

    result = {
        "replay_of_investigation_id": (
            validated["record"]["investigation_id"]
        ),
        "input_file": loaded["file_name"],
        "input_sha256": validated["input_sha256"],
        "input_matches_original": validated["input_matches"],
        "configuration_used": configuration,
        "checks_performed": validated["checks_performed"],
        "row_count": loaded["row_count"],
        "columns": loaded["columns"],
        "diagnostics": diagnostics,
        "replay_note": (
            "Diagnostics were rerun using the saved configuration. "
            "Time-sensitive results, such as freshness, may differ "
            "from the original investigation."
        ),
    }

    project_dir = Path(__file__).resolve().parent.parent
    reports_dir = project_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    input_stem = Path(loaded["file_name"]).stem
    output_path = reports_dir / f"{input_stem}_replay_run.json"

    output_path.write_text(
        json.dumps(result, indent=2, default=str),
        encoding="utf-8",
    )

    return result, output_path


def main():
    if len(sys.argv) != 3:
        print(
            "Usage: python -m src.replay_runner "
            "<replay_record.json> <input.csv>"
        )
        sys.exit(2)

    try:
        result, output_path = rerun_investigation(
            sys.argv[1], sys.argv[2]
        )

        print("Replay completed successfully.")
        print(
            "Original investigation ID: "
            f"{result['replay_of_investigation_id']}"
        )
        print(f"Input unchanged: {result['input_matches_original']}")
        print(f"Rows inspected: {result['row_count']}")
        print(f"Checks rerun: {len(result['diagnostics'])}")
        print(f"Replay results: {output_path}")

    except (
        FileNotFoundError,
        ValueError,
        TypeError,
        KeyError,
        OSError,
    ) as error:
        print(f"Replay failed: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
