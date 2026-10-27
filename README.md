
# 🔎 DataContract Detective

**An Evidence-Driven CSV Data Quality Agent with Adaptive Diagnostic Tool Selection**

> Don't guess the cause. Test the evidence. Then prove it.

DataContract Detective investigates CSV data quality problems, asks Strands Decider 2B to select a useful follow-up diagnostic, executes the selected check, and uses Amazon Bedrock to summarize the evidence when configured. The app distinguishes measured data-quality findings from root-cause hypotheses and preserves replay verification and comparison.

For local offline development, Bedrock may remain unconfigured. **The hackathon demo must show both a real Strands Decider 2B decision and a successful Amazon Bedrock explanation.** A deterministic fallback is clearly labeled and does not count as a Decider model decision.

## Features

- Duplicate record detection
- Data freshness checks
- Schema validation
- Missing value detection
- Numeric range validation
- Evidence-based root-cause hypothesis evaluation
- SHA-256 input fingerprint verification
- Repeatable diagnostic execution
- Original-versus-replay comparison
- Interactive Streamlit dashboard
- Strands Decider 2B tool selection through its documented local HTTP API
- Executes the selected follow-up diagnostic and records its output
- Amazon Bedrock evidence summary through the Converse API (required for the hackathon demo; optional for offline development)
- Explicit offline fallback when the Decider server is not configured
- Automated test coverage for core functionality

## Technology Stack

- Python 3.12
- pandas
- Streamlit
- pytest
- Amazon Bedrock Converse API (optional)
- Strands Decider 2B (optional local model server)
- JSON
- SHA-256 hashing

## Project Structure

```text
DataContractDetective/
├── app.py
├── SUBMISSION_DRAFT.md
├── requirements.txt
├── requirements-agent.txt
├── data/
│   └── quality_test.csv
├── reports/
├── src/
├── tests/
├── .venv/
├── .gitignore
├── LICENSE
└── README.md
```

## Getting Started

### 1. Open the project directory

Open a terminal in the project root:

```powershell
cd "C:\Users\Umme Habeeba\DataContractDetective"
```

### 2. Activate the virtual environment

```powershell
.\.venv\Scripts\Activate.ps1
```

Alternatively, run Python directly without activating the environment:

```powershell
.\.venv\Scripts\python.exe --version
```

### 3. Install core dependencies

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Install the optional agent integrations when you are ready to run the local Decider model or call Bedrock:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-agent.txt
```

The Strands Decider model downloads model files and may require substantial disk space, memory, and startup time. Install the optional dependencies only when you can run the model server. Bedrock requires an AWS account, model access in the selected region, and permission to invoke the chosen model.

### 4. Run the automated tests

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

## Launch the Dashboard

Start the Streamlit application:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open the local URL shown in the terminal, usually:

```text
http://localhost:8501
```

Use the sample CSV or upload a CSV file to investigate data quality.

## Enable Strands Decider 2B

The project uses Strands Decider's documented `POST /v1/systemone` choice API. The dashboard sends a compact aggregate evidence summary to the Decider service on the configured host; it does not send CSV rows. The Decider's choice determines which diagnostic is rerun as the next action. With no server URL configured, the app uses a clearly labeled deterministic fallback and does not claim that the model made the decision.

In a separate PowerShell terminal, install and start the official model server:

```powershell
cd "C:\Users\Umme Habeeba\DataContractDetective"
.\.venv\Scripts\Activate.ps1
strands-decider serve StrandsAgents/strands-decider-2B-qwen3.5-v1-2610 --device cpu --port 8000
```

The first start downloads the model. Check that the server responds before launching the app:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

In the PowerShell terminal where you launch Streamlit:

```powershell
$env:STRANDS_DECIDER_URL = "http://127.0.0.1:8000"
.\.venv\Scripts\python.exe -m streamlit run app.py
```

The app shows the selected diagnostic, the model confidence and option probabilities, and the result of rerunning the selected tool. Stop the Decider server with Ctrl+C when you are done.

## Enable Amazon Bedrock summaries

Bedrock is optional for offline development, but **must be configured and successfully used in the hackathon demo**.

Bedrock is a separate generative explanation step: it does not make or override the Decider's tool choice. The summary prompt contains the selected action, finding descriptions, and aggregate diagnostic results—not source CSV rows. A configured but unsuccessful Bedrock call is shown as an error rather than being silently reported as successful.

Configure AWS credentials with the AWS CLI rather than putting access keys in project files. For example:

```powershell
aws configure --profile data-contract-detective
$env:AWS_PROFILE = "data-contract-detective"
$env:AWS_REGION = "us-east-1"
$env:BEDROCK_MODEL_ID = "us.amazon.nova-micro-v1:0"
```

Use a model ID available to your AWS account and region. The AWS identity needs `bedrock:InvokeModel` permission. AWS documents the credentials provider chain and supported model IDs; check current model availability and pricing before use. Start the Decider server in its own terminal as described above. Launch Streamlit from the AWS-configured terminal so the app can call both services:

```powershell
$env:STRANDS_DECIDER_URL = "http://127.0.0.1:8000"
.\.venv\Scripts\python.exe -m streamlit run app.py
```

The dashboard labels Bedrock **Connected** only after a successful summary response. If configured but not yet called, it is marked unverified; if the last call failed, the error is displayed. Clear the session settings afterward if needed:

```powershell
Remove-Item Env:AWS_PROFILE -ErrorAction SilentlyContinue
Remove-Item Env:AWS_REGION -ErrorAction SilentlyContinue
Remove-Item Env:BEDROCK_MODEL_ID -ErrorAction SilentlyContinue
Remove-Item Env:STRANDS_DECIDER_URL -ErrorAction SilentlyContinue
```

## Hackathon submission runbook

### Reusable decision pattern

**Pattern tag: `#tool-selection`**

