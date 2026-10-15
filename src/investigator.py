
"""Coordinate diagnostics and build an evidence-based investigation report."""

from diagnostics import (
    check_duplicates,
    check_freshness,
    compare_schema,
)


def investigate(
    data,
    key_columns,
    timestamp_column,
    max_age_hours,
    expected_schema,
    now=None,
):
    """Run diagnostic checks and summarize their evidence.

    Findings describe observed data-quality problems. They do not
    automatically prove the underlying business root cause.
    """

    diagnostics = {
        "duplicates": check_duplicates(data, key_columns),
        "freshness": check_freshness(
            data, timestamp_column, max_age_hours, now=now
        ),
        "schema": compare_schema(data, expected_schema),
    }

    evidence_ledger = []
    findings = []

    def record_evidence(check_name, result, problem_detected):
        entry = {
            "check": check_name,
            "status": result.get("status", "unknown"),
            "observation": result.get("evidence", ""),
            "details": {
                key: value
                for key, value in result.items()
                if key not in {"status", "evidence"}
            },
            "problem_detected": problem_detected,
        }
        evidence_ledger.append(entry)

        if result.get("status") != "completed":
            return

        if problem_detected:
            findings.append({
                "finding": check_name,
                "evidence": result.get("evidence", ""),
                "details": entry["details"],
            })

    duplicate_result = diagnostics["duplicates"]
    record_evidence(
        "duplicates",
        duplicate_result,
        duplicate_result.get("duplicate_count", 0) > 0,
    )

    freshness_result = diagnostics["freshness"]
    record_evidence(
        "freshness",
        freshness_result,
        freshness_result.get("is_fresh") is False,
    )

    schema_result = diagnostics["schema"]
    record_evidence(
        "schema",
        schema_result,
        schema_result.get("schema_matches") is False,
    )

    incomplete_checks = [
        name
        for name, result in diagnostics.items()
        if result.get("status") != "completed"
    ]

    if incomplete_checks:
        conclusion = "inconclusive"
    elif findings:
        conclusion = "data_quality_issues_detected"
    else:
        conclusion = "no_configured_issues_detected"

    return {
        "status": "completed" if not incomplete_checks else "partial",
        "conclusion": conclusion,
        "findings": findings,
        "evidence_ledger": evidence_ledger,
        "incomplete_checks": incomplete_checks,
        "diagnostics": diagnostics,
        "limitations": [
            "Detected data-quality issues do not by themselves prove "
            "their underlying business root cause.",
            "Only the configured checks and supplied schema were evaluated.",
        ],
    }


def investigate_hypotheses(hypotheses):
    """Evaluate multiple hypotheses and preserve uncertainty."""

    from hypothesis_engine import evaluate_hypothesis

    results = []

    for hypothesis in hypotheses:
        result = evaluate_hypothesis(
            name=hypothesis["name"],
            supporting_evidence=hypothesis.get(
                "supporting_evidence", []
            ),
            contradicting_evidence=hypothesis.get(
                "contradicting_evidence", []
            ),
            required_evidence=hypothesis.get(
                "required_evidence", []
            ),
        )
        results.append(result)

    return {
        "hypotheses": results,
        "root_cause_confirmed": False,
        "conclusion": (
            "Hypotheses evaluated; no root cause is confirmed "
            "by this assessment alone."
        ),
    }
