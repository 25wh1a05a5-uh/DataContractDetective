\# DataContract Detective



\*\*An evidence-driven CSV data quality investigation and replay system.\*\*



DataContract Detective identifies data quality problems in CSV files, evaluates possible causes, and compares diagnostic results across repeatable investigations.



> Don't guess the cause. Test the evidence. Then prove it.



\## Features



\- Duplicate record detection

\- Data freshness checks

\- Schema validation

\- Missing value detection

\- Numeric range validation

\- Hypothesis evaluation without automatically claiming an unproven root cause

\- Replay validation using SHA-256 file fingerprints

\- Re-running diagnostics using saved configuration

\- Comparing original and replayed diagnostic results

\- Automated tests for diagnostics, replay validation, and comparison



\## Technology Stack



\- Python

\- pandas

\- pytest

\- JSON

\- Markdown

\- SHA-256 hashing



\## Getting Started



\### 1. Activate the virtual environment



```powershell

.\\venv\\Scripts\\Activate.ps1

```



\### 2. Install dependencies



```powershell

python -m pip install pandas pytest

```



\### 3. Run the tests



```powershell

python -m pytest tests -v

```



\*\*Latest test result:\*\* 50 tests passed.



\## Replay an Investigation



Example command:



```powershell

python -m src.replay\_runner reports\\quality\_test\_replay.json data\\quality\_test.csv

```



\## Compare Investigation Results



```powershell

python -m src.replay\_comparison reports\\quality\_test\_investigation.json reports\\quality\_test\_replay\_run.json

```



Replace example filenames if your actual filenames differ.



\## Current Scope



The project currently performs local CSV diagnostics, validates replay records, reruns checks, and compares results. Freshness results can change over time, and diagnostic findings alone do not necessarily prove a root cause.



\## Future Improvements



\- Integrate an AI agent to select follow-up diagnostic tests

\- Generate evidence-backed investigation summaries

\- Recommend data-contract rules

\- Build a user-friendly interface



\## Author



Built as a data quality investigation and reproducibility project.

