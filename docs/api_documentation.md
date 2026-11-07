# API guide

Interactive schemas are at `http://localhost:8010/docs`. All application routes begin `/api/v1/`. `GET /health` is public and checks database/checkpoint connectivity. Login creates a two-hour signed JWT plus a persisted revocable session. Send `Authorization: Bearer TOKEN`. Logout and account deactivation revoke access. Validation responses omit original password inputs. Five failed logins within fifteen minutes lock further login attempts temporarily.

| Group | Routes | Permissions |
|---|---|---|
| Auth/users | POST auth/login, auth/logout; POST users; GET users, roles; POST users/{id}/role, users/{id}/access | Admin manages users; current role is loaded from database |
| Data | POST data/ingest, data/upload; GET data/records, data/quality | Write admin; read authenticated |
| Processes | GET processes, processes/{id}/parameters; POST processes | Configure admin |
| Monitoring | GET monitoring/live, monitoring/history, monitoring/trends, monitoring/catalog, monitoring/drift, monitoring/configuration | Authenticated |
| Analysis | POST anomaly/detect, prediction/run, agents/workflow/run | Admin/reviewer |
| Durable workers | POST agents/workflow/enqueue; GET agents/jobs; POST agents/jobs/{id}/retry | Queue/retry admin/reviewer |
| Workflow state | GET agents/workflows, agents/workflow/{id}, agents/workflow/{id}/checkpoint, agents/execution-logs, agents/graph, agents/contracts; POST agents/workflow/{id}/recover | Recover admin/reviewer; other reads authenticated |
| Findings | GET anomaly/results, anomaly/{id}, prediction/results, deviations, deviations/{id} | Authenticated |
| Review | POST deviations/{id}/review, deviations/{id}/escalate | Reviewer/admin; attributed rationale required |
| Risk | POST risk/assess; GET risk/assessments, risk/configuration | Assess reviewer/admin; read authenticated |
| Models | GET models, models/performance; POST models/train; POST models/{id}/review | Train/activate admin; approve/reject reviewer/admin |
| Reports | POST reports/generate; GET reports, reports/{id} | Generate reviewer/admin; read authenticated |
| Evidence | POST equipment/events; GET equipment/events | Write reviewer/admin; read authenticated |
| Settings | GET settings; POST settings/risk, settings/agents, settings/models | Admin; changes audited |
| Simulation | GET simulation; POST simulation | Control admin; read authenticated |
| Audit/overview | GET audit/logs, dashboard | Audit reviewer/admin; dashboard authenticated |

JSON ingestion is `{records:[measurement,...]}`; CSV uploads use multipart field `file`. Limits are 8 MB and 20,000 rows. Accepted records preserve their originals. Unknown units/parameters, missing values and physical-invalidity cases are quarantined, and gaps/duplicates create quality records.

Analysis is `{process,batch,equipment,event_id,method,horizon}`. Batch/equipment mixing is rejected unless explicitly filtered. Repeated identical event keys return the existing result; conflicting reuse returns 409. Enqueued jobs return a job ID; poll jobs or workflow state for completion. Recover failed checkpoints using the recovery endpoint or the original event request. Recovery cannot bypass a human-review interrupt.

Review is `{decision,notes}` with accept/reject/more_evidence/escalate and at least ten rationale characters. Identical submissions are idempotent. Reports accept `{family,format,deviation_id?,process?,batch?,model_id?}`. Families are deviation, early_warning, batch_monitoring, investigation, root_cause, risk, process_performance and model_performance. Formats are json/csv/pdf. Downloads are authenticated.

Model review is `{action,rationale}` with approve/reject/activate/retire. Activation requires prior explicit approval and verified artifact integrity. Prediction and anomaly tasks are activated independently. Training optionally accepts `{process}`. Controlled inference requires approved active versions for both tasks.

Readings support process, batch, equipment, parameter, timezone-aware start/end, limit and offset. Analytical lists expose bounded limit/offset pagination; execution logs merge durable journal entries with historical records. Simulation accepts `{action,process,scenario,interval}`, including a deterministic `step` for test execution. Reset preserves old simulated batches.

Rate limiting is local to each API process (300 requests/minute/client IP); use a trusted gateway for shared deployment throttling. Docker does not expose the backend port publicly. The system has no manufacturing-control, batch-release, formal deviation-closure or electronic-signature endpoint.

`POST /api/v1/auth/register` accepts only username/password and creates a hashed, audited viewer account. Client-supplied roles are rejected. Controlled-mode registrations start inactive pending administrator activation.
