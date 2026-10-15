
import hashlib
import json

import pytest

from src.replay_runner import (
    load_and_validate_replay,
    rerun_investigation,
)


def create_test_files(tmp_path):
    csv_path = tmp_path / "students.csv"
    csv_path.write_text(
        "student_id,date,updated_at,marks\n"
        "101,2026-10-15,2026-10-15 10:00:00,85\n"
        "102,2026-10-15,2026-10-15 10:00:00,90\n",
        encoding="utf-8",
    )

    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()

    record = {
        "investigation_id": "test-investigation-001",
        "input_file": "students.csv",
        "input_sha256": digest,
        "configuration": {
            "freshness_limit_hours": 24,
            "duplicate_key_columns": ["student_id"],
            "expected_schema": {
                "student_id": "int64",
                "date": "str",
                "updated_at": "str",
                "marks": "int64",
            },
            "marks_range": {
                "column": "marks",
                "minimum": 0,
                "maximum": 100,
            },
        },
        "checks_performed": [
            "duplicates",
            "freshness",
            "schema",
            "missing_values",
            "marks_range",
        ],
    }

    replay_path = tmp_path / "replay.json"
    replay_path.write_text(
        json.dumps(record),
        encoding="utf-8",
    )

    return replay_path, csv_path


def test_valid_replay_record_matches_input(tmp_path):
    replay_path, csv_path = create_test_files(tmp_path)

    result = load_and_validate_replay(replay_path, csv_path)

    assert result["input_matches"] is True
    assert (
        result["record"]["investigation_id"]
        == "test-investigation-001"
    )


def test_changed_input_is_rejected(tmp_path):
    replay_path, csv_path = create_test_files(tmp_path)

    csv_path.write_text(
        csv_path.read_text(encoding="utf-8")
        + "103,2026-10-15,2026-10-15 10:00:00,75\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Input file has changed"):
        load_and_validate_replay(replay_path, csv_path)


def test_invalid_replay_json_is_rejected(tmp_path):
    replay_path, csv_path = create_test_files(tmp_path)
    replay_path.write_text("{invalid json", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid JSON"):
        load_and_validate_replay(replay_path, csv_path)


def test_missing_configuration_is_rejected(tmp_path):
    replay_path, csv_path = create_test_files(tmp_path)

    record = json.loads(
        replay_path.read_text(encoding="utf-8")
    )
    del record["configuration"]["marks_range"]

    replay_path.write_text(
        json.dumps(record),
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="configuration is missing",
    ):
        load_and_validate_replay(replay_path, csv_path)


def test_replay_runs_all_five_diagnostics(tmp_path, monkeypatch):
    replay_path, csv_path = create_test_files(tmp_path)

    result, output_path = rerun_investigation(
        replay_path,
        csv_path,
    )

    assert result["input_matches_original"] is True
    assert len(result["diagnostics"]) == 5

    assert set(result["diagnostics"]) == {
        "duplicates",
        "freshness",
        "schema",
        "missing_values",
        "marks_range",
    }

    assert output_path.is_file()
