# Master-specification traceability

This matrix maps requested prototype capabilities to actual implementation and evidence. It does not replace pharmaceutical validation documentation.

| Master section | Implementation | Verification |
|---|---|---|
| 1-2 Executable decision-support platform and safety boundary | FastAPI, React, durable SQL state, no manufacturing-control interfaces; all findings remain potential | API and workflow integration tests; browser review controls |
| 3 Four process families and extensible registry | registry.py, process configuration API/UI, all requested parameter families | 15,702 generated observations; ingestion for all four processes |
| 4-6 Event-driven analytical agents and LangGraph | workflow.py, CONTRACTS, strict state, SQL saver, conditional graph, human interrupts, retries/deadlines and recovery | Durable reconstruction, fault injection, invalid-transition and API recovery tests |
| 5.1 Data ingestion | JSON/CSV/REST/simulator, original preservation, quarantine, identity hashes and gaps | Validation, duplicate, missing/unit/physical checks and simulation tests |
| 5.2-5.3 Monitoring and eight anomaly methods | analytics.py, approved_anomaly.py, features.py, multivariate joint screening and detector comparison | Each method, normal data, shift test and approved frozen-artifact inference |
| 5.4 Prediction | RF/GB/XGBoost, next-sample target, linear time horizon and empirical envelope | Held-out chronological evaluation, calibration, event timing and batch metrics |
| 5.5 Root cause | Correlation, first excursion, historical references, equipment evidence, TreeSHAP and hypotheses | Source retrieval, evidence-request loop and model runtime tests |
| 5.6-5.8 Risk, investigation and decision support | Configurable scales/criticality, missing-evidence recommendations, retained conflicting/current/future signals and human routing | RPN, override, scale and review tests |
| 5.9 Reporting | Eight families, PDF/CSV/JSON, attribution and review notices | All 24 family/format combinations; rendered representative PDF |
| 5.10 Quality/audit | User and model/configuration events, independent execution journal, append-only chained audit | Chain verification, forbidden mutation and role/session tests |
| 7 Synthetic engineering data | generate_data.py, CSV datasets, reproducible labels/noise/drift/faults/gaps | Executed generator and profile/EDA output |
| 8 ML lifecycle | Versioned hashed artifacts, approved activation, calibration, SHAP, continuous drift signals, latency/lead time | Training/inference, tamper rejection, controlled dual-model gating |
| 9 REST API and security | Required routes plus worker/model governance/source/config/session APIs | TestClient integration, permissions, redaction and health checks |
| 10 Eleven UI sections | main.tsx and AdvancedPanels.tsx, real API data, charts/forms/graph/exports | TypeScript/Vite build and isolated desktop/mobile browser QA |
| 11 Normalized schema and migrations | Domain tables, evidence documents, typed projections, context FKs, migrations 0001-0005 | Existing-record backfill, 31 local tables, 35 FK links, database tests |
| 12 GMP/data integrity | Provenance, attributable review, version/config history and explicit qualification gaps | GMP design document; no claim of compliance or regulated signature |
| 13 Cybersecurity | Hashing, signed/revocable sessions, role checks, finite/typed input, limits, CORS, trusted artifact paths and advisory checks | Auth/access/tamper tests; backend/frontend audit JSON |
| 14 Real-time simulation | Persistent state, configurable intervals, five scenarios, automatic investigation | Ten-step abnormal simulation test and lifecycle controls |
| 15-16 Structure and automated verification | Modular backend/frontend/services/scripts/docs; 33 tests | Executed suite and builds; no placeholder-only files |
| 17 Docker deployment | PostgreSQL, backend, worker, frontend, volumes, health checks and verification script | YAML parsed; **runtime blocked by missing Docker** |
| 18-19 Documentation and status | README, architectural Mermaid, agents/models/data/API/operations/GMP/validation/status | Updated after executed checks |
| 20 Final acceptance | All software acceptance paths implemented | **Cannot declare full completion before Docker/PostgreSQL execution passes** |
| 21-22 Engineering and persistence | Traceable deterministic agents, evidence limits, original data preservation, tests and maintained status | Working code and executed evidence listed above |

Optional LSTM, TimescaleDB and Redis are not required for this workload. External LLM explanations use the allowed deterministic fallback because no external model key is configured. Regulated qualification and approved procedures are documented prerequisites, not properties the prototype claims to possess.
