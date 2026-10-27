
"""Run a CSV investigation and save JSON, Markdown, and replay reports."""

import json
import sys
from pathlib import Path

from csv_loader import load_csv
from bedrock_summary import summarize_with_bedrock
from diagnostics import (
    check_duplicates,
    check_freshness,
    compare_schema,
    check_missing_values,
    check_numeric_range,
)
from decider import (
    choose_next_diagnostic_action,
    execute_selected_diagnostic,
)
from investigator import investigate_hypotheses
from replay_record import create_replay_record, save_replay_record


FRESHNESS_LIMIT_HOURS = 24

EXPECTED_SCHEMA = {
    "student_id": "int64",
    "date": "str",
    "updated_at": "str",
    "marks": "int64",
}

DUPLICATE_KEY_COLUMNS = ["student_id"]


def investigate_csv(file_path):
    loaded = load_csv(file_path)
    data = loaded["data"]

    duplicate_result = check_duplicates(data, DUPLICATE_KEY_COLUMNS)

    freshness_result = check_freshness(
        data,
        timestamp_column="updated_at",
        max_age_hours=FRESHNESS_LIMIT_HOURS,
    )

    schema_result = compare_schema(data, EXPECTED_SCHEMA)
    missing_result = check_missing_values(data)
    marks_result = check_numeric_range(
        data, "marks", minimum=0, maximum=100
    )

    diagnostics = {
        "duplicates": duplicate_result,
        "freshness": freshness_result,
        "schema": schema_result,
        "missing_values": missing_result,
        "marks_range": marks_result,
    }

    problem_conditions = {
        "duplicates": duplicate_result.get("duplicate_count", 0) > 0,
        "freshness": freshness_result.get("is_fresh") is False,
        "schema": schema_result.get("schema_matches") is False,
        "missing_values": (
            missing_result.get("missing_cell_count", 0) > 0
        ),
        "marks_range": marks_result.get("invalid_count", 0) > 0,
    }

    findings = []

    for check_name, result in diagnostics.items():
        if (
            result.get("status") == "completed"
            and problem_conditions[check_name]
        ):
            findings.append({
                "check": check_name,
                "evidence": result.get("evidence", ""),
            })

    evidence_ledger = []

    for check_name, result in diagnostics.items():
        details = {
            key: value
            for key, value in result.items()
            if key not in {"status", "evidence"}
        }

        evidence_ledger.append({
            "check": check_name,
            "status": result.get("status", "unknown"),
            "observation": result.get("evidence", ""),
            "details": details,
            "problem_detected": (
                problem_conditions[check_name]
                if result.get("status") == "completed"
                else None
            ),
        })

    decision = choose_next_diagnostic_action({"diagnostics": diagnostics})
    follow_up = execute_selected_diagnostic(data, decision)

    report = {
        "file_name": loaded["file_name"],
        "row_count": loaded["row_count"],
        "columns": loaded["columns"],
        "findings": findings,
        "diagnostics": diagnostics,
        "evidence_ledger": evidence_ledger,
        "next_diagnostic_action": decision,
        "follow_up_diagnostic": follow_up,
    }
    report["bedrock_summary"] = summarize_with_bedrock(report)
    return report


def build_hypotheses(csv_report):
    """Build hypothesis evidence from observed CSV diagnostics."""

    diagnostics = csv_report["diagnostics"]

    delivery_evidence = []
    delivery_contradictions = []

    if diagnostics["missing_values"].get("missing_cell_count", 0) > 0:
        delivery_evidence.append(
            "The CSV contains missing cell values."
        )

    if (
        diagnostics["schema"].get("missing_columns")
        or diagnostics["schema"].get("type_changes")
        or diagnostics["schema"].get("unexpected_columns")
    ):
        delivery_evidence.append(
            "The CSV does not match the expected schema."
        )

    if diagnostics["duplicates"].get("duplicate_count", 0) > 0:
        delivery_evidence.append(
            "Duplicate student records were detected."
        )

    if diagnostics["marks_range"].get("invalid_count", 0) > 0:
        delivery_evidence.append(
            "Marks outside the configured range were detected."
        )

    if not delivery_evidence:
        delivery_contradictions.append(
            "The configured checks found no missing values, "
            "duplicate records, schema mismatch, or invalid marks."
        )

    freshness_evidence = []
    freshness_contradictions = []

    freshness = diagnostics.get("freshness")

    if freshness and freshness.get("status") == "completed":
        if freshness.get("is_fresh") is False:
            freshness_evidence.append(
                freshness.get("evidence", "The data is stale.")
            )
        elif freshness.get("is_fresh") is True:
            freshness_contradictions.append(
                "The latest timestamp is within the configured "
                "freshness limit."
            )

    return [
        {
            "name": "Missing or invalid data delivery",
            "supporting_evidence": delivery_evidence,
            "contradicting_evidence": delivery_contradictions,
        },
        {
            "name": "Pipeline delay",
            "supporting_evidence": freshness_evidence,
            "contradicting_evidence": freshness_contradictions,
        },
    ]


