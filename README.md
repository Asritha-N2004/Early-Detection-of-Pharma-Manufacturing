# PharmaSignal

A modular pharmaceutical manufacturing decision-support prototype with executable APIs, eleven React dashboard sections, synthetic data, statistical and machine-learning detection, durable LangGraph investigations, model governance, authorized review, reports, audit integrity and background workers.

**Synthetic demonstration. Not validated or certified for regulated use.** There is no equipment-control, PLC/SCADA, interlock, batch-release or manufacturing-authorization interface. AI findings remain potential deviations until handled under authorized quality procedures.

## Start locally

Python 3.12 and Node 22+ are recommended for the dependency versions verified here. Run from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.lock
$env:BOOTSTRAP_PASSWORD = Read-Host 'Administrator password, 12+ characters'
$env:JWT_SECRET = python -c "import secrets; print(secrets.token_urlsafe(48))"
python -m alembic upgrade head
python scripts/generate_data.py
python scripts/bootstrap.py
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8010
```

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open [dashboard](http://localhost:5173) and [API documentation](http://localhost:8010/docs). Sign in as `admin` using your runtime password. `scripts/start_local.ps1` can instead generate ignored local `.env` credentials and start the API. The bundled-runtime alternative to npm is documented in [local environment](docs/local_environment.md).

The current production-build preview is at [local preview](http://127.0.0.1:5181). Reload after an update. Its API uses port 8010 because another application owns port 8000. Local SQLite data is preserved in `pharma.db`; durable workflows use `pharma-workflows.db`. Set `DATABASE_URL` to use PostgreSQL.

## Data and simulation

The seed-42 generator creates 15,702 clearly synthetic observations across fermentation, tablet, sterile and liquid processes. Original accepted and quarantined submissions are preserved. Bootstrap accepts 15,654 unique finite readings and records quality events for missing values, duplicates and gaps. Re-uploading does not create duplicate sensor records.

```sh
python scripts/explore_data.py
```

This produces `data/processed/profile.json` and an engineering overview figure. Live monitoring supports Start/Pause/Stop/Reset, configurable intervals, normal/drift/spike/sensor-failure/equipment-fault scenarios and automatic investigations. Simulation state survives application restarts. Reset starts a new simulated batch without deleting historical evidence. No simulator connects to real equipment.

## Dashboard guide

- Overview: database-backed batch/process counts, anomalies, forecasts, open investigations, critical risk, risk distribution, model metrics and recent findings.
- Live monitoring: process/batch/equipment/parameter/date filters, operating bounds, excursion markers, sensor values, quality events and simulation controls.
- Anomaly detection: eight algorithms, ensemble comparison and multivariate screening. Scores are not probabilities.
- Early warnings: forecast trajectories, empirical uncertainty, distinct current excursions and next-sample model predictions.
- AI investigation: interactive execution graph, persisted input/output summaries, failures, checkpoints, jobs and recovery.
- Deviation management: evidence, hypotheses, notes, requests for more evidence, recommendation acceptance/rejection, escalation and reports.
- Root cause: correlations, observed onset ordering, historical findings, model attribution and submitted equipment/source evidence. These remain hypotheses.
- Risk assessment: configurable FMEA-inspired scales, RPN, criticality overrides, impact context and matrix.
- Model performance: held-out comparison, calibration, event latency/lead time, SHAP, drift and audited approval/activation/retirement.
- Reports & audit: eight report families in PDF/CSV/JSON and hash-chain verification.
- Configuration: process parameters/ranges/thresholds/criticality, risk policy, agent settings, users/roles/access and CSV ingestion.

Select one batch, and equipment when necessary, before running an investigation. The dashboard queues work; the embedded local worker or Docker worker processes it. Direct synchronous execution is also available through the API.

## Model lifecycle and controlled mode

Training produces Random Forest, Gradient Boosting, XGBoost and a frozen eight-method anomaly ensemble. Earlier batches train, a separate batch calibrates, and a final batch tests. Boundary-crossing targets are purged. Results include precision/recall/F1, PR/ROC-AUC where defined, false positives/negatives, calibration, event timing and batch metrics. No training-only result is represented as validation.

Models start unapproved. A reviewer/admin records an approval rationale, and an administrator separately activates a version. Controlled mode requires one approved active predictor and one approved active anomaly artifact for the selected process; anomaly inference then uses the frozen approved reference without refitting. Artifact paths/hashes and configuration signatures are checked. Approval is a prototype administrative record, not a Part 11 signature or a claim of pharmaceutical validation.

Minute-based trend projections remain separate from next-sample classifiers. Empirical residual envelopes are available only with sufficient horizon-specific history and can lose coverage under drift. Model distribution shifts and missing features route findings for human assessment. No external LLM key is configured: explanation/report functionality works through the evidence-grounded deterministic fallback.

## Docker deployment

Copy `.env.example` to `.env`; set unique `POSTGRES_PASSWORD`, `BOOTSTRAP_PASSWORD` (12+ characters) and `JWT_SECRET` (32+ random characters). Use a URL-safe database password or encode it correctly in `DATABASE_URL`.

```sh
docker compose up --build
docker compose exec backend python scripts/generate_data.py
docker compose exec backend python scripts/bootstrap.py
```

Open [Docker dashboard](http://localhost:8080). Services are PostgreSQL 16, FastAPI, a separate database-backed worker and nginx serving the React build. Migrations run before API startup. Persistent database/model volumes, health checks and pinned dependency locks are included. Redis and TimescaleDB were not necessary for this workload.

**Docker/PostgreSQL execution is not verified here because Docker is unavailable.** Run `scripts/verify_docker.ps1` on a Docker-enabled host before declaring full master-specification acceptance. The supplied CI workflow is configuration, not a remotely executed result.

## Verification

```sh
python -m pytest backend/tests -q
cd frontend
npm run build
```

Current local result: **33 backend tests passed**, TypeScript passed, production Vite build passed. The suite covers validation, all detectors, durable failure/restart/review, approved-model inference, permissions, tampering, eight report families in three formats, queue leases, persistent simulation, risk scales and backup restore-read. Browser checks use a disposable synthetic test database. PDF pages are rendered and inspected. Advisory audits returned no known vulnerabilities; retained JSON reports provide the execution evidence. Known upstream deprecation/bundle notices remain non-fatal.

## Operations and remaining regulated-use controls

See [operations](docs/operations.md) for checkpoint storage, workers, backups and recovery; [architecture](docs/architecture.md), [agents](docs/agent_documentation.md), [models](docs/model_documentation.md), [data dictionary](docs/data_dictionary.md), [API](docs/api_documentation.md), [validation](docs/validation_strategy.md), [GMP considerations](docs/gmp_considerations.md), [requirement traceability](docs/requirements_traceability.md) and [status](DEVELOPMENT_STATUS.md).

Use TLS and qualified infrastructure for any non-local deployment. Access reviews, source/instrument qualification, electronic-signature controls, immutable external audit anchoring, retention, disaster recovery, approved SOPs, IQ/OQ/PQ and independent realistic model validation remain prerequisites before regulated production use. Database owners can bypass local controls; a hash chain alone does not protect against a privileged administrator. Optional LSTM and external explanatory LLM integration are extension points, not required to run the prototype.

Self-registration is available through **Create account** on the sign-in screen. New accounts always start as viewers; administrator/reviewer access must be assigned by an administrator. In controlled mode, newly registered accounts require administrator activation before sign-in.
