
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.replay_record import (
    calculate_file_sha256,
    create_replay_record,
    save_replay_record,
)


def test_file_fingerprint_is_consistent(tmp_path):
    file_path = tmp_path / "sample.csv"
    file_path.write_text("id,marks\n1,85\n", encoding="utf-8")

    first_hash = calculate_file_sha256(file_path)
    second_hash = calculate_file_sha256(file_path)

    assert first_hash == second_hash
    assert len(first_hash) == 64


def test_file_fingerprint_changes_when_contents_change(tmp_path):
    file_path = tmp_path / "sample.csv"
    file_path.write_text("id,marks\n1,85\n", encoding="utf-8")
    first_hash = calculate_file_sha256(file_path)

    file_path.write_text("id,marks\n1,90\n", encoding="utf-8")
    second_hash = calculate_file_sha256(file_path)

    assert first_hash != second_hash


def test_create_replay_record_contains_expected_fields(tmp_path):
    file_path = tmp_path / "sample.csv"
    file_path.write_text("id,marks\n1,85\n", encoding="utf-8")

    record = create_replay_record(
        file_path,
        {"max_age_hours": 24},
        ["freshness", "schema"],
    )

    assert record["input_file"] == "sample.csv"
    assert len(record["input_sha256"]) == 64
    assert record["configuration"] == {"max_age_hours": 24}
    assert record["checks_performed"] == ["freshness", "schema"]
    assert record["investigation_id"]
    assert record["created_at_utc"]


def test_create_replay_record_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        create_replay_record(
            tmp_path / "missing.csv",
            {},
            [],
        )


def test_create_replay_record_rejects_invalid_configuration(tmp_path):
    file_path = tmp_path / "sample.csv"
    file_path.write_text("id\n1\n", encoding="utf-8")

    with pytest.raises(TypeError):
        create_replay_record(file_path, [], [])


def test_create_replay_record_rejects_invalid_checks(tmp_path):
    file_path = tmp_path / "sample.csv"
    file_path.write_text("id\n1\n", encoding="utf-8")

    with pytest.raises(ValueError):
        create_replay_record(file_path, {}, ["freshness", ""])


def test_save_replay_record_creates_json(tmp_path):
    output_path = tmp_path / "reports" / "replay.json"
    record = {
        "investigation_id": "test-id",
        "input_file": "sample.csv",
    }

    saved_path = save_replay_record(record, output_path)

    assert saved_path.exists()
    saved_record = json.loads(saved_path.read_text(encoding="utf-8"))
    assert saved_record == record