def build_markdown_report(report):
    """Build a readable Markdown investigation report."""

    csv_report = report["csv_investigation"]

    lines = [
        "# DataContract Detective",
        "",
        "## CSV Investigation",
        "",
        f"**File:** {csv_report['file_name']}",
        "",
        f"**Rows inspected:** {csv_report['row_count']}",
        "",
        "**Columns:** " + ", ".join(csv_report["columns"]),
        "",
        "### Detected data-quality issues",
        "",
    ]

    if csv_report["findings"]:
        for finding in csv_report["findings"]:
            lines.append(
                f"- **{finding['check'].replace('_', ' ').title()}:** "
                f"{finding['evidence']}"
            )
    else:
        lines.append("- No configured data-quality issues detected.")

    action = csv_report.get("next_diagnostic_action", {})
    lines.extend([
        "",
        "### Adaptive follow-up decision",
        "",
    ])
    if action.get("tool_name"):
        lines.extend([
            f"- Selected tool: {action['tool_name']}",
            f"- Decision source: {action.get('source', 'unknown')}",
            "- Evidence basis: "
            f"{action.get('evidence_basis') or action.get('reason', 'Not provided.')}",
        ])
        if action.get("confidence") is not None:
            lines.append(f"- Decider confidence: {action['confidence']}")
        follow_up = csv_report.get("follow_up_diagnostic")
        if follow_up:
            result = follow_up.get("result", {})
            lines.append(
                f"- Follow-up execution: {follow_up.get('status', 'unknown')}"
            )
            lines.append(
                f"- Follow-up evidence: {result.get('evidence', 'Not available.')}"
            )
    else:
        lines.append(action.get("reason", "No follow-up action was selected."))

    bedrock = csv_report.get("bedrock_summary", {})
    if bedrock.get("status") == "completed":
        lines.extend([
            "",
            "### Amazon Bedrock summary",
            "",
            bedrock["text"],
        ])
    elif bedrock.get("status") == "failed":
        lines.extend([
            "",
            "### Amazon Bedrock summary",
            "",
            f"Summary unavailable: {bedrock.get('error', 'Unknown error.')}",
        ])

    diagnostics = csv_report["diagnostics"]
    freshness = diagnostics["freshness"]

    lines.extend([
        "",
        "### Diagnostic summary",
        "",
        f"- Missing cells: "
        f"{diagnostics['missing_values'].get('missing_cell_count', 0)}",
        f"- Invalid marks: "
        f"{diagnostics['marks_range'].get('invalid_count', 0)}",
        f"- Freshness status: {freshness.get('status', 'unknown')}",
        f"- Valid timestamps: "
        f"{freshness.get('valid_timestamp_count', 'Not available')}",
        f"- Invalid timestamps: "
        f"{freshness.get('invalid_timestamp_count', 'Not available')}",
    ])

    if freshness.get("status") == "completed":
        lines.extend([
            f"- Latest timestamp: {freshness['latest_timestamp']}",
            f"- Data age in hours: {freshness['age_hours']}",
            f"- Freshness limit in hours: {freshness['max_age_hours']}",
            f"- Data is fresh: {freshness['is_fresh']}",
        ])
    else:
        lines.append(
            f"- Freshness observation: "
            f"{freshness.get('evidence', 'Not verified.')}"
        )

    lines.extend([
        "",
        "## Evidence Ledger",
        "",
        "| Check | Status | Observation | Problem detected |",
        "|---|---|---|---|",
    ])

    for entry in csv_report["evidence_ledger"]:
        observation = entry["observation"].replace("|", "\\|")
        problem = entry["problem_detected"]
        lines.append(
            f"| {entry['check']} | {entry['status']} | "
            f"{observation} | {problem} |"
        )

    lines.extend([
        "",
        "## Hypothesis Assessments",
        "",
        f"**Conclusion:** {report['conclusion']}",
        "",
        f"**Root cause confirmed:** {report['root_cause_confirmed']}",
        "",
    ])

    for index, hypothesis in enumerate(report["hypotheses"], start=1):
        lines.extend([
            f"### {index}. {hypothesis['hypothesis']}",
            "",
            f"**Assessment:** "
            f"{hypothesis['assessment'].replace('_', ' ').title()}",
            "",
            "**Supporting evidence**",
        ])

        lines.extend(
            [f"- {item}" for item in hypothesis["supporting_evidence"]]
            or ["- No supporting evidence recorded."]
        )

        lines.extend(["", "**Contradicting evidence**"])

        lines.extend(
            [f"- {item}" for item in hypothesis["contradicting_evidence"]]
            or ["- No contradicting evidence recorded."]
        )

        lines.extend(["", "**Missing required evidence**"])

        lines.extend(
            [
                f"- {item}"
                for item in hypothesis["missing_required_evidence"]
            ]
            or ["- No missing required evidence recorded."]
        )

        lines.extend([
            "",
            f"**Root cause confirmed:** "
            f"{hypothesis['root_cause_confirmed']}",
            "",
            hypothesis["explanation"],
            "",
        ])

    replay = report.get("replay_record")

    if replay:
        lines.extend([
            "## Replay Record",
            "",
            f"- Investigation ID: `{replay['investigation_id']}`",
            f"- Input SHA-256: `{replay['input_sha256']}`",
            f"- Replay metadata: `{report.get('replay_record_file', 'Not saved')}`",
            "",
        ])

    lines.extend([
        "## Limitations",
        "",
        "- Findings describe observed data-quality conditions.",
        "- Freshness is evaluated using the latest valid updated_at "
        "timestamp and the configured 24-hour limit.",
        "- Invalid timestamps are counted and excluded from the "
        "freshness calculation.",
        "- A stale timestamp is evidence of old data, not proof of "
        "the underlying cause.",
        "- The input fingerprint identifies file contents; it does "
        "not guarantee identical results across code or environment versions.",
        "- Further pipeline logs or source-system evidence may be "
        "required to confirm a root cause.",
        "",
    ])

    return "\n".join(lines)


