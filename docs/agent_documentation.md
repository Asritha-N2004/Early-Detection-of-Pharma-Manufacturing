# Agent contracts and execution controls

The ten reusable analytical functions live in `backend/app/workflow.py`. `CONTRACTS` declares each role, required state inputs and permitted output keys; `ValidState` provides strict runtime types. `GET /api/v1/agents/contracts` exposes concrete input/output schemas and tool limits. State includes original reading references, configuration snapshots, model versions, observed findings, predictions, hypotheses, risk, recommendations and review disposition.

| Agent | Inputs | Outputs | Conditions / permitted tools | Limitations |
|---|---|---|---|---|
| Data ingestion | Accepted readings and parameter registry | Validated status | Entry; read validated provenance | Request and quality validation precede the graph |
| Process monitoring | Readings, ranges, history and equipment evidence | Counted evidence summary, trailing feature engineering | Every workflow; read-only feature functions | Engineering ranges require approved procedures |
| Anomaly detection | Readings, selected method, approved anomaly version if active | Parameter scores and joint pattern assessment | Every workflow; numerical inference | Demo refit is labeled; controlled mode requires a frozen approved artifact; scores are not probabilities |
| Predictive | Findings, observed sampling cadence, horizon, active predictor | Trajectory forecasts, residual envelope, classifier prediction, drift, SHAP | Every workflow; trusted artifact inference | Next-sample classification and minute-based forecasts have different horizons |
| Root cause | Findings, onset times, correlations, historical events, current equipment records and model attributions | Ranked hypotheses with evidence and gaps | Abnormal/uncertain workflows and evidence-request loops; read-only source retrieval | Associations and earlier timestamps do not establish causes |
| Risk assessment | Flags, recurrence, configured scales/criticality | S/O/D, RPN, classification, impact context and escalation | Investigated workflows; deterministic arithmetic | Screening ratings require authorized quality assessment |
| Investigation | Findings, hypotheses and missing evidence | Questions and recommendations | Investigated workflows and renewed evidence requests | Missing records are identified, never fabricated |
| Decision support | Current, forecast, multivariate and model/drift signals | Routing status and explanation of retained signals | Every workflow; deterministic routing | Never confirms a GMP deviation or authorizes manufacturing |
| Report generation | Grounded summary and attributed human disposition | Labeled preliminary narrative | Before review and after recommendation disposition | Downloadable snapshots remain AI-generated and require review |
| Quality and audit | Execution events, versions, source context and user actions | Persisted execution and audit evidence | Orchestrator-owned writes | Database owners still require segregation and external anchoring controls |

Nodes execute under configurable deadlines. Timeout/connection failures retry twice. A timed-out pure calculation may finish in its worker thread, but its detached output is discarded and it cannot write state or control equipment. All starts/completions/failures are independently journaled. Invalid transition keys or types fail safely. Retry is deterministic against checkpointed inputs; recovery preserves completed nodes.

The graph interrupts at `human_review`. Reviewer/admin authentication and a rationale of at least ten characters are required before the API resumes it. Duplicate identical review submissions are idempotent. Evidence requests loop through root-cause/risk/investigation again and refresh available equipment evidence. Accept/reject/escalate only dispose of AI recommendations; they do not close a GMP deviation, sign a regulated record or release a batch.

No external LLM key is required. Summaries are an evidence-grounded deterministic fallback; no uploaded text can select tools, execute commands or change configuration.
