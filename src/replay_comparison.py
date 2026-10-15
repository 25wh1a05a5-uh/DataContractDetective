
"""Compare original investigation diagnostics with replay results."""

import json
import sys
from pathlib import Path


DIAGNOSTIC_NAMES = (
    "duplicates",
    "freshness",
    "schema",
    "missing_values",
    "marks_range",
)


def read_json_object(path):
    """Load a JSON file and require a JSON object."""

    path = Path(path)

    if not path.is_file():
        raise FileNotFoundError(f"Report not found: {path}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON in report: {path}") from error

    if not isinstance(data, dict):
        raise ValueError(f"Report must contain a JSON object: {path}")

    return data


def get_diagnostics(report, is_replay):
    """Return the diagnostics section from either report format."""

    if is_replay:
        diagnostics = report.get("diagnostics")
    else:
        investigation = report.get("csv_investigation", {})
        diagnostics = (
            investigation.get("diagnostics")
            if isinstance(investigation, dict)
            else None
        )

    if not isinstance(diagnostics, dict):
        raise ValueError("Report does not contain a valid diagnostics object.")

    missing = set(DIAGNOSTIC_NAMES) - set(diagnostics)

    if missing:
        raise ValueError(
            "Report is missing diagnostics: "
            + ", ".join(sorted(missing))
        )

    return diagnostics


def compare_diagnostics(original_report, replay_report):
    """Compare key diagnostic results and flag changed values."""

    original = get_diagnostics(original_report, is_replay=False)
    replay = get_diagnostics(replay_report, is_replay=True)

    comparisons = {}

    for name in DIAGNOSTIC_NAMES:
        original_result = original[name]
        replay_result = replay[name]

        if not isinstance(original_result, dict):
            raise ValueError(f"Original '{name}' diagnostic must be an object.")

        if not isinstance(replay_result, dict):
            raise ValueError(f"Replay '{name}' diagnostic must be an object.")

        # Evidence wording and timestamps may change. Compare structured
        # result fields while excluding descriptive evidence and time values.
        ignored_fields = {
            "evidence",
            "latest_timestamp",
            "age_hours",
        }

        fields = sorted(
            (set(original_result) | set(replay_result)) - ignored_fields
        )

        field_changes = {}

        for field in fields:
            before = original_result.get(field)
            after = replay_result.get(field)

            if before != after:
                field_changes[field] = {
                    "original": before,
                    "replay": after,
                }

        freshness_time_sensitive = (
            name == "freshness"
            and (
                original_result.get("age_hours")
                != replay_result.get("age_hours")
                or original_result.get("latest_timestamp")
                != replay_result.get("latest_timestamp")
            )
        )

        comparisons[name] = {
            "status": "changed" if field_changes else "unchanged",
            "changed_fields": field_changes,
            "time_sensitive_values_changed": freshness_time_sensitive,
        }

    changed_count = sum(
        result["status"] == "changed"
        for result in comparisons.values()
    )

    return {
        "original_investigation_id": (
            original_report.get("replay_record", {}).get("investigation_id")
        ),
        "replay_of_investigation_id": (
            replay_report.get("replay_of_investigation_id")
        ),
        "input_matches_original": replay_report.get(
            "input_matches_original"
        ),
        "diagnostics": comparisons,
        "summary": {
            "checks_compared": len(comparisons),
            "checks_changed": changed_count,
            "checks_unchanged": len(comparisons) - changed_count,
        },
        "comparison_note": (
            "Freshness age and timestamp can change with time. "
            "A changed field indicates a difference between the saved "
            "results, not by itself a confirmed root cause."
        ),
    }


def main():
    if len(sys.argv) != 3:
        print(
            "Usage: python -m src.replay_comparison "
            "<original_investigation.json> <replay_run.json>"
        )
        sys.exit(2)

    try:
        original_report = read_json_object(sys.argv[1])
        replay_report = read_json_object(sys.argv[2])

        result = compare_diagnostics(original_report, replay_report)

        output_dir = Path(__file__).resolve().parent.parent / "reports"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "replay_comparison.json"

        output_path.write_text(
            json.dumps(result, indent=2, default=str),
            encoding="utf-8",
        )

        print("Replay comparison completed.")
        print(f"Checks compared: {result['summary']['checks_compared']}")
        print(f"Checks changed: {result['summary']['checks_changed']}")
        print(f"Checks unchanged: {result['summary']['checks_unchanged']}")
        print(f"Comparison report: {output_path}")

        for name, comparison in result["diagnostics"].items():
            print(f"{name}: {comparison['status']}")

    except (FileNotFoundError, ValueError, OSError) as error:
        print(f"Comparison failed: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
