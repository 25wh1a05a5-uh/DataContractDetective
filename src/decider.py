
"""Choose and execute an evidence-driven follow-up diagnostic."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

TOOL_DESCRIPTIONS = {
    "missing_values": "Recheck missing cells and report the affected columns.",
    "marks_range": "Recheck marks outside the configured inclusive 0–100 range.",
    "schema": "Recheck missing, unexpected, or incorrectly typed columns.",
    "freshness": "Recheck whether the latest updated_at value exceeds 24 hours.",
    "duplicates": "Recheck repeated student_id records.",
}

NEXT_TOOL_INSTRUCTIONS = (
    "Choose the single most useful diagnostic to rerun next. "
    "Prioritize a concrete anomaly already supported by the evidence. "
    "If there is no anomaly, choose a check that best validates the dataset."
)


def _diagnostics_from_report(report: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {}

    diagnostics = report.get("diagnostics")
    if isinstance(diagnostics, dict):
        return diagnostics

    csv_investigation = report.get("csv_investigation")
    if isinstance(csv_investigation, dict):
        nested = csv_investigation.get("diagnostics")
        return nested if isinstance(nested, dict) else {}

    return {}


def build_evidence_state(diagnostics: dict[str, Any]) -> dict[str, Any]:
    """Build compact, row-free evidence for the Decider service."""
    state: dict[str, Any] = {}
    count_fields = {
        "duplicates": "duplicate_count",
        "missing_values": "missing_cell_count",
        "marks_range": "invalid_count",
    }

    for name in TOOL_DESCRIPTIONS:
        result = diagnostics.get(name, {})
        if not isinstance(result, dict):
            continue

        item: dict[str, Any] = {"status": result.get("status", "unknown")}

        if name in count_fields:
            field = count_fields[name]
            if field in result:
                item[field] = result[field]
        elif name == "freshness":
            for field in ("is_fresh", "age_hours", "max_age_hours"):
                if field in result:
                    item[field] = result[field]
        elif name == "schema":
            item["schema_matches"] = result.get("schema_matches")
            item["missing_columns"] = result.get("missing_columns", [])
            item["unexpected_columns"] = result.get("unexpected_columns", [])
            item["type_changes"] = result.get("type_changes", {})

        item["evidence"] = result.get("evidence", "")
        state[name] = item

    return state


def _count(result: dict[str, Any], field: str) -> int:
    try:
        return max(0, int(result.get(field, 0) or 0))
    except (TypeError, ValueError):
        return 0


def _priority(name: str, result: dict[str, Any]) -> tuple[float, str]:
    if name == "missing_values":
        count = _count(result, "missing_cell_count")
        if count:
            return min(0.95, 0.7 + count / 20), (
                f"{count} missing cell(s) were detected."
            )

    elif name == "marks_range":
        count = _count(result, "invalid_count")
        if count:
            return min(0.98, 0.76 + count / 20), (
                f"{count} out-of-range mark(s) were detected."
            )

    elif name == "schema" and result.get("schema_matches") is False:
        return 0.84, "The observed columns or data types differ from the contract."

    elif name == "freshness" and result.get("is_fresh") is False:
        return 0.82, "The latest data exceeds the configured freshness limit."

    elif name == "duplicates":
        count = _count(result, "duplicate_count")
        if count:
            return min(0.9, 0.68 + count / 20), (
                f"{count} duplicate row(s) were detected."
            )

    return 0.05, "No issue was detected by this diagnostic."


def _eligible_tools(
    diagnostics: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    return {
        name: result
        for name, result in diagnostics.items()
        if name in TOOL_DESCRIPTIONS
        and isinstance(result, dict)
        and result.get("status") == "completed"
    }


def _rule_based_decision(
    eligible: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if not eligible:
        return {
            "status": "no_actionable_diagnostics",
            "source": "rule_based_fallback",
            "tool_name": None,
            "tool_label": None,
            "reason": "No completed diagnostic is available to select.",
            "confidence": None,
            "alternatives": [],
        }

    ranked = sorted(
        (
            {
                "tool_name": name,
                "priority_score": _priority(name, result)[0],
                "reason": _priority(name, result)[1],
            }
            for name, result in eligible.items()
        ),
        key=lambda item: item["priority_score"],
        reverse=True,
    )

    selected = ranked[0]
    return {
        "status": "completed",
        "source": "rule_based_fallback",
        "tool_name": selected["tool_name"],
        "tool_label": selected["tool_name"].replace("_", " ").title(),
        "reason": selected["reason"],
        "confidence": None,
        "priority_score": round(selected["priority_score"], 3),
        "alternatives": ranked[1:4],
    }


def choose_next_diagnostic_action(
    report: dict[str, Any] | None,
) -> dict[str, Any]:
    """Choose a follow-up diagnostic using Strands Decider or a local fallback."""
    diagnostics = _diagnostics_from_report(report)
    eligible = _eligible_tools(diagnostics)
    endpoint = os.getenv("STRANDS_DECIDER_URL", "").strip()

    if not endpoint or len(eligible) < 2:
        decision = _rule_based_decision(eligible)
        if endpoint and len(eligible) < 2:
            decision["fallback_reason"] = (
                "The Decider choice API requires at least two available options."
            )
        return decision

    criteria = {
        name: TOOL_DESCRIPTIONS[name]
        for name in eligible
    }

    payload: dict[str, Any] = {
        "state": json.dumps(build_evidence_state(diagnostics), sort_keys=True),
        "questions": {
            "next_tool": {
                "type": "choice",
                "instructions": NEXT_TOOL_INSTRUCTIONS,
                "criteria": criteria,
            }
        },
    }

    model_name = os.getenv("STRANDS_DECIDER_MODEL")
    if model_name:
        payload["model"] = model_name

    parsed_endpoint = urlsplit(endpoint)
    if parsed_endpoint.scheme not in {"http", "https"} or not parsed_endpoint.netloc:
        raise ValueError(
            "STRANDS_DECIDER_URL must be an absolute HTTP or HTTPS URL."
        )

    request = Request(
        f"{endpoint.rstrip('/')}/v1/systemone",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=120) as response:
            response_body = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Strands Decider returned HTTP {exc.code}: {detail}"
        ) from exc
    except URLError as exc:
        raise RuntimeError(
            f"Could not connect to Strands Decider at {endpoint}: {exc.reason}"
        ) from exc
    except (TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Invalid or timed-out Strands Decider response: {exc}"
        ) from exc

    if not isinstance(response_body, dict):
        raise RuntimeError("Strands Decider response must be a JSON object.")

    model = response_body.get("model")
    if not isinstance(model, str) or "2b" not in model.lower():
        raise RuntimeError(
            "The configured Strands service did not identify a Decider 2B model."
        )

    answers = response_body.get("answers")
    if not isinstance(answers, dict):
        raise RuntimeError("Strands Decider response is missing its answers.")

    answer = answers.get("next_tool")
    if not isinstance(answer, dict):
        raise RuntimeError("Strands Decider response is missing next_tool.")

    selected = answer.get("choice")
    if answer.get("type") != "choice" or selected not in eligible:
        raise RuntimeError(
            "Strands Decider returned an invalid next_tool choice."
        )

    confidence = answer.get("confidence")
    probabilities = answer.get("probabilities", {})

    if (
        not isinstance(confidence, (int, float))
        or isinstance(confidence, bool)
        or not 0 <= confidence <= 1
        or not isinstance(probabilities, dict)
        or any(
            name not in eligible
            or not isinstance(probability, (int, float))
            or isinstance(probability, bool)
            or not 0 <= probability <= 1
            for name, probability in probabilities.items()
        )
        or selected not in probabilities
    ):
        raise RuntimeError("Strands Decider returned invalid confidence data.")

    return {
        "status": "completed",
        "source": "strands_decider_2b",
        "model": model,
        "tool_name": selected,
        "tool_label": selected.replace("_", " ").title(),
        "evidence_basis": _priority(selected, eligible[selected])[1],
        "confidence": round(float(confidence), 4),
        "probabilities": probabilities,
        "alternatives": [
            {"tool_name": name, "probability": probability}
            for name, probability in probabilities.items()
            if name != selected
        ],
    }


def execute_selected_diagnostic(
    data: Any,
    decision: dict[str, Any],
) -> dict[str, Any] | None:
    """Run the diagnostic selected by the decision."""
    tool_name = decision.get("tool_name")
    if tool_name is None:
        return None

    from diagnostics import (
        check_duplicates,
        check_freshness,
        check_missing_values,
        check_numeric_range,
        compare_schema,
    )
    from run_investigation import (
        DUPLICATE_KEY_COLUMNS,
        EXPECTED_SCHEMA,
        FRESHNESS_LIMIT_HOURS,
    )

    runners = {
        "duplicates": lambda: check_duplicates(data, DUPLICATE_KEY_COLUMNS),
        "freshness": lambda: check_freshness(
            data, "updated_at", FRESHNESS_LIMIT_HOURS
        ),
        "schema": lambda: compare_schema(data, EXPECTED_SCHEMA),
        "missing_values": lambda: check_missing_values(data),
        "marks_range": lambda: check_numeric_range(
            data, "marks", minimum=0, maximum=100
        ),
    }

    if tool_name not in runners:
        raise ValueError(f"Unsupported follow-up diagnostic: {tool_name}")

    return {
        "tool_name": tool_name,
        "status": "executed",
        "result": runners[tool_name](),
    }
