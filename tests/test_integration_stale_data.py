
"""Integration test for stale-data investigation."""

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from run_investigation import (
    investigate_csv,
    build_hypotheses,
    build_markdown_report,
)
from investigator import investigate_hypotheses


def test_stale_data_flows_through_full_investigation(tmp_path):
    # Arrange: create a CSV with timestamps well beyond 24 hours old.
    csv_path = tmp_path / "stale_integration.csv"

    data = pd.DataFrame({
        "student_id": [1, 2],
        "date": ["2020-01-01", "2020-01-01"],
        "updated_at": [
            "2020-01-01T10:00:00Z",
            "2020-01-01T10:00:00Z",
        ],
        "marks": [85, 90],
    })

    data.to_csv(csv_path, index=False)

    # Act: run the CSV diagnostics.
    csv_report = investigate_csv(csv_path)

    # Check that freshness detects stale data.
    freshness = csv_report["diagnostics"]["freshness"]

    assert freshness["status"] == "completed"
    assert freshness["is_fresh"] is False
    assert freshness["age_hours"] > 24

    # Check that the Evidence Ledger records the stale-data finding.
    ledger_entry = next(
        entry
        for entry in csv_report["evidence_ledger"]
        if entry["check"] == "freshness"
    )

    assert ledger_entry["status"] == "completed"
    assert ledger_entry["problem_detected"] is True
    assert "exceeds the freshness limit" in (
        ledger_entry["observation"].lower()
    )

    # Evaluate the hypotheses using the diagnostic evidence.
    hypotheses = build_hypotheses(csv_report)
    report = investigate_hypotheses(hypotheses)

    # Check that Pipeline delay is supported by the evidence.
    pipeline_delay = next(
        hypothesis
        for hypothesis in report["hypotheses"]
        if hypothesis["hypothesis"] == "Pipeline delay"
    )

    assert (
        pipeline_delay["assessment"]
        == "supported_by_available_evidence"
    )
    assert any(
        "freshness limit" in evidence.lower()
        for evidence in pipeline_delay["supporting_evidence"]
    )

    # Stale data alone must not confirm the underlying root cause.
    assert pipeline_delay["root_cause_confirmed"] is False
    assert report["root_cause_confirmed"] is False

    # Check that the generated Markdown includes the findings.
    complete_report = {
        **report,
        "csv_investigation": csv_report,
    }

    markdown = build_markdown_report(complete_report)

    assert "Evidence Ledger" in markdown
    assert "Data exceeds the freshness limit." in markdown
    assert "Pipeline delay" in markdown
    assert "**Root cause confirmed:** False" in markdown
