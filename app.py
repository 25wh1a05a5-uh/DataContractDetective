
"""DataContract Detective — Streamlit dashboard."""

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import streamlit as st

PROJECT_DIR = Path(__file__).resolve().parent
SRC_DIR = PROJECT_DIR / "src"
DATA_DIR = PROJECT_DIR / "data"
REPORTS_DIR = PROJECT_DIR / "reports"

sys.path.insert(0, str(SRC_DIR))

import run_investigation as engine  # noqa: E402


st.set_page_config(
    page_title="DataContract Detective",
    page_icon="🔎",
    layout="wide",
)

st.title("🔎 DataContract Detective")
st.caption(
    "Don't guess the cause. Test the evidence. Then prove it."
)

st.write(
    "Investigate data quality problems, examine evidence, "
    "evaluate possible causes, and verify saved investigation results."
)

# ---------------------------------------------------------
# Investigation
# ---------------------------------------------------------

st.header("1. Run an Investigation")

use_sample = st.checkbox(
    "Use the sample quality_test.csv",
    value=True,
)

uploaded_file = None

if not use_sample:
    uploaded_file = st.file_uploader(
        "Upload a CSV file",
        type=["csv"],
    )

if st.button("Run Investigation", type="primary"):
    try:
        if use_sample:
            csv_path = DATA_DIR / "quality_test.csv"

            if not csv_path.exists():
                st.error(f"Sample CSV not found: {csv_path}")
                st.stop()

            csv_bytes = csv_path.read_bytes()
        else:
            if uploaded_file is None:
                st.warning("Please upload a CSV file first.")
                st.stop()

            csv_bytes = uploaded_file.getvalue()

        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=".csv",
            delete=False,
        ) as temp_file:
            temp_file.write(csv_bytes)
            temp_path = Path(temp_file.name)

        try:
            report = engine.investigate_csv(str(temp_path))
            hypotheses = engine.build_hypotheses(report)
            assessments = engine.investigate_hypotheses(
                hypotheses,
                report,
            )

            st.session_state["investigation_report"] = report
            st.session_state["investigation_assessments"] = assessments
            st.session_state["investigation_input_sha256"] = (
                hashlib.sha256(csv_bytes).hexdigest()
            )

            st.success("Investigation completed successfully.")
        finally:
            temp_path.unlink(missing_ok=True)

    except Exception as exc:
        st.error(f"Investigation failed: {exc}")

report = st.session_state.get("investigation_report")
assessments = st.session_state.get("investigation_assessments")

if report:
    st.header("2. Investigation Results")

    if isinstance(report, dict):
        st.subheader("Investigation Summary")

        summary = report.get("summary", {})
        if isinstance(summary, dict) and summary:
            columns = st.columns(min(len(summary), 4))
            for index, (key, value) in enumerate(summary.items()):
                with columns[index % len(columns)]:
                    st.metric(
                        key.replace("_", " ").title(),
                        str(value),
                    )

        st.subheader("Evidence Report")
        st.json(report)

    else:
        st.write(report)

    if assessments is not None:
        st.subheader("Root-Cause Hypotheses")

        st.info(
            "A hypothesis is not a confirmed root cause. "
            "Review supporting evidence, contradicting evidence, "
            "and evidence that is still missing."
        )

        if isinstance(assessments, dict):
            assessment_items = assessments.items()
        elif isinstance(assessments, list):
            assessment_items = [
                (f"Hypothesis {index + 1}", item)
                for index, item in enumerate(assessments)
            ]
        else:
            assessment_items = []

        for name, assessment in assessment_items:
            with st.expander(str(name), expanded=True):
                if isinstance(assessment, dict):
                    st.json(assessment)
                else:
                    st.write(assessment)

    report_bytes = json.dumps(
        report,
        indent=2,
        default=str,
    ).encode("utf-8")

    st.download_button(
        "Download Investigation Report (JSON)",
        data=report_bytes,
        file_name="investigation_report.json",
        mime="application/json",
    )

    if assessments is not None:
        assessments_bytes = json.dumps(
            assessments,
            indent=2,
            default=str,
        ).encode("utf-8")

        st.download_button(
            "Download Hypothesis Assessments (JSON)",
            data=assessments_bytes,
            file_name="hypothesis_assessments.json",
            mime="application/json",
        )