Use this pattern when an agent must choose its next action from a fixed set of safe, executable tools:

1. Run baseline diagnostics and build a compact evidence state (counts, statuses, schema differences and freshness values). The state excludes CSV rows.
2. Build the option set only from diagnostics that actually completed. Each option has a stable name and description in `src/decider.py`.
3. Ask Strands Decider's `choice` question for the single most useful next diagnostic.
4. Validate that the returned option is one of the available tools, then execute exactly that diagnostic.
5. Record the choice separately from the follow-up result. If the Decider endpoint is unavailable, label the rule-based fallback; never present it as a model decision.

The typed question is `next_tool`, with `type: choice`. Its instructions prioritize a concrete anomaly supported by evidence or, if none exists, the best validation check. Available options are:

| Option | Diagnostic rerun |
|---|---|
| `duplicates` | Repeated `student_id` records |
| `freshness` | Whether the latest `updated_at` timestamp exceeds 24 hours |
| `schema` | Missing, unexpected, or incorrectly typed columns |
| `missing_values` | Missing cells and affected columns |
| `marks_range` | Marks outside the inclusive 0–100 range |

**Implementation:** `src/decider.py` constructs the typed question and row-free evidence state, calls `POST /v1/systemone`, validates the choice, and runs the selected diagnostic. `src/run_investigation.py` wires the result into the report. The dashboard's Decision Inspector displays the question, actual evidence state, eligible options, selected choice, returned confidence (when supplied), and executed tool output.

To reproduce it, start the model server above, set `STRANDS_DECIDER_URL` in the Streamlit terminal, and run an investigation. Automated tests mock the API response to cover valid decisions, malformed output, unavailable service handling, and selected-tool execution.

### Suggested under-three-minute demo

1. **0:00–0:15** — Introduce the problem: a CSV reveals symptoms, but an investigation needs a defensible next test.
2. **0:15–0:40** — Select the sample CSV and show the measured baseline findings.
3. **0:40–1:15** — Show Decision Inspector: typed question, evidence state, available options, and the real Strands Decider choice.
4. **1:15–1:35** — Show the selected diagnostic's actual rerun result.
5. **1:35–2:00** — Show a successful Bedrock evidence explanation and distinguish observation from cause.
6. **2:00–2:25** — Show replay fingerprint verification/comparison and name the reusable `#tool-selection` pattern.

Record the demo only after both services work: the local Decider endpoint must produce a real decision and Bedrock must return a successful explanation. Keep AWS credentials and account details off-screen. Target under 2:30 to stay below the three-minute maximum.

### Publication checklist

- [ ] Run tests and the sample investigation with both Strands Decider and Bedrock enabled; record the real choice and successful explanation.
- [ ] Push the final project changes to the [public GitHub repository](https://github.com/25wh1a05a5-uh/DataContractDetective) and verify the latest version is accessible.
- [ ] Publish a Builder Center article based on [SUBMISSION_DRAFT.md](./SUBMISSION_DRAFT.md), replacing placeholders with observed live results.
- [ ] Publish a public demo video shorter than three minutes and include its link in the article/submission.
- [ ] Include `#strands-decider-2b` and the applicable pattern tag, such as `#tool-selection`.
- [ ] Confirm the project is original and was not published before the hackathon.

External publication, public repository settings, and video recording must be completed and verified by the project owner; this local project does not claim those submissions are already published.

### Official references

- [Strands Decider project and server API](https://github.com/strands-labs/strands-decider)
- [Strands Decider README/API usage](https://github.com/strands-labs/strands-decider/blob/main/README.md)
- [Amazon Bedrock Converse API](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html)
- [Amazon Bedrock model IDs and regional availability](https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html)

## Run an Investigation from the Terminal

```powershell
.\.venv\Scripts\python.exe src\run_investigation.py data\quality_test.csv
```

The investigation generates reports in the `reports/` directory.

## Verify a Saved Replay

```powershell
.\.venv\Scripts\python.exe src\verify_replay.py reports\quality_test_replay.json data\quality_test.csv
```

Replay verification checks whether the current input matches the saved fingerprint.

## Run a Replay

```powershell
.\.venv\Scripts\python.exe -m src.replay_runner reports\quality_test_replay.json data\quality_test.csv
```

## Compare Investigation Results

```powershell
.\.venv\Scripts\python.exe -m src.replay_comparison reports\quality_test_investigation.json reports\quality_test_replay_run.json
```

The comparison identifies changed and unchanged diagnostic results.

Use the report filenames generated by your actual investigation if they differ from these examples.

## Design Principles

### Evidence before conclusions

A hypothesis may have supporting evidence without being a confirmed root cause. Contradicting evidence and missing evidence must also be considered.

### Reproducibility

Saved replay records and SHA-256 fingerprints help verify that the input data has not changed.

### Transparent comparisons

The replay comparison distinguishes changes in diagnostic results from time-sensitive values, such as freshness age.

## Current Scope

The project supports local CSV diagnostics, evidence-conditioned tool selection (Strands Decider when configured), selected-tool execution, Bedrock summaries when configured, hypothesis evaluation, saved replay validation, diagnostic reruns, and comparison reports. The hackathon demo must configure both model integrations even though offline development remains possible.

The system does not guarantee that every underlying pipeline problem can be identified from CSV diagnostics alone.

## Future Improvements

- Support configurable data-contract rules.
- Allow users to define additional data contracts.
- Add more datasets and integration tests.

## Author

Built as a data quality investigation and reproducibility project.
