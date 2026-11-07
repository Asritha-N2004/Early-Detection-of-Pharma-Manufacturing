# Development status

Updated 7 November 2026. The remaining software features have been implemented. Full master-specification acceptance is **not yet declared** because Docker/PostgreSQL runtime verification requires a Docker-enabled host, which is unavailable in this environment.

| Phase | Status | Executed evidence and scope |
|---|---|---|
| 1 Repository / architecture | Implemented | Empty repository preserved and initialized; architecture and requirement traceability documented |
| 2 Backend / database | Verified locally | FastAPI, typed request schemas, 31 relational tables, 35 foreign-key links, five forward migrations; existing 15,654 readings backfilled into normalized context indexes |
| 3 Synthetic data | Verified | 15,702 seeded observations; four process registries; six chronological batches per process; drift, spikes, missing values, duplicates, gaps and noise |
| 4 Ingestion / features | Verified | JSON, multipart CSV, unit/name/finite-value checks, quarantine, idempotent reading identities, gap events, original payloads, aligned and trailing features |
| 5 Anomaly detection | Verified | Eight methods and ensemble, rolling/EWMA/CUSUM, multivariate covariance/forest, held-out detector comparison, approved frozen anomaly artifacts |
| 6 Prediction / lifecycle | Verified on synthetic batches | RF, Gradient Boosting, XGBoost; separate chronological train/validation/test batches with boundary purging; validation calibration; residual forecast envelopes; timing and batch metrics; drift monitoring |
| 7 Root cause | Verified | Correlation, observed onset ordering, historical finding IDs, attributable equipment/source evidence, online TreeSHAP from approved predictors; explicit hypotheses and limitations |
| 8 Risk | Verified | Configurable scales and RPN thresholds; procedure reference, critical-parameter and patient-safety overrides; risk matrix and recurrence context |
| 9 LangGraph | Verified | Durable SQL checkpoint saver, typed and agent-specific transition contracts, detached inputs, independent execution journal, retries, deadlines, restart recovery without replaying completed nodes, conditional branches |
| 10 Human review | Verified | Persistent interrupt checkpoint; authorized attributed review; idempotent rationale records; evidence requests re-run investigation; final recommendation dispositions do not authorize manufacturing |
| 11 Dashboard | Built and browser-checked | Eleven sections; API-backed metrics; equipment/date/batch/parameter filters; bounds and excursion markers; detector comparison; forecast envelopes; interactive graph; model governance, hyperparameter/agent/role settings, risk matrix and exports |
| 12 Reports / audit | Verified | Eight report families in JSON/CSV/PDF; PDF rendering reviewed; append-only hash chain and database mutation triggers; historical execution records retained |
| 13 Workers / Docker | Implemented; runtime verification pending | PostgreSQL-backed lease queue, separate worker service, shared persistent simulation with five scenarios, health checks, volumes, pinned dependency locks, Compose smoke-test script |
| 14 Automated verification | Passed locally | 33 backend tests; TypeScript check; Vite production build; both production and build-time dependency audits; backup integrity and restore-read test |
| 15 Documentation | Updated | README; architecture, data, agents, ML, API, deployment/operations, GMP gap inventory, validation strategy, requirement traceability |

## Completed in this continuation

- Reconstructed a new graph/saver from persisted checkpoint bytes and resumed the human checkpoint.
- Injected transient, timeout, invalid-transition and analytical failures; confirmed independent failure journals and API recovery without re-running completed ingestion nodes.
- Trained and evaluated three predictors plus a versioned eight-method anomaly ensemble. Controlled inference was tested to reject a predictor-only approval and accept approved active predictor **and** anomaly versions without refitting the latter.
- Checked model artifact hashes, rejected tampering and untrusted paths, preserved model versions, calibrated on validation only, and measured final held-out event latency/lead time without inventing missing detections.
- Tested all eight report families in all three formats, session revocation/deactivation, permissions, configurable risk scales, multivariate relationship shifts and equipment evidence retrieval.
- Parsed Compose YAML for PostgreSQL/backend/worker/frontend. This is configuration validation, **not** a successful Docker startup.
- Ran advisory audits with no known vulnerabilities returned. Backend and frontend audit JSON files retain the actual tool results.
- Browser checks use a disposable copy of the synthetic test database, not privileged test accounts in the main application. Model approval interaction, registry/settings forms, persistent workflow evidence and desktop/mobile layouts were inspected. PDF generation/download and risk-matrix submission were exercised. The QA database copies, proxy settings and processes were removed after verification.

## Remaining acceptance blocker

**Docker and PostgreSQL execution:** Docker Desktop/Engine is not installed or available on PATH. The user has been asked to make a Docker-enabled environment available. Run `scripts/verify_docker.ps1` there, then run the PostgreSQL integration test job. Do not mark full acceptance until those checks pass and any platform-specific failures are fixed.

## Boundaries, not unfinished prototype features

Optional LSTM, TimescaleDB and Redis were not needed for the specified prototype. Explanations use the requested deterministic fallback because no external LLM key is configured. Real equipment integration, regulated qualification, Part 11 electronic signatures, approved SOPs, infrastructure hardening and clinical/manufacturing validation remain external prerequisites before regulated production use, as the master prompt explicitly requires documenting. The system has no equipment-control or batch-release capability.

Known non-fatal upstream advisories: Starlette TestClient/httpx deprecation, joblib/NumPy array-shape deprecations, and Vite client-directive/bundle-size notices. These do not constitute a failed test or a known vulnerability finding.

## Account creation update

Added public Create account form and registration API. New accounts are viewer-only, passwords are hashed, self-elevation is rejected, and registration is audited. Controlled-mode accounts require administrator activation. Seven targeted registration/authentication checks passed; TypeScript and Vite production build passed. The live registration route and dashboard HTTP response were verified. Browser automation timed out, so the new form was not visually rechecked.

Account creation simplified: usernames accept spaces, email-style names and Unicode, with surrounding whitespace removed; passwords require at least 8 characters. The form displays friendly errors instead of raw validation JSON. Eleven registration checks and the production build passed.

## Vercel deployment â€” 7 November 2026

Production: https://pharmasignal-manufacturing.vercel.app in the requested `resum-projects` team. Vercel built the React frontend and Python container API successfully. A separate production daemon runs the workflow worker. An isolated free Neon PostgreSQL database stores application records, accounts, workflow state and trained artifact bytes; temporary files serve only as verified model caches. Fresh cloud secrets are separate from local credentials. Deployment uploads exclude local databases, secrets, model files and development caches.

Six forward migrations were applied to hosted PostgreSQL. All 47 backend tests passed locally. Live production health, authenticated registry/dashboard/graph/models/simulation requests, and audit-chain verification passed. The hosted account form was inspected and shows the eight-character minimum. With explicit user approval, all four synthetic datasets were imported: 15,654 accepted readings across fermentation, liquid, sterile and tablet manufacturing. Twenty-four duplicate inputs were skipped, and 282 data-quality events were recorded. Four starter investigations reached awaiting_human_review. Hosted dashboard, graph, model registry, simulation status and audit integrity checks passed after seeding.

The successful hosted container build and PostgreSQL migrations provide additional execution evidence, but do not replace the pending complete Docker Compose and PostgreSQL integration acceptance checks described above.
