
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

import run_investigation as engine


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
    "Investigate data quality problems using diagnostics, "
    "evidence-based hypotheses, replay verification, and comparison."
)


def load_json(path: Path):
    """Load a JSON file, returning None when it is unavailable."""
    if not path.exists():
        return None

    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        return None


def display_json_download(data, filename: str, label: str):
    """Display a download button for JSON data."""
    if data is not None:
        st.download_button(
            label=label,
            data=json.dumps(data, indent=2, default=str),
            file_name=filename,
            mime="application/json",
        )


st.header("1. Choose a CSV file")

sample_path = DATA_DIR / "quality_test.csv"

use_sample = st.checkbox(
    "Use the sample quality_test.csv file",
    value=True,
)

uploaded_file = None

if not use_sample:
    uploaded_file = st.file_uploader(
        "Upload a CSV file",
        type=["csv"],
    )

if use_sample:
    if sample_path.exists():
        st.success(f"Sample file ready: {sample_path.name}")
    else:
        st.error(f"Sample file not found: {sample_path}")
elif uploaded_file is not None:
    st.success(f"Uploaded file: {uploaded_file.name}")
else:
    st.info("Upload a CSV file to begin.")

st.divider()
st.header("2. Run Investigation")

if st.button("🔍 Run Investigation", type="primary"):
    input_path = None

    try:
        if use_sample:
            if not sample_path.exists():
                st.error("The sample CSV file does not exist.")
                st.stop()

            input_path = sample_path
            report = engine.investigate_csv(str(input_path))

        else:
            if uploaded_file is None:
                st.warning("Please upload a CSV file first.")
                st.stop()

            with tempfile.NamedTemporaryFile(
                mode="wb",
                suffix=".csv",
                delete=False,
            ) as temp_file:
                temp_file.write(uploaded_file.getvalue())
                input_path = Path(temp_file.name)

            report = engine.investigate_csv(str(input_path))

        hypotheses = engine.build_hypotheses(report)

        assessments = engine.investigate_hypotheses(hypotheses)

        st.session_state["investigation_report"] = report
        st.session_state["investigation_hypotheses"] = hypotheses
        st.session_state["investigation_assessments"] = assessments

        st.success("Investigation completed successfully.")

    except Exception as exc:
        st.error(f"Investigation failed: {exc}")

    finally:
        if (
            input_path is not None
            and input_path != sample_path
            and input_path.exists()
        ):
            try:
                input_path.unlink()
            except OSError:
                pass


report = st.session_state.get("investigation_report")
hypotheses = st.session_state.get("investigation_hypotheses")
assessments = st.session_state.get("investigation_assessments")

if report is not None:
    st.divider()
    st.header("3. Investigation Results")

    st.subheader("Diagnostic Report")
    st.json(report)

    st.download_button(
        label="Download Investigation Report",
        data=json.dumps(report, indent=2, default=str),
        file_name="investigation_report.json",
        mime="application/json",
    )

    if hypotheses is not None:
        st.subheader("Root-Cause Hypotheses")
        st.json(hypotheses)

        display_json_download(
            hypotheses,
            "investigation_hypotheses.json",
            "Download Hypotheses",
        )

    if assessments is not None:
        st.subheader("Hypothesis Assessments")
        st.json(assessments)

        display_json_download(
            assessments,
            "hypothesis_assessments.json",
            "Download Hypothesis Assessments",
        )


st.divider()
st.header("4. Replay Verification")

st.write(
    "Verify whether a saved replay record matches the original input data."
)

replay_path = REPORTS_DIR / "quality_test_replay.json"

if st.button("✅ Verify Replay"):
    if not replay_path.exists():
        st.warning(
            "Replay record not found. Run an investigation first."
        )
    elif not sample_path.exists():
        st.error("The sample CSV file was not found.")
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
            )

            if result.returncode == 0:
                st.success("Replay verification completed.")
            else:
                st.error("Replay verification reported an error.")

            if result.stdout:
                st.code(result.stdout, language="text")

            if result.stderr:
                st.code(result.stderr, language="text")

        except (OSError, subprocess.TimeoutExpired) as exc:
            st.error(f"Replay verification failed: {exc}")


st.divider()
st.header("5. Replay Comparison")

st.write(
    "Compare the original investigation with a replay run to identify "
    "which diagnostic checks changed."
)

comparison_path = REPORTS_DIR / "replay_comparison.json"
comparison = load_json(comparison_path)

if comparison is None:
    st.info(
        "No comparison report found. Run the replay comparison command "
        "in the terminal to generate one."
    )
else:
    summary = comparison.get("summary", {})
    diagnostics = comparison.get("diagnostics", {})

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Checks Compared",
        summary.get("checks_compared", 0),
    )
    col2.metric(
        "Checks Changed",
        summary.get("checks_changed", 0),
    )
    col3.metric(
        "Checks Unchanged",
        summary.get("checks_unchanged", 0),
    )

    if summary.get("checks_changed", 0) == 0:
        st.success("All compared diagnostic checks remain unchanged.")
    else:
        st.warning("Some diagnostic checks have changed.")

    comparison_note = comparison.get("comparison_note")
    if comparison_note:
        st.info(comparison_note)

    st.subheader("Individual Check Results")

    if diagnostics:
        for check_name, details in diagnostics.items():
            status = details.get("status", "unknown")
            changed_fields = details.get("changed_fields", {})
            time_sensitive = details.get(
                "time_sensitive_values_changed",
                False,
            )

            with st.expander(
                f"{check_name.replace('_', ' ').title()} — {status.title()}"
            ):
                st.write(f"**Status:** {status}")

                if changed_fields:
                    st.write("**Changed fields:**")
                    st.json(changed_fields)
                else:
                    st.write("No diagnostic field changes recorded.")

                st.write(
                    "**Time-sensitive values changed:** "
                    f"{'Yes' if time_sensitive else 'No'}"
                )
    else:
        st.info("No individual diagnostic results are available.")

    st.download_button(
        label="Download Full Comparison Report",
        data=json.dumps(comparison, indent=2, default=str),
        file_name="replay_comparison.json",
        mime="application/json",
    )

st.divider()
st.caption(
    "DataContract Detective | Evidence-driven data pipeline investigation"
)