def main():
    project_dir = Path(__file__).resolve().parent.parent

    if len(sys.argv) > 1:
        csv_path = Path(sys.argv[1])
        if not csv_path.is_absolute():
            csv_path = Path.cwd() / csv_path
    else:
        csv_path = project_dir / "data" / "sample_data.csv"

    try:
        csv_path = csv_path.resolve()

        csv_report = investigate_csv(csv_path)
        hypotheses = build_hypotheses(csv_report)

        report = {
            **investigate_hypotheses(hypotheses),
            "csv_investigation": csv_report,
        }

        reports_dir = project_dir / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        output_name = Path(csv_report["file_name"]).stem

        json_path = reports_dir / f"{output_name}_investigation.json"
        markdown_path = reports_dir / f"{output_name}_investigation.md"
        replay_path = reports_dir / f"{output_name}_replay.json"

        configuration = {
            "freshness_limit_hours": FRESHNESS_LIMIT_HOURS,
            "duplicate_key_columns": DUPLICATE_KEY_COLUMNS,
            "expected_schema": EXPECTED_SCHEMA,
            "marks_range": {
                "column": "marks",
                "minimum": 0,
                "maximum": 100,
            },
        }

        replay_record = create_replay_record(
            file_path=csv_path,
            configuration=configuration,
            checks_performed=list(csv_report["diagnostics"].keys()),
        )

        save_replay_record(replay_record, replay_path)

        report["replay_record"] = replay_record
        report["replay_record_file"] = str(replay_path)

        json_path.write_text(
            json.dumps(report, indent=2, default=str),
            encoding="utf-8",
        )

        markdown_path.write_text(
            build_markdown_report(report),
            encoding="utf-8",
        )

        diagnostics = csv_report["diagnostics"]
        freshness = diagnostics["freshness"]

        print("Investigation completed.")
        print(f"JSON report: {json_path}")
        print(f"Markdown report: {markdown_path}")
        print(f"Replay record: {replay_path}")
        print(f"Investigation ID: {replay_record['investigation_id']}")
        print(f"Input SHA-256: {replay_record['input_sha256']}")
        print(f"CSV file inspected: {csv_report['file_name']}")
        print(f"Rows inspected: {csv_report['row_count']}")
        print(
            f"Data-quality issues detected: {len(csv_report['findings'])}"
        )
        print(
            "Missing cells: "
            f"{diagnostics['missing_values'].get('missing_cell_count', 0)}"
        )
        print(
            "Invalid marks: "
            f"{diagnostics['marks_range'].get('invalid_count', 0)}"
        )
        print(
            "Schema matches expectations: "
            f"{diagnostics['schema'].get('schema_matches')}"
        )
        print(f"Freshness status: {freshness.get('status')}")
        print(
            "Valid timestamps: "
            f"{freshness.get('valid_timestamp_count', 'Not available')}"
        )
        print(
            "Invalid timestamps: "
            f"{freshness.get('invalid_timestamp_count', 'Not available')}"
        )

        if freshness.get("status") == "completed":
            print(f"Data age in hours: {freshness['age_hours']}")
            print(f"Data is fresh: {freshness['is_fresh']}")
        else:
            print(
                f"Freshness observation: {freshness.get('evidence')}"
            )

        print(f"Conclusion: {report['conclusion']}")
        print(f"Root cause confirmed: {report['root_cause_confirmed']}")

    except (
        FileNotFoundError,
        ValueError,
        TypeError,
        OSError,
        RuntimeError,
    ) as error:
        print(f"Investigation failed: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
