# Builder Center article draft

> Before publishing: run a live investigation with the Strands Decider server enabled, replace every bracketed placeholder with the observed result, and verify that the linked public repository and demo video are accessible. Do not present an offline fallback run as a Decider result.

## DataContract Detective: Letting Strands Decider Choose the Next Data-Quality Check

Data-quality dashboards can tell us that a CSV is wrong. The harder question is what to investigate next.

DataContract Detective is a CSV investigation app built around that next-step decision. It checks a student-marks dataset for missing values, out-of-range marks, schema drift, stale timestamps, and duplicate student records. It then offers the available diagnostic tools and a compact summary of the observed evidence to Strands Decider 2B. Decider returns a typed choice; the app validates that choice, runs the selected diagnostic again, and records both the decision and the resulting evidence.

### Why delegate this choice?

A fixed diagnostic sequence is predictable, but it cannot adapt the follow-up to the evidence. A general-purpose text response would be difficult to validate and could name a tool the app cannot execute. Decider's choice interface is a better fit: the options are constrained to tools that are actually available, and the selected option is checked before execution.

The app keeps this boundary explicit. With `STRANDS_DECIDER_URL` configured, the choice comes from the Strands Decider `/v1/systemone` API. If the service is not configured, a deterministic rule-based fallback is used and labeled as such; it is never described as an AI decision. The interface shows the decision source, selected tool, model confidence and probabilities when returned by Decider, and the selected tool's follow-up result.

### What happens in the sample investigation?

The sample CSV includes missing and out-of-range marks, a type mismatch, and stale timestamps. Baseline diagnostics create an evidence ledger. Decider then selects one available follow-up tool. In the live demo, the selected tool was **[insert the exact tool returned by the running Decider server]**, with confidence **[insert the displayed confidence]**. The application executed that tool and displayed **[insert the exact follow-up observation]**.

The sample also demonstrates why observation and cause must stay separate. A stale timestamp is evidence that the data is old; it does not prove that a particular pipeline failed. Hypotheses remain unconfirmed until additional source-system or pipeline evidence is available.

### The reusable pattern: evidence-conditioned tool selection

1. Run initial checks and convert their output into a compact, row-free evidence state.
2. Describe only valid, executable next-step tools as named choice options.
3. Ask Decider to choose one option based on the current evidence.
4. Validate the returned option and confidence before acting.
5. Execute the chosen tool and record the decision beside its result.
6. Keep fallback behavior and unconfirmed hypotheses visibly distinct from model decisions and proven causes.

This pattern is useful anywhere an agent should choose among known, auditable actions rather than invent a new action in free text.

### Bedrock's role

Amazon Bedrock is the generative explanation layer, not the decision-maker. The hackathon demo must configure `BEDROCK_MODEL_ID` and show a successful Bedrock Converse API response; it may remain unconfigured during offline development. Bedrock receives aggregate findings and the selected follow-up result, not raw CSV rows. The summary is displayed separately and is instructed not to claim that a root cause has been proven. AWS credentials are resolved through boto3's normal provider chain; credentials are not stored in the repository.

### Reproduce the demo

Install the optional dependencies, start the official Strands Decider 2B server, set `STRANDS_DECIDER_URL`, and launch the Streamlit app. The project's README has the exact Windows PowerShell commands, Bedrock setup, tests, and a short demo sequence. The source repository is **[25wh1a05a5-uh/DataContractDetective](https://github.com/25wh1a05a5-uh/DataContractDetective)** and the demo video is **[insert the public video URL]**.

The demonstrated decision was produced by the configured Strands Decider model. The Bedrock summary was **[enabled/disabled; name the configured model if enabled]**. The automated tests cover the documented API request/response handling using a mocked server response; **[after live validation, add the date, model name, and concise result of a real server run]**.

**Tags:** `#strands-decider-2b` `#tool-selection`

**Source repository:** [25wh1a05a5-uh/DataContractDetective](https://github.com/25wh1a05a5-uh/DataContractDetective)

## Official references

- [Strands Decider](https://github.com/strands-labs/strands-decider)
- [Amazon Bedrock Converse API](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html)
- [DataContract Detective README](./README.md)
