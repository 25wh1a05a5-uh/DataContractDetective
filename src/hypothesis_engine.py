
"""Evaluate root-cause hypotheses against explicit evidence."""

from typing import Any


def evaluate_hypothesis(
    name: str,
    supporting_evidence: list[str],
    contradicting_evidence: list[str],
    required_evidence: list[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Hypothesis name must be a non-empty string.")

    if not isinstance(supporting_evidence, list):
        raise TypeError("Supporting evidence must be a list.")

    if not isinstance(contradicting_evidence, list):
        raise TypeError("Contradicting evidence must be a list.")

    if required_evidence is None:
        required_evidence = []

    if not isinstance(required_evidence, list):
        raise TypeError("Required evidence must be a list.")

    evidence_lists = [
        supporting_evidence,
        contradicting_evidence,
        required_evidence,
    ]

    if any(
        not isinstance(item, str) or not item.strip()
        for evidence_list in evidence_lists
        for item in evidence_list
    ):
        raise ValueError("Evidence entries must be non-empty strings.")

    missing_required = [
        item for item in required_evidence
        if item not in supporting_evidence
    ]

    if not supporting_evidence:
        assessment = "inconclusive"
    elif contradicting_evidence:
        assessment = "conflicted"
    elif missing_required:
        assessment = "insufficient_evidence"
    else:
        assessment = "supported_by_available_evidence"

    return {
        "hypothesis": name.strip(),
        "assessment": assessment,
        "supporting_evidence": supporting_evidence.copy(),
        "contradicting_evidence": contradicting_evidence.copy(),
        "missing_required_evidence": missing_required,
        "root_cause_confirmed": False,
        "explanation": (
            "This assessment evaluates the supplied evidence only. "
            "It does not independently establish the actual root cause."
        ),
    }
