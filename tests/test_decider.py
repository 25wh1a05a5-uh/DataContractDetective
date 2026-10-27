import json
import sys
from urllib.error import URLError
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from decider import choose_next_diagnostic_action
from run_investigation import investigate_csv


def completed_diagnostics():
    return {
        "duplicates": {
            "status": "completed",
            "duplicate_count": 0,
            "evidence": "No duplicate records found.",
        },
        "freshness": {
            "status": "completed",
            "is_fresh": True,
            "age_hours": 1,
            "max_age_hours": 24,
            "evidence": "Data is within the freshness limit.",
        },
        "schema": {
            "status": "completed",
            "schema_matches": True,
            "missing_columns": [],
            "unexpected_columns": [],
            "type_changes": {},
            "evidence": "Schema matches expectations.",
        },
        "missing_values": {
            "status": "completed",
            "missing_cell_count": 0,
            "evidence": "No missing values found.",
        },
        "marks_range": {
            "status": "completed",
            "invalid_count": 1,
            "evidence": "Found 1 value outside the range.",
        },
    }


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


def test_falls_back_transparently_when_decider_url_is_not_configured():
    with patch.dict("os.environ", {"STRANDS_DECIDER_URL": ""}):
        result = choose_next_diagnostic_action({
            "diagnostics": completed_diagnostics(),
        })

    assert result["source"] == "rule_based_fallback"
    assert result["tool_name"] == "marks_range"
    assert result["confidence"] is None


def test_calls_official_choice_api_and_validates_selected_option():
    reply = {
        "model": "strands-decider-2B-test",
        "answers": {
            "next_tool": {
                "type": "choice",
                "choice": "freshness",
                "confidence": 0.82,
                "probabilities": {
                    "freshness": 0.82,
                    "marks_range": 0.18,
                },
            }
        },
    }
    with (
        patch.dict("os.environ", {"STRANDS_DECIDER_URL": "http://localhost:8000"}),
        patch("decider.urlopen", return_value=FakeResponse(reply)) as mocked_urlopen,
    ):
        result = choose_next_diagnostic_action({
            "diagnostics": completed_diagnostics(),
        })

    request = mocked_urlopen.call_args.args[0]
    request_payload = json.loads(request.data.decode("utf-8"))
    assert request.full_url == "http://localhost:8000/v1/systemone"
    assert request_payload["questions"]["next_tool"]["type"] == "choice"
    assert set(request_payload["questions"]["next_tool"]["criteria"]) == set(
        completed_diagnostics()
    )
    assert result["source"] == "strands_decider_2b"
    assert result["tool_name"] == "freshness"
    assert result["confidence"] == 0.82


def test_rejects_a_decider_choice_that_is_not_an_available_tool():
    reply = {
        "model": "strands-decider-2B-test",
        "answers": {
            "next_tool": {
                "type": "choice",
                "choice": "delete_database",
                "confidence": 0.99,
                "probabilities": {"delete_database": 1.0},
            }
        },
    }
    with (
        patch.dict("os.environ", {"STRANDS_DECIDER_URL": "http://localhost:8000"}),
        patch("decider.urlopen", return_value=FakeResponse(reply)),
        pytest.raises(RuntimeError, match="invalid next_tool choice"),
    ):
        choose_next_diagnostic_action({"diagnostics": completed_diagnostics()})


def test_reports_unavailable_decider_instead_of_using_fallback():
    with (
        patch.dict("os.environ", {"STRANDS_DECIDER_URL": "http://localhost:8000"}),
        patch("decider.urlopen", side_effect=URLError("connection refused")),
        pytest.raises(RuntimeError, match="Could not connect to Strands Decider"),
    ):
        choose_next_diagnostic_action({"diagnostics": completed_diagnostics()})


def test_missing_or_malformed_diagnostics_return_no_action_without_crashing():
    with patch.dict("os.environ", {"STRANDS_DECIDER_URL": ""}):
        result = choose_next_diagnostic_action({
            "diagnostics": {
                "marks_range": {
                    "status": "invalid_input",
                    "evidence": "Missing marks column.",
                }
            }
        })

    assert result["status"] == "no_actionable_diagnostics"
    assert result["tool_name"] is None


def test_rejects_malformed_decider_response():
    with (
        patch.dict("os.environ", {"STRANDS_DECIDER_URL": "http://localhost:8000"}),
        patch(
            "decider.urlopen",
            return_value=FakeResponse({
                "model": "strands-decider-2B-test",
                "answers": [],
            }),
        ),
        pytest.raises(RuntimeError, match="missing its answers"),
    ):
        choose_next_diagnostic_action({"diagnostics": completed_diagnostics()})