# ---------------------------------------------------------
# Replay Verification
# ---------------------------------------------------------

st.divider()
st.header("3. Replay Verification")

st.write(
    "Verify that the saved replay record matches the original input "
    "and that the input has not changed."
)

replay_path = REPORTS_DIR / "quality_test_replay.json"
sample_path = DATA_DIR / "quality_test.csv"

if st.button("Verify Saved Replay"):
    if not replay_path.exists():
        st.error(f"Replay record not found: {replay_path}")
    elif not sample_path.exists():
        st.error(f"Sample CSV not found: {sample_path}")
    else:
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    str(SRC_DIR / "verify_replay.py"),
                    str(replay_path),
                    str(sample_path),
                ],
                cwd=str(PROJECT_DIR),
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )

            output = (result.stdout or "") + (result.stderr or "")
            st.code(output or "No output returned.")

            if result.returncode == 0 and "MATCH" in output:
                st.success("Replay verification completed.")
            else:
                st.warning(
                    "Replay verification did not report a successful MATCH. "
                    "Review the output above."
                )

        except Exception as exc:
            st.error(f"Replay verification failed: {exc}")

# ---------------------------------------------------------
# Replay Comparison
# ---------------------------------------------------------

st.divider()
st.header("4. Replay Comparison")

st.write(
    "Compare the original investigation with a replay run to identify "
    "diagnostic changes."
)

comparison_path = REPORTS_DIR / "replay_comparison.json"

if st.button("Refresh Replay Comparison"):
    st.rerun()

if comparison_path.exists():
    try:
        with comparison_path.open("r", encoding="utf-8") as file:
            comparison = json.load(file)

        # IMPORTANT: summary metrics are nested under "summary".
        summary = comparison.get("summary", {})

        checks_compared = summary.get("checks_compared", 0)
        checks_changed = summary.get("checks_changed", 0)
        checks_unchanged = summary.get("checks_unchanged", 0)

        col1, col2, col3 = st.columns(3)

        col1.metric("Checks Compared", checks_compared)
        col2.metric("Checks Changed", checks_changed)
        col3.metric("Checks Unchanged", checks_unchanged)

        st.subheader("Comparison Details")

        input_matches = comparison.get("input_matches_original")
        if input_matches is True:
            st.success("Replay input matches the original input.")
        elif input_matches is False:
            st.warning("Replay input differs from the original input.")
        else:
            st.info("Input-match status is not available.")

        st.write(
            comparison.get(
                "comparison_note",
                "No comparison note available.",
            )
        )

        # IMPORTANT: individual checks are nested under "diagnostics".
        diagnostics = comparison.get("diagnostics", {})

        if diagnostics:
            for check_name, details in diagnostics.items():
                with st.expander(
                    check_name.replace("_", " ").title()
                ):
                    if isinstance(details, dict):
                        status = details.get("status", "unknown")

                        if status == "unchanged":
                            st.success("Status: Unchanged")
                        elif status == "changed":
                            st.warning("Status: Changed")
                        else:
                            st.info(f"Status: {status}")

                        st.json(details)
                    else:
                        st.write(details)
        else:
            st.warning(
                "No diagnostic entries were found under "
                "'diagnostics' in the comparison JSON."
            )

        st.download_button(
            "Download Replay Comparison (JSON)",
            data=json.dumps(
                comparison,
                indent=2,
                default=str,
            ),
            file_name="replay_comparison.json",
            mime="application/json",
        )

    except (json.JSONDecodeError, OSError) as exc:
        st.error(f"Could not read the comparison JSON: {exc}")
else:
    st.warning(
        "Comparison report not found. Run the replay comparison command "
        "in your terminal first."
    )
    st.code(
        r".\.venv\Scripts\python.exe -m src.replay_comparison "
        r"reports\quality_test_investigation.json "
        r"reports\quality_test_replay_run.json",
        language="powershell",
    )
