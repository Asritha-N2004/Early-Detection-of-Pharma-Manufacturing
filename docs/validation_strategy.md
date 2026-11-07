# Verification and validation strategy

## Executed prototype checks

The current backend suite has 33 passing tests. It uses a unique isolated database selected before application imports, never the main local demo database. Coverage includes all eight detectors and ensemble, multivariate relationship shifts, temporal feature windows, risk arithmetic/scales/critical overrides, request validation and secret redaction, auth/role denials, session revocation and identity deactivation, original-quality preservation, duplicate reading/event protection, relational context integrity, model artifact tampering, calibration and held-out evaluation.

Workflow tests reconstruct saver/graph objects from persisted bytes, resume human interrupts, inject node failure/deadlines, reject invalid transition outputs and recover through the API without replaying completed nodes. Integration tests approve and activate prediction/anomaly versions, verify controlled-mode gating, retrieve source evidence, request more evidence, record idempotent human decisions, exercise all eight report families in all three formats, reclaim expired worker leases and run the persistent simulator into an abnormal investigation.

TypeScript checks and Vite production builds pass. Browser QA uses a disposable copy of test data and inspects desktop/mobile layouts, the interactive graph, model approval interaction, settings and roles, reports and review controls. Representative PDF pages are rendered with Poppler and visually inspected; text extraction alone is not treated as layout verification. Advisory audit JSON records are retained in `docs`. Backup checks compare SHA-256 manifests, restore-read a separate SQLite copy, and detect tampering.

## Deployment acceptance still required

Docker/PostgreSQL cannot be executed here because Docker is unavailable. YAML parsing, authored health checks and CI configuration are not claimed as successful deployment. Run `scripts/verify_docker.ps1` on a Docker-enabled host, run the PostgreSQL CI suite, verify worker recovery and permissions there, and fix any platform-specific findings before declaring full master-specification acceptance.

The GitHub workflow is supplied but has not been run remotely. SQLite verification does not prove PostgreSQL behavior. Perform load/fault testing and backup/restore qualification on the intended infrastructure before operational use.

## Regulated-use validation remains external

Prototype verification is not IQ/OQ/PQ or pharmaceutical computerized-system validation. Quality personnel must approve intended use, requirements/risk traceability, source integrations, operating ranges, criticality rules, model/threshold selection, audit review, user management, backup/retention, electronic-signature controls, incident handling, change control and periodic review. Model validation needs independent realistic batches, source shifts, sensor noise/gaps, stage-specific contexts and adjudicated event definitions. Synthetic held-out metrics cannot establish manufacturing or patient-safety performance.
