# Deployment, backup and recovery

## Storage and workers

Local default: `sqlite:///./pharma.db` with a separate `pharma-workflows.db` checkpoint/journal file. `CHECKPOINT_DATABASE_URL` can override the workflow store. PostgreSQL uses separate workflow tables and transactions in the configured database. Model artifacts are trusted local files under `ml/models` and must remain synchronized with registry hashes.

`EMBEDDED_WORKER=1` starts local queue/simulation polling in the API. Docker sets it to zero and runs `python -m backend.worker` separately. Scale workers only with PostgreSQL. Claims use row locks, lease ownership and expiry. A failed job can be explicitly requeued; the same event resumes its existing graph. Do not run multiple SQLite application/worker processes against the same store.

Start/pause/stop/reset and scenario/interval changes are persisted and audited. Tick processing locks the shared state and checks the interval, preventing duplicate ticks across PostgreSQL workers. Reset starts a new simulation run and preserves historical records. Sensor failures create missing-value evidence; equipment faults create clearly synthetic source events.

## Recovery

Inspect workflow status, checkpoint and execution logs. For a failed analytical node, correct the source/configuration or restore the trusted model artifact and call `POST /api/v1/agents/workflow/{id}/recover`. Completed nodes remain checkpointed. Connection/timeouts retry twice; late pure-computation outputs are discarded. Human interrupts require the deviation review API and cannot be resumed through the recovery endpoint.

Human review and graph state are persisted separately. Identical attributed review submissions are idempotent, and matching persisted dispositions can be reconciled after an interrupted application transaction. Requesting more evidence re-enters the investigation path and refreshes submitted equipment evidence. No recovery path grants manufacturing authority.

## Backups

Stop writers for a coordinated SQLite snapshot, then:

```sh
python scripts/backup.py backups/run-2026-11-07
python scripts/backup.py backups/run-2026-11-07 --verify
```

The utility creates a new destination, preserves existing files, uses SQLite's backup API or PostgreSQL `pg_dump`, copies model artifacts and writes a SHA-256 manifest. It never prints database credentials. Restore into a **separate** database/environment and verify audit integrity, record counts, model hashes and checkpoint recovery before any cutover. PostgreSQL requires `pg_dump`; the backend image includes its client tools. Secure retention, encryption, access control and restoration approval remain infrastructure/SOP responsibilities.

The automated suite creates a separate SQLite backup, reads restored evidence and detects checksum tampering. This is prototype verification, not a qualified disaster-recovery exercise.

## Docker acceptance

Set unique secrets in ignored `.env`, then run `scripts/verify_docker.ps1`. It validates Compose, builds/starts health-checked PostgreSQL/backend/worker/frontend services, loads synthetic data and runs an authenticated live smoke test. The current environment cannot execute it because Docker is not installed. The GitHub Actions PostgreSQL job is supplied but has not been executed remotely.

Use a qualified TLS reverse proxy for non-local access; do not expose demo credentials. Audit owners, schema owners and operational users require appropriate separation. Preserve old identities by deactivation rather than deleting attributed records. Review dependency audit JSON and re-run advisory checks before deployment.
