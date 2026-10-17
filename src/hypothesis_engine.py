
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

    if assessment == "inconclusive":
        explanation = (
            "No supporting evidence was supplied, so this hypothesis "
            "cannot yet be assessed."
        )
    elif assessment == "conflicted":
        explanation = (
            "Supporting evidence exists, but contradictory evidence "
            "prevents a consistent assessment."
        )
    elif assessment == "insufficient_evidence":
        explanation = (
            "Supporting evidence exists, but one or more required "
            "evidence items are missing."
        )
    else:
        explanation = (
            "The supplied evidence supports this hypothesis, but it "
            "does not independently confirm the actual root cause."
        )

    return {
        "hypothesis": name.strip(),
        "assessment": assessment,
        "supporting_evidence": supporting_evidence.copy(),
        "contradicting_evidence": contradicting_evidence.copy(),
        "missing_required_evidence": missing_required,
        "root_cause_confirmed": False,
        "explanation": explanation,
    }


def generate_hypotheses(diagnostics: dict[str, Any]) -> list[dict[str, Any]]:
    """Generate cautious hypotheses from completed diagnostic results."""

    hypotheses = []

    freshness = diagnostics.get("freshness", {})
    if freshness.get("status") == "completed":
        if freshness.get("is_fresh") is False:
            hypotheses.append({
                "name": "Stale data",
                "supporting_evidence": [
                    freshness.get(
                        "evidence",
                        "The latest data exceeds the freshness threshold.",
                    )
                ],
                "contradicting_evidence": [],
                "required_evidence": [
                    "Pipeline run logs or source-system timestamps "
                    "to investigate the underlying cause"
                ],
            })

    duplicates = diagnostics.get("duplicates", {})
    if duplicates.get("status") == "completed":
        if duplicates.get("duplicate_count", 0) > 0:
            hypotheses.append({
                "name": "Duplicate records in the dataset",
                "supporting_evidence": [
                    duplicates.get(
                        "evidence",
                        "Duplicate records were detected.",
                    )
                ],
                "contradicting_evidence": [],
                "required_evidence": [],
            })

    schema = diagnostics.get("schema", {})
    if schema.get("status") == "completed":
        if schema.get("schema_matches") is False:
            hypotheses.append({
                "name": "Schema contract violation",
                "supporting_evidence": [
                    schema.get(
                        "evidence",
                        "The observed schema differs from the expected schema.",
                    )
                ],
                "contradicting_evidence": [],
                "required_evidence": [],
            })

    return hypotheses

