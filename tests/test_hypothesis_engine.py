
import pytest

from hypothesis_engine import evaluate_hypothesis


def test_supported_hypothesis():
    result = evaluate_hypothesis(
        "Pipeline delay",
        ["Latest timestamp is 48 hours old"],
        [],
        ["Latest timestamp is 48 hours old"],
    )

    assert result["assessment"] == "supported_by_available_evidence"
    assert result["root_cause_confirmed"] is False
    assert result["missing_required_evidence"] == []


def test_conflicted_hypothesis():
    result = evaluate_hypothesis(
        "Pipeline delay",
        ["Latest timestamp is 48 hours old"],
        ["Pipeline logs show a successful recent run"],
    )

    assert result["assessment"] == "conflicted"
    assert result["root_cause_confirmed"] is False


def test_inconclusive_hypothesis():
    result = evaluate_hypothesis("Pipeline delay", [], [])

    assert result["assessment"] == "inconclusive"
    assert result["root_cause_confirmed"] is False


def test_missing_required_evidence():
    result = evaluate_hypothesis(
        "Pipeline delay",
        ["Latest timestamp is 48 hours old"],
        [],
        ["Pipeline logs confirm a failed run"],
    )

    assert result["assessment"] == "insufficient_evidence"
    assert result["missing_required_evidence"] == [
        "Pipeline logs confirm a failed run"
    ]


def test_empty_hypothesis_name_is_rejected():
    with pytest.raises(ValueError):
        evaluate_hypothesis("", [], [])


def test_whitespace_hypothesis_name_is_rejected():
    with pytest.raises(ValueError):
        evaluate_hypothesis("   ", [], [])


def test_supporting_evidence_must_be_a_list():
    with pytest.raises(TypeError):
        evaluate_hypothesis(
            "Pipeline delay",
            "Latest timestamp is 48 hours old",
            [],
        )


def test_contradicting_evidence_must_be_a_list():
    with pytest.raises(TypeError):
        evaluate_hypothesis(
            "Pipeline delay",
            [],
            "Pipeline logs show a successful recent run",
        )


def test_empty_evidence_entries_are_rejected():
    with pytest.raises(ValueError):
        evaluate_hypothesis(
            "Pipeline delay",
            [""],
            [],
        )


def test_required_evidence_must_be_a_list():
    with pytest.raises(TypeError):
        evaluate_hypothesis(
            "Pipeline delay",
            [],
            [],
            "Pipeline logs confirm a failed run",
        )


def test_evidence_lists_are_not_modified():
    supporting = ["Latest timestamp is 48 hours old"]
    contradicting = []
    required = ["Latest timestamp is 48 hours old"]

    evaluate_hypothesis(
        "Pipeline delay",
        supporting,
        contradicting,
        required,
    )

    assert supporting == ["Latest timestamp is 48 hours old"]
    assert contradicting == []
    assert required == ["Latest timestamp is 48 hours old"]


def test_hypothesis_name_is_trimmed():
    result = evaluate_hypothesis(
        "  Pipeline delay  ",
        ["Old timestamp observed"],
        [],
    )

    assert result["hypothesis"] == "Pipeline delay"
