
import pytest

from hypothesis_engine import evaluate_hypothesis
from hypothesis_engine import generate_hypotheses

def test_hypothesis_supported_by_evidence():
    result = evaluate_hypothesis(
        "Pipeline delay",
        ["Latest timestamp is 48 hours old"],
        [],
        ["Latest timestamp is 48 hours old"],
    )

    assert result["assessment"] == "supported_by_available_evidence"
    assert result["root_cause_confirmed"] is False


def test_hypothesis_with_conflicting_evidence():
    result = evaluate_hypothesis(
        "Pipeline delay",
        ["Latest timestamp is 48 hours old"],
        ["Pipeline logs show a successful recent run"],
    )

    assert result["assessment"] == "conflicted"
    assert result["root_cause_confirmed"] is False


def test_hypothesis_without_evidence_is_inconclusive():
    result = evaluate_hypothesis(
        "Pipeline delay",
        [],
        [],
    )

    assert result["assessment"] == "inconclusive"
    assert result["root_cause_confirmed"] is False


def test_missing_required_evidence_is_reported():
    result = evaluate_hypothesis(
        "Pipeline delay",
        ["Latest timestamp is 48 hours old"],
        [],
        ["Pipeline run logs confirm a failed run"],
    )

    assert result["assessment"] == "insufficient_evidence"
    assert result["missing_required_evidence"] == [
        "Pipeline run logs confirm a failed run"
    ]


def test_empty_hypothesis_name_is_rejected():
    with pytest.raises(ValueError):
        evaluate_hypothesis("", [], [])


def test_generate_hypotheses_detects_stale_data():
    from hypothesis_engine import generate_hypotheses

    diagnostics = {
        "freshness": {
            "status": "completed",
            "is_fresh": False,
            "evidence": "Data is 33.83 hours old.",
        },
        "duplicates": {
            "status": "completed",
            "duplicate_count": 0,
        },
        "schema": {
            "status": "completed",
            "schema_matches": True,
        },
    }

    hypotheses = generate_hypotheses(diagnostics)

    assert len(hypotheses) == 1
    assert hypotheses[0]["name"] == "Stale data"
    assert hypotheses[0]["supporting_evidence"] == [
        "Data is 33.83 hours old."
    ]


def test_generate_hypotheses_ignores_incomplete_checks():
    from hypothesis_engine import generate_hypotheses

    diagnostics = {
        "freshness": {
            "status": "partial",
            "is_fresh": False,
            "evidence": "Incomplete freshness check.",
        }
    }

    assert generate_hypotheses(diagnostics) == []


def test_stale_data_hypothesis_requires_additional_evidence():
    diagnostics = {
        "freshness": {
            "status": "completed",
            "is_fresh": False,
            "evidence": "Data exceeds the freshness threshold.",
        }
    }

    hypotheses = generate_hypotheses(diagnostics)

    stale = next(
        hypothesis
        for hypothesis in hypotheses
        if hypothesis["name"] == "Stale data"
    )

    assert stale["supporting_evidence"] == [
        "Data exceeds the freshness threshold."
    ]
    assert stale["required_evidence"]
    assert stale["contradicting_evidence"] == []


def test_hypothesis_remains_unconfirmed_when_evidence_conflicts():
    result = evaluate_hypothesis(
        name="Stale data",
        supporting_evidence=["The data exceeds the freshness threshold."],
        contradicting_evidence=["Source logs show a recent successful update."],
        required_evidence=["Pipeline run logs"],
    )

    assert result["assessment"] == "conflicted"
    assert result["root_cause_confirmed"] is False
    assert "Pipeline run logs" in result["missing_required_evidence"]


def test_missing_supporting_evidence_remains_inconclusive():
    result = evaluate_hypothesis(
        name="Pipeline delay",
        supporting_evidence=[],
        contradicting_evidence=[],
        required_evidence=["Pipeline run logs"],
    )

    assert result["assessment"] == "inconclusive"
    assert result["missing_required_evidence"] == ["Pipeline run logs"]
    assert result["root_cause_confirmed"] is False



def test_conflicted_hypothesis_explains_why_it_is_unresolved():
    result = evaluate_hypothesis(
        name="Pipeline delay",
        supporting_evidence=["The latest data is old."],
        contradicting_evidence=["Logs show a recent successful update."],
    )

    assert result["assessment"] == "conflicted"
    assert result["explanation"]
    assert result["root_cause_confirmed"] is False


def test_inconclusive_explanation():
    result = evaluate_hypothesis("Pipeline delay", [], [])

    assert result["assessment"] == "inconclusive"
    assert "No supporting evidence" in result["explanation"]


def test_conflicted_explanation():
    result = evaluate_hypothesis(
        "Pipeline delay",
        ["Data is old."],
        ["A recent update was recorded."],
    )

    assert result["assessment"] == "conflicted"
    assert "contradictory evidence" in result["explanation"]


def test_insufficient_evidence_explanation():
    result = evaluate_hypothesis(
        "Pipeline delay",
        ["Data is old."],
        [],
        ["Pipeline run logs"],
    )

    assert result["assessment"] == "insufficient_evidence"
    assert "required evidence items are missing" in result["explanation"]


def test_supported_explanation_does_not_confirm_root_cause():
    result = evaluate_hypothesis(
        "Duplicate records",
        ["Duplicate records were detected."],
        [],
    )

    assert result["assessment"] == "supported_by_available_evidence"
    assert "does not independently confirm" in result["explanation"]
    assert result["root_cause_confirmed"] is False