def test_rejects_a_decider_service_that_does_not_identify_a_2b_model():
    reply = {
        "model": "strands-decider-large",
        "answers": {
            "next_tool": {
                "type": "choice",
                "choice": "marks_range",
                "confidence": 0.9,
                "probabilities": {"marks_range": 0.9},
            }
        },
    }
    with (
        patch.dict("os.environ", {"STRANDS_DECIDER_URL": "http://localhost:8000"}),
        patch("decider.urlopen", return_value=FakeResponse(reply)),
        pytest.raises(RuntimeError, match="did not identify a Decider 2B model"),
    ):
        choose_next_diagnostic_action({"diagnostics": completed_diagnostics()})


def test_investigation_executes_the_tool_selected_by_decider(tmp_path):
    csv_path = tmp_path / "marks.csv"
    csv_path.write_text(
        "student_id,date,updated_at,marks\n"
        "1,2026-10-19,2026-10-19T10:00:00Z,125\n"
        "2,2026-10-19,2026-10-19T10:00:00Z,88\n",
        encoding="utf-8",
    )
    reply = {
        "model": "strands-decider-2B-test",
        "answers": {
            "next_tool": {
                "type": "choice",
                "choice": "marks_range",
                "confidence": 0.91,
                "probabilities": {"marks_range": 0.91},
            }
        },
    }
    with (
        patch.dict(
            "os.environ",
            {
                "STRANDS_DECIDER_URL": "http://localhost:8000",
                "BEDROCK_MODEL_ID": "",
            },
        ),
        patch("decider.urlopen", return_value=FakeResponse(reply)),
    ):
        report = investigate_csv(csv_path)

    assert report["next_diagnostic_action"]["source"] == "strands_decider_2b"
    assert report["next_diagnostic_action"]["tool_name"] == "marks_range"
    assert report["follow_up_diagnostic"]["status"] == "executed"
    assert report["follow_up_diagnostic"]["tool_name"] == "marks_range"
    assert report["follow_up_diagnostic"]["result"]["invalid_count"] == 1


def test_bedrock_failure_is_explicit(monkeypatch):
    from bedrock_summary import summarize_with_bedrock

    class FailingBedrockClient:
        def converse(self, **_kwargs):
            raise RuntimeError("model access denied")

    monkeypatch.setenv("BEDROCK_MODEL_ID", "example-model")
    monkeypatch.setitem(
        sys.modules,
        "boto3",
        SimpleNamespace(
            client=lambda *_args, **_kwargs: FailingBedrockClient()
        ),
    )

    result = summarize_with_bedrock({})

    assert result["status"] == "failed"
    assert "model access denied" in result["error"]


def test_bedrock_summary_uses_only_aggregate_evidence(monkeypatch):
    from bedrock_summary import summarize_with_bedrock

    captured = {}

    class FakeBedrockClient:
        def converse(self, **kwargs):
            captured.update(kwargs)
            return {
                "output": {
                    "message": {
                        "content": [{"text": "One mark is out of range."}]
                    }
                }
            }

    monkeypatch.setenv("BEDROCK_MODEL_ID", "example-model")
    monkeypatch.setitem(
        sys.modules,
        "boto3",
        SimpleNamespace(client=lambda *_args, **_kwargs: FakeBedrockClient()),
    )

    result = summarize_with_bedrock({
        "file_name": "private.csv",
        "row_count": 1,
        "findings": [{"check": "marks_range", "evidence": "One invalid mark."}],
        "next_diagnostic_action": {
            "tool_name": "marks_range",
            "source": "strands_decider_2b",
            "reason": "An out-of-range value was detected.",
            "confidence": 0.9,
        },
        "follow_up_diagnostic": {
            "tool_name": "marks_range",
            "status": "executed",
            "result": {
                "evidence": "One invalid mark.",
                "invalid_rows": [{"student_id": "private-student"}],
            },
        },
        "diagnostics": {
            "marks_range": {
                "status": "completed",
                "invalid_rows": [{"student_id": "private-student"}],
            }
        },
    })

    prompt = captured["messages"][0]["content"][0]["text"]
    assert result["status"] == "completed"
    assert "One mark is out of range." in result["text"]
    assert "private-student" not in prompt
