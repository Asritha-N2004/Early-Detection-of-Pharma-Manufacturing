# Vercel deployment

Production URL: https://pharmasignal-manufacturing.vercel.app

Project dashboard: https://vercel.com/resum-projects/pharmasignal-manufacturing

`vercel.json` routes `/api/*` and `/health` to the Python container service and all other paths to the Vite frontend. One production daemon runs `backend.worker` in `iad1`. API and worker share the isolated free Neon PostgreSQL database provisioned for this project. The worker consumes the existing leased SQL queue. Vercel Services, containers and daemons are currently beta features.

`MODEL_STORAGE=database` stores server-trained artifacts as SHA-256-addressed PostgreSQL binary records. Inference verifies durable bytes before writing a temporary cache under `/tmp/pharmasignal-models`. Local development continues using trusted local artifacts. New migration `0006` creates the artifact table.

The deployment has fresh `JWT_SECRET` and `BOOTSTRAP_PASSWORD` variables. The bootstrap administrator is `admin`. Its generated password is available to the project owner through Vercel environment settings and the ignored local `.env.vercel.secrets` file. Do not publish this file or reuse the local application password. Public registration creates viewer accounts and requires an eight-character minimum password.

Verification: all 47 backend tests passed; Vercel's frontend TypeScript/Vite and container builds passed; six migrations completed on hosted PostgreSQL; live health and authenticated read-only API checks passed, including audit-chain integrity. Account creation form visually inspected in production. With explicit user approval, 15,654 synthetic readings were imported across four processes, with 24 duplicate inputs skipped and 282 data-quality events recorded. Four starter investigations reached awaiting_human_review. Post-import live checks passed. No local database or existing account was uploaded.

For subsequent deployments use `vercel deploy --prod --scope resum-projects` from the linked root. Use `vercel daemons inspect worker --scope resum-projects` to inspect readiness. Keep database backups external to ephemeral containers. Monitor Vercel compute and Neon quotas, especially provisioned worker memory.
