import io
import json
import os
import re
import sys
import tempfile
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import pandas as pd
import streamlit as st

PROJECT_DIR = Path(__file__).resolve().parent
SRC_DIR = PROJECT_DIR / "src"
DATA_DIR = PROJECT_DIR / "data"
REPORTS_DIR = PROJECT_DIR / "reports"

sys.path.insert(0, str(SRC_DIR))

import run_investigation as engine
from decider import (
    NEXT_TOOL_INSTRUCTIONS,
    TOOL_DESCRIPTIONS,
    build_evidence_state,
)
from replay_comparison import compare_diagnostics
from replay_record import create_replay_record, save_replay_record
from replay_runner import rerun_investigation


st.set_page_config(
    page_title="DataContract Detective",
    page_icon="D",
    layout="wide",
)

st.markdown(
    """
    <style>
    :root {
        color-scheme: dark;
        --canvas: #0b1220;
        --panel: #111c2d;
        --panel-raised: #162438;
        --line: #27374d;
        --text: #e6edf6;
        --muted: #9aabc0;
        --teal: #47d7c5;
        --blue: #68a9ff;
        --amber: #f4bd62;
        --red: #ff7b78;
    }
    .stApp {
        background: var(--canvas);
        color: var(--text);
    }
    [data-testid="stHeader"] {
        background: rgba(11, 18, 32, 0.96);
    }
    [data-testid="stSidebar"] {
        background: #0e1929;
        border-right: 1px solid var(--line);
    }
    .brand-lockup {
        display: flex;
        align-items: center;
        gap: 11px;
        margin: 4px 0 20px;
    }
    .brand-mark {
        display: grid;
        width: 38px;
        height: 38px;
        place-items: center;
        border: 1px solid #356677;
        border-radius: 10px;
        background: #102b3a;
        color: var(--teal);
        font-size: 13px;
        font-weight: 800;
        letter-spacing: 0.04em;
    }
    .brand-name {
        color: var(--text);
        font-size: 15px;
        font-weight: 700;
        line-height: 1.15;
    }
    .brand-kicker {
        color: var(--muted);
        font-size: 10px;
        letter-spacing: 0.16em;
    }
    h1, h2, h3 {
        color: var(--text);
        letter-spacing: -0.025em;
    }
    [data-testid="stMetric"] {
        background: var(--panel);
        border: 1px solid var(--line);
        border-radius: 10px;
        padding: 14px 16px;
    }
    [data-testid="stMetricLabel"] p,
    [data-testid="stCaptionContainer"] {
        color: var(--muted);
    }
    [data-testid="stExpander"],
    [data-testid="stFileUploader"],
    [data-testid="stDataFrame"] {
        border-color: var(--line);
    }
    div.stButton > button[kind="primary"] {
        background: var(--teal);
        border: 1px solid var(--teal);
        color: #07131a;
        font-weight: 700;
        border-radius: 8px;
    }
    div.stButton > button {
        border-radius: 8px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


CHECK_LABELS = {
    "duplicates": "Duplicate records",
    "freshness": "Data freshness",
    "schema": "Schema contract",
    "missing_values": "Missing values",
    "marks_range": "Marks range",
}

NAV_ITEMS = [
    "Overview",
    "Investigate",
    "Evidence Ledger",
    "Hypotheses",
    "Replay Verification",
    "Replay Comparison",
    "Configuration",
]


def read_decider_health() -> tuple[str, str]:
    endpoint = os.getenv("STRANDS_DECIDER_URL", "").strip()
    if not endpoint:
        return "Unavailable", "STRANDS_DECIDER_URL is not configured."

    try:
        with urlopen(f"{endpoint.rstrip('/')}/health", timeout=2) as response:
            health = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return "Unavailable", str(exc)

    if (
        isinstance(health, dict)
        and health.get("status") == "ok"
        and isinstance(health.get("model"), str)
        and "2b" in health["model"].lower()
    ):
        return "Connected", health["model"]
    return "Error", "The health endpoint returned an unexpected response."


def get_bedrock_status() -> tuple[str, str]:
    model_id = os.getenv("BEDROCK_MODEL_ID", "").strip()
    if not model_id:
        return "Not configured", "Bedrock must be enabled for the hackathon demo."

    report = st.session_state.get("investigation_report")
    summary = report.get("bedrock_summary", {}) if report else {}
    if (
        summary.get("status") == "completed"
        and summary.get("model_id") == model_id
    ):
        return "Connected", summary.get("model_id", model_id)
    if summary.get("status") == "failed":
        return "Error", summary.get("error", "The last Bedrock request failed.")
    return "Configured · unverified", "A successful Bedrock request has not been recorded."


def load_json(path: Path):
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        return {"_load_error": str(exc)}


def display_json_download(data, filename: str, label: str):
    if data is not None:
        st.download_button(
            label=label,
            data=json.dumps(data, indent=2, default=str),
            file_name=filename,
            mime="application/json",
        )


def render_status(label: str, status: str, detail: str = ""):
    st.markdown(f"**{label}** · {status}")
    if detail:
        st.caption(detail)


def current_dataset(sample_path: Path):
    source = st.session_state.get("dataset_source", "Sample dataset")
    if source == "Sample dataset":
        if not sample_path.is_file():
            return None, None, "The sample CSV file is missing."
        try:
            raw = sample_path.read_bytes()
            frame = pd.read_csv(io.BytesIO(raw))
        except (OSError, pd.errors.ParserError, UnicodeDecodeError, ValueError) as exc:
            return None, None, f"Could not read the sample CSV: {exc}"
        return raw, frame, None

    uploaded = st.session_state.get("dataset_upload")
    if uploaded is None:
        return None, None, None
    try:
        raw = uploaded.getvalue()
        frame = pd.read_csv(io.BytesIO(raw))
    except (pd.errors.ParserError, UnicodeDecodeError, ValueError) as exc:
        return None, None, f"Could not read the uploaded CSV: {exc}"
    return raw, frame, None


def finding_exists(check_name: str, details: dict) -> bool | None:
    if details.get("status") != "completed":
        return None
    if check_name == "duplicates":
        return details.get("duplicate_count", 0) > 0
    if check_name == "freshness":
        return details.get("is_fresh") is False
    if check_name == "schema":
        return details.get("schema_matches") is False
    if check_name == "missing_values":
        return details.get("missing_cell_count", 0) > 0
    if check_name == "marks_range":
        return details.get("invalid_count", 0) > 0
    return None


def render_diagnostic(name: str, details: dict):
    label = CHECK_LABELS.get(name, name.replace("_", " ").title())
    problem = finding_exists(name, details)
    if problem is True:
        st.warning(f"Finding · {label}")
    elif problem is False:
        st.success(f"Verified · {label}")
    else:
        st.info(f"Unavailable · {label}")
    st.write(details.get("evidence", "No diagnostic evidence was returned."))
    with st.expander("Diagnostic output"):
        st.json(details)


def render_timeline(report: dict, assessments: dict | None, replay_result: dict | None):
    action = report.get("next_diagnostic_action", {})
    follow_up = report.get("follow_up_diagnostic", {})
    bedrock = report.get("bedrock_summary", {})
    stages = [
        ("CSV profiled", "Complete", f"{report.get('row_count', '—')} rows inspected."),
        ("Initial diagnostics", "Complete", f"{len(report.get('diagnostics', {}))} checks returned."),
        (
            "Decider choice",
            "Complete" if action.get("source") == "strands_decider_2b" else "Fallback / unavailable",
            (
                f"Selected {action.get('tool_label', action.get('tool_name'))}."
                if action.get("tool_name")
                else action.get("reason", "No choice was made.")
            ),
        ),
        (
            "Follow-up execution",
            "Complete" if follow_up.get("status") == "executed" else "Unavailable",
            follow_up.get("result", {}).get("evidence", "No follow-up result."),
        ),
        (
            "Bedrock explanation",
            {
                "completed": "Complete",
                "failed": "Error",
                "disabled": "Not configured",
            }.get(bedrock.get("status"), "Pending"),
            bedrock.get("text", bedrock.get("error", "No Bedrock response recorded.")),
        ),
        (
            "Hypothesis assessment",
            "Complete" if assessments else "Pending",
            (
                assessments.get("conclusion", "Assessment recorded.")
                if assessments
                else "No hypothesis assessment is available."
            ),
        ),
        (
            "Replay verification",
            "Complete" if replay_result else "Pending",
            (
                replay_result.get("status", "Replay completed.")
                if replay_result
                else "Run replay verification to verify this input fingerprint."
            ),
        ),
    ]
    for index, (title, status, detail) in enumerate(stages, start=1):
        st.markdown(f"**{index:02d} · {title}** — {status}")
        st.caption(detail)


def run_investigation(raw: bytes, filename: str):
    started = time.perf_counter()
    for key in (
        "investigation_report",
        "investigation_hypotheses",
        "investigation_assessments",
        "replay_record",
        "replay_result",
        "replay_run",
        "comparison_result",
    ):
        st.session_state.pop(key, None)
    safe_name = Path(filename).name or "uploaded.csv"
    if Path(safe_name).suffix.lower() != ".csv":
        safe_name += ".csv"

    input_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=".csv",
            prefix="datacontract_",
            delete=False,
        ) as temp_file:
            temp_file.write(raw)
            input_path = Path(temp_file.name)

        report = engine.investigate_csv(str(input_path))
        hypotheses = engine.build_hypotheses(report)
        assessments = engine.investigate_hypotheses(hypotheses)
        report["file_name"] = safe_name
        record = create_replay_record(
            input_path,
            {
                "freshness_limit_hours": engine.FRESHNESS_LIMIT_HOURS,
                "duplicate_key_columns": engine.DUPLICATE_KEY_COLUMNS,
                "expected_schema": engine.EXPECTED_SCHEMA,
                "marks_range": {
                    "column": "marks",
                    "minimum": 0,
                    "maximum": 100,
                },
            },
            list(report["diagnostics"]),
        )
        record["input_file"] = safe_name
        st.session_state["investigation_report"] = report
        st.session_state["investigation_hypotheses"] = hypotheses
        st.session_state["investigation_assessments"] = assessments
        st.session_state["replay_record"] = record
        st.session_state["replay_result"] = None
        st.session_state["comparison_result"] = None
        st.session_state["investigation_duration"] = time.perf_counter() - started
        st.session_state["investigation_error"] = None
    except Exception as exc:
        st.session_state["investigation_error"] = str(exc)
        raise
    finally:
        if input_path is not None:
            input_path.unlink(missing_ok=True)


def run_replay(raw: bytes):
    st.session_state["replay_result"] = None
    st.session_state["replay_run"] = None
    st.session_state["comparison_result"] = None
    record = st.session_state.get("replay_record")
    original = st.session_state.get("investigation_report")
    if not record or not original:
        raise ValueError("Run an investigation before verifying its replay.")

    replay_file = None
    input_file = None
    replay_output = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".json", prefix="datacontract_replay_", delete=False,
        ) as file:
            replay_file = Path(file.name)
        save_replay_record(record, replay_file)

        original_name = Path(record["input_file"]).name
        safe_stem = re.sub(r"[^A-Za-z0-9_-]", "_", Path(original_name).stem)[:40]
        unique_stem = f"ui_replay_{uuid.uuid4().hex}_{safe_stem}"
        input_file = REPORTS_DIR / f"{unique_stem}.csv"
        input_file.write_bytes(raw)

        replay, replay_output = rerun_investigation(replay_file, input_file)
        comparison = compare_diagnostics(
            {
                "replay_record": record,
                "csv_investigation": original,
            },
            replay,
        )
        verification = {
            "status": "MATCH" if replay["input_matches_original"] else "CHANGED",
            "investigation_id": record["investigation_id"],
            "replay_of_investigation_id": replay["replay_of_investigation_id"],
            "input_unchanged": replay["input_matches_original"],
            "checks_compared": comparison["summary"]["checks_compared"],
        }
        st.session_state["replay_result"] = verification
        st.session_state["replay_run"] = replay
        st.session_state["comparison_result"] = comparison
    finally:
        if replay_file is not None:
            replay_file.unlink(missing_ok=True)
        if input_file is not None:
            input_file.unlink(missing_ok=True)
        if replay_output is not None:
            replay_output.unlink(missing_ok=True)


def render_overview(report: dict | None, frame: pd.DataFrame | None, dataset_error: str | None):
    st.title("Don't guess the cause. Investigate the evidence.")
    st.markdown("**Every finding needs evidence. Every hypothesis faces a test. Every replay checks the result.**")
    st.write(
        "A data-pipeline investigation agent that measures CSV issues, asks "
        "Strands Decider 2B what to test next, and explains what the evidence does—and does not—prove."
    )
    action_col, sample_col, explainer_col = st.columns([1, 1, 1.5])
    with action_col:
        st.button(
            "Start investigation",
            type="primary",
            on_click=lambda: st.session_state.update({"active_view": "Investigate"}),
            width="stretch",
        )
    with sample_col:
        st.button(
            "Explore sample dataset",
            on_click=lambda: st.session_state.update(
                {"active_view": "Investigate", "dataset_source": "Sample dataset"}
            ),
            width="stretch",
        )
    with explainer_col:
        st.caption("Profile → diagnose → decide → execute → explain → replay")

    st.divider()
    if report is None:
        st.subheader("Your investigation workspace")
        st.info("No investigation has run in this session. Choose the sample CSV or upload a file under Investigate.")
        return

    diagnostics = report.get("diagnostics", {})
    findings = sum(
        finding_exists(name, value) is True for name, value in diagnostics.items()
    )
    schema_problem = finding_exists("schema", diagnostics.get("schema", {}))
    freshness = diagnostics.get("freshness", {})
    replay = st.session_state.get("replay_result")
    cols = st.columns(5)
    cols[0].metric("Findings", findings)
    cols[1].metric("Schema", "Needs attention" if schema_problem else "Matches" if schema_problem is False else "Unknown")
    cols[2].metric("Freshness", "Stale" if freshness.get("is_fresh") is False else "Fresh" if freshness.get("is_fresh") is True else "Unknown")
    cols[3].metric("Decider", "Real choice" if report.get("next_diagnostic_action", {}).get("source") == "strands_decider_2b" else "Fallback")
    cols[4].metric("Replay", replay.get("status") if replay else "Not run")

    st.subheader("Investigation journey")
    render_timeline(
        report,
        st.session_state.get("investigation_assessments"),
        replay,
    )
    st.divider()
    render_decision(report)
    if frame is not None:
        st.caption(f"Current dataset preview · {len(frame)} rows · {len(frame.columns)} columns")
    if dataset_error:
        st.warning(dataset_error)


def render_intake(sample_path: Path):
    st.title("Investigate a dataset")
    st.write("Choose a CSV. The app previews its structure before running the checks.")
    st.radio(
        "Dataset",
        ["Sample dataset", "Upload CSV"],
        horizontal=True,
        key="dataset_source",
    )
    if st.session_state["dataset_source"] == "Upload CSV":
        st.file_uploader(
            "Drop a CSV here or browse files",
            type=["csv"],
            key="dataset_upload",
            help="CSV rows are processed locally. Aggregate findings are sent to configured Strands Decider and Bedrock services.",
        )

    raw, frame, error = current_dataset(sample_path)
    if error:
        st.error(error)
    elif frame is None:
        st.info("Choose the sample dataset or upload a CSV to continue.")
    else:
        source = (
            sample_path.name
            if st.session_state["dataset_source"] == "Sample dataset"
            else st.session_state["dataset_upload"].name
        )
        st.markdown(f"**{source}** · {len(frame)} rows · {len(frame.columns)} columns")
        st.success("CSV parsed successfully.")
        st.dataframe(frame.head(8), width="stretch", hide_index=True)
        with st.expander("Detected columns and data types"):
            st.dataframe(
                pd.DataFrame(
                    {"Column": frame.columns, "Detected type": frame.dtypes.astype(str).values}
                ),
                width="stretch",
                hide_index=True,
            )

        st.caption(
            "The configured contract checks student_id, date, updated_at and "
            "marks. Other CSVs can still be inspected, but schema or marks checks "
            "may report that expected fields are missing."
        )
        if st.button("Run investigation", type="primary", width="stretch"):
            with st.spinner("Running diagnostics, asking Decider, and requesting Bedrock explanation if configured…"):
                try:
                    run_investigation(raw, source)
                    st.success("Investigation finished. Open Overview or Evidence Ledger to review the results.")
                except Exception as exc:
                    st.error(f"Investigation failed: {exc}")
                    with st.expander("Technical error details"):
                        st.exception(exc)


def render_findings(report: dict | None):
    st.title("Evidence Ledger")
    if report is None:
        st.info("Run an investigation to create an evidence ledger.")
        return
    st.caption("Measured observations from the CSV. These are not root-cause claims.")
    diagnostics = report.get("diagnostics", {})
    for start in range(0, len(diagnostics), 2):
        columns = st.columns(2)
        for column, (name, details) in zip(columns, list(diagnostics.items())[start:start + 2]):
            with column:
                render_diagnostic(name, details)
    with st.expander("Chronological evidence trail"):
        st.caption("Events are shown in execution order; timestamps are not recorded by the current engine.")
        replay_record = st.session_state.get("replay_record", {})
        st.markdown("**Input / state**")
        st.write(
            f"{report.get('file_name', 'CSV')} · {report.get('row_count', '—')} rows · "
            f"{len(report.get('columns', []))} columns"
        )
        if replay_record.get("input_sha256"):
            st.caption(f"Input SHA-256: {replay_record['input_sha256']}")
        st.markdown("**Observed baseline evidence**")
        for entry in report.get("evidence_ledger", []):
            st.markdown(f"**{entry.get('check', 'Check')}** · {entry.get('status', 'unknown')}")
            st.write(entry.get("observation", ""))
            st.caption(
                "Problem detected: "
                + (
                    "Yes" if entry.get("problem_detected") is True
                    else "No" if entry.get("problem_detected") is False
                    else "Unknown"
                )
            )
            st.json(entry.get("details", {}))
        action = report.get("next_diagnostic_action", {})
        st.markdown("**Decision**")
        if action.get("source") == "strands_decider_2b":
            st.write(f"Strands Decider 2B selected `{action.get('tool_name')}`.")
        elif action.get("tool_name"):
            st.write(f"Rule-based fallback selected `{action.get('tool_name')}`; no model decision is claimed.")
        else:
            st.write(action.get("reason", "No decision was recorded."))
        follow_up = report.get("follow_up_diagnostic") or {}
        st.markdown("**Tool execution / observed follow-up**")
        st.write(
            follow_up.get("result", {}).get(
                "evidence",
                f"No follow-up result recorded ({follow_up.get('status', 'unavailable')}).",
            )
        )
        st.markdown("**Interpretation**")
        assessments = st.session_state.get("investigation_assessments")
        st.write(
            assessments.get("conclusion", "No hypothesis assessment is available.")
            if assessments
            else "No hypothesis assessment is available."
        )


def render_decision(report: dict | None):
    st.title("Decision Inspector")
    if report is None:
        st.info("No decision trace is available until an investigation runs.")
        return
    action = report.get("next_diagnostic_action", {})
    diagnostics = report.get("diagnostics", {})
    eligible = [
        name for name, result in diagnostics.items()
        if name in TOOL_DESCRIPTIONS and result.get("status") == "completed"
    ]
    decision_col, evidence_col = st.columns([1, 1])
    with decision_col:
        st.subheader("Typed decision")
        st.caption("Question type: choice")
        st.write(NEXT_TOOL_INSTRUCTIONS)
        st.markdown("**Available diagnostic options**")
        for name in eligible:
            st.markdown(f"- `{name}` — {TOOL_DESCRIPTIONS[name]}")
        with st.expander("Aggregate evidence state supplied to Decider"):
            st.json(build_evidence_state(diagnostics))
        st.caption(
            "This compact state is the model input. The next panel is the "
            "separate observed result from executing its selected tool."
        )

    with evidence_col:
        st.subheader("Decision outcome")
        if action.get("source") == "strands_decider_2b":
            st.success("Decision made by the configured Strands Decider 2B service.")
            st.markdown(f"### {action.get('tool_label', action.get('tool_name'))}")
            if action.get("confidence") is not None:
                st.metric("Returned confidence", f"{action['confidence']:.0%}")
            st.caption(f"Model: {action.get('model', 'Model not identified')}")
        elif action.get("tool_name"):
            st.warning("Rule-based offline fallback — not a Decider model decision.")
            st.markdown(f"### {action.get('tool_label', action.get('tool_name'))}")
            st.caption(action.get("reason", ""))
        else:
            st.info("Decision trace unavailable — the Decider integration has not completed a real decision.")

        follow_up = report.get("follow_up_diagnostic") or {}
        if follow_up.get("status") == "executed":
            st.markdown("**Executed tool output**")
            st.write(follow_up.get("result", {}).get("evidence", "No output evidence."))
            with st.expander("Full selected-tool output"):
                st.json(follow_up)
        elif action.get("tool_name"):
            st.warning("A decision exists, but no successful follow-up execution is recorded.")

    if action.get("source") == "strands_decider_2b":
        with st.expander("Model-returned option probabilities"):
            probabilities = action.get("probabilities", {})
            if probabilities:
                for name, value in sorted(probabilities.items(), key=lambda item: item[1], reverse=True):
                    st.progress(float(value), text=f"{CHECK_LABELS.get(name, name)} · {float(value):.1%}")
            else:
                st.info("No probabilities were returned.")

    st.divider()
    st.subheader("Amazon Bedrock explanation")
    st.caption("Bedrock generates an explanation from aggregate findings; it does not make or override the Decider's choice.")
    bedrock = report.get("bedrock_summary", {})
    if bedrock.get("status") == "completed":
        st.success(f"Bedrock response · {bedrock.get('model_id', 'Model ID unavailable')}")
        st.write(bedrock.get("text", ""))
    elif bedrock.get("status") == "failed":
        st.error(bedrock.get("error", "Bedrock request failed."))
    else:
        st.warning("No Bedrock explanation was generated. Configure BEDROCK_MODEL_ID and AWS credentials, then rerun the investigation.")

def render_replay(raw: bytes | None):
    st.title("Replay Verification")
    record = st.session_state.get("replay_record")
    if not record:
        st.info("Run an investigation first. A replay fingerprint and investigation ID will be created for that input.")
        return
    st.write("Replay verification compares the current CSV fingerprint with the saved investigation fingerprint, then reruns the saved diagnostic configuration.")
    st.code(f"Investigation ID  {record['investigation_id']}\nInput file        {record['input_file']}\nSHA-256           {record['input_sha256']}")
    if raw is None:
        st.warning("The dataset is not currently available. Re-select or re-upload the same CSV to verify it.")
    elif st.button("Verify fingerprint and rerun diagnostics", type="primary"):
        with st.spinner("Verifying the input and rerunning saved checks…"):
            try:
                run_replay(raw)
                st.success("Replay completed and the input fingerprint matches.")
            except Exception as exc:
                st.error(f"Replay could not be verified: {exc}")
                with st.expander("Technical error details"):
                    st.exception(exc)

    result = st.session_state.get("replay_result")
    if result:
        if result["input_unchanged"]:
            st.success("MATCH · Input bytes match the saved SHA-256 fingerprint.")
        else:
            st.error("CHANGED · Replay input differs from the original.")
        first, second, third = st.columns(3)
        first.metric("Original investigation", result["investigation_id"][:8])
        second.metric("Replay of", result["replay_of_investigation_id"][:8])
        third.metric("Checks rerun", result["checks_compared"])


def render_comparison():
    st.title("Replay Comparison")
    comparison = st.session_state.get("comparison_result")
    if not comparison:
        st.info("Verify a replay first. The comparison will then show results for that investigation.")
        return
    summary = comparison["summary"]
    a, b, c = st.columns(3)
    a.metric("Checks compared", summary["checks_compared"])
    b.metric("Changed", summary["checks_changed"])
    c.metric("Unchanged", summary["checks_unchanged"])
    if comparison.get("input_matches_original"):
        st.success("Replay input matches the original investigation fingerprint.")
    else:
        st.error("Replay input does not match the original fingerprint.")
    st.caption(comparison.get("comparison_note", ""))
    for name, result in comparison.get("diagnostics", {}).items():
        title = CHECK_LABELS.get(name, name.replace("_", " ").title())
        with st.expander(f"{title} · {result.get('status', 'unknown').title()}"):
            if result.get("changed_fields"):
                st.markdown("**Changed fields**")
                st.json(result["changed_fields"])
            else:
                st.write("No structured diagnostic fields changed.")
            if result.get("time_sensitive_values_changed"):
                st.caption("Time-sensitive freshness values changed; these are shown separately from structured changes.")
    display_json_download(comparison, "replay_comparison.json", "Download comparison JSON")


def render_configuration(decider_status, decider_detail, bedrock_status, bedrock_detail, dataset_loaded):
    st.title("Configuration & integrations")
    st.write("Connection labels below come from live health checks or recorded successful/failed requests—not from installed packages.")
    left, right = st.columns(2)
    with left:
        render_status("Strands Decider 2B", decider_status, decider_detail)
        st.caption(f"Endpoint: {os.getenv('STRANDS_DECIDER_URL', 'Not configured')}")
    with right:
        render_status("Amazon Bedrock", bedrock_status, bedrock_detail)
        st.caption(f"Model ID: {os.getenv('BEDROCK_MODEL_ID', 'Not configured')}")
        st.caption(f"AWS region: {os.getenv('AWS_REGION', os.getenv('AWS_DEFAULT_REGION', 'Default credential chain'))}")
    st.divider()
    render_status("Dataset", "Loaded" if dataset_loaded else "Not loaded")
    st.subheader("Submission readiness")
    st.markdown(
        "- [x] Meaningful Strands Decider choice and selected-tool execution are implemented.\n"
        "- [x] Reusable `#tool-selection` pattern is documented in the README.\n"
        "- [ ] A successful Amazon Bedrock request must be shown in the demo.\n"
        "- [ ] Publish the Builder Center article and public under-three-minute demo.\n"
        "- [ ] Confirm the public repository has an OSI-approved license and final code."
    )
    st.caption("The UI cannot publish the article/video or confirm originality on your behalf.")


sample_path = DATA_DIR / "quality_test.csv"
with st.sidebar:
    st.markdown("## DATA / CONTRACT")
    st.markdown(
        """
        <div class="brand-lockup">
          <span class="brand-mark">DC</span>
          <div>
            <div class="brand-name">DataContract</div>
            <div class="brand-kicker">DETECTIVE</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    selected_view = st.radio("Workspace", NAV_ITEMS, key="active_view", label_visibility="collapsed")
    st.divider()
    decider_status, decider_detail = read_decider_health()
    bedrock_status, bedrock_detail = get_bedrock_status()
    dataset_raw, dataset_frame, dataset_error = current_dataset(sample_path)
    render_status("Decider", decider_status, decider_detail)
    render_status("Bedrock", bedrock_status, bedrock_detail)
    render_status("Dataset", "Loaded" if dataset_frame is not None else "Not loaded")
    st.caption("Decider makes the typed choice. Bedrock explains evidence.")

report = st.session_state.get("investigation_report")
assessments = st.session_state.get("investigation_assessments")

if selected_view == "Overview":
    render_overview(report, dataset_frame, dataset_error)
elif selected_view == "Investigate":
    render_intake(sample_path)
elif selected_view == "Evidence Ledger":
    render_findings(report)
elif selected_view == "Hypotheses":
    st.title("Hypothesis Board")
    if assessments is None:
        st.info("Run an investigation to assess possible causes.")
    else:
        if assessments.get("root_cause_confirmed"):
            st.warning("A root cause is marked confirmed by the assessment. Check the evidence and limitations.")
        else:
            st.info("Unresolved · available CSV checks do not prove the underlying cause.")
        for hypothesis in assessments.get("hypotheses", []):
            with st.container(border=True):
                st.subheader(hypothesis.get("hypothesis", "Hypothesis"))
                st.caption(hypothesis.get("assessment", "unresolved").replace("_", " ").title())
                st.write(hypothesis.get("explanation", ""))
                left, right = st.columns(2)
                with left:
                    st.markdown("**Supporting evidence**")
                    for value in hypothesis.get("supporting_evidence", []) or ["None recorded"]:
                        st.markdown(f"- {value}")
                with right:
                    st.markdown("**Contradicting evidence**")
                    for value in hypothesis.get("contradicting_evidence", []) or ["None recorded"]:
                        st.markdown(f"- {value}")
                if hypothesis.get("missing_required_evidence"):
                    st.markdown("**Remaining uncertainty**")
                    for value in hypothesis["missing_required_evidence"]:
                        st.markdown(f"- {value}")
elif selected_view == "Replay Verification":
    render_replay(dataset_raw)
elif selected_view == "Replay Comparison":
    render_comparison()
elif selected_view == "Configuration":
    render_configuration(
        decider_status,
        decider_detail,
        bedrock_status,
        bedrock_detail,
        dataset_frame is not None,
    )

if report is not None:
    with st.sidebar:
        st.divider()
        st.caption(
            f"Latest investigation · {report.get('file_name', 'CSV')} · "
            f"{st.session_state.get('investigation_duration', 0):.2f}s measured"
        )
        display_json_download(report, "investigation_report.json", "Download report JSON")

st.markdown("---")
st.caption("DataContract Detective · Findings are observations. Hypotheses remain open until evidence proves more.")
