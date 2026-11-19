# Deployment

Production uses `docker-compose.prod.yml`, PostgreSQL with pgvector, Redis, an
external model gateway network and an external Nginx reverse proxy. Releases
have a maintenance window: stop ingress and writers, back up, migrate, then start
all runtime services from the prepared images. Do not start new API/workers before
migrations, or use the development Compose file for a production upgrade.

## Prepare an upgrade

Keep real credentials in `backend/.env` and out of Git. Configure the gateway
container URL and `MODEL_GATEWAY_NETWORK`; that external network must already
exist. The external `agent_rag_models` and `agent_rerank_models` volumes must
contain the required models. See [configuration.md](configuration.md) and
[storage-maintenance.md](storage-maintenance.md). The release command upgrades an
existing healthy installation; it does not provision a new database or model cache.

Review and commit the combined source changes, run the release regressions, and
choose a unique image version. From the repository root:

```bash
# Read-only: prints the release order, makes no Docker calls.
make prod

# Builds app and frontend only; does not recreate running services.
make prod-prepare RELEASE_VERSION=v2026.11.19-rc1
```

Preparation requires a clean working tree. It builds `agent_backend:<version>`
and `agent-frontend:<version>` with the current Git revision label, and records
exact image IDs in `backups/prepared/<version>/prepared.json`. Existing tags
belonging to another revision are rejected. Keep source, images and configuration
frozen between preparation and application. A failed preparation leaves private
evidence; review it and use a fresh version for another attempt.

`NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_WS_URL` and `NEXT_PUBLIC_SITE_URL` are baked
into the frontend at build time. Set reachable public HTTPS/WSS addresses before
preparing images. For trusted HTTP-only testing, `COOKIE_SECURE=false` allows the
auth cookies; production should use TLS. Nginx must forward WebSocket Upgrade
headers for `/api/v1/ws`. Use `nginx/nginx.conf` as a template, updating domain
names and certificate paths.

## Verify the candidate

Run backend tests with Python 3.12 and a disposable PostgreSQL database, migration
upgrade/downgrade/upgrade checks, frontend unit/type checks, desktop/mobile browser
contracts, and `python3 -m unittest discover -s scripts/tests -p test_release.py`.
Tests must not discover the production `.env` or connect to production databases.
See [testing.md](testing.md) for database test setup.

The explicit live probe uses synthetic input and no business records. It makes at
most three bounded model requests and two small sandbox jobs. Use the prepared
image and the configured gateway network:

```bash
BACKEND_IMAGE=agent_backend:v2026.11.19-rc1 \
FRONTEND_IMAGE=agent-frontend:v2026.11.19-rc1 \
docker compose --env-file backend/.env -f docker-compose.prod.yml \
  run --rm --no-deps -T app python scripts/release_smoke.py --live --model --sandbox
```

The script defaults to offline mode without `--live`. Missing or incompatible
sandbox configuration is an unpassed check. Enable Python/file execution only
after the sandbox probe passes, or explicitly release with that capability disabled.
The probes do not replace a real authenticated login/chat/reconnect acceptance
check after cutover. Keep probe reports and deployment evidence private.

## Apply during maintenance

Before applying, enable maintenance at the external reverse proxy and block new
API/WebSocket traffic. Drain active jobs and check there are no external workers
or scheduled clients still writing the same database/media. The script controls
only this Compose installation; it does not configure Nginx or freeze external
integrations. Ensure backup storage has space and keep the maintenance window open
until acceptance is complete.

```bash
# Explicit operation: stops production services and changes the database.
make prod-apply RELEASE_VERSION=v2026.11.19-rc1 \
  BACKUP_DIR=backups/releases/v2026.11.19-rc1
```

`BACKUP_DIR` must be new. The command:

1. Checks the clean source revision, prepared image IDs, gateway network and healthy
   existing PostgreSQL/Redis. Records old image IDs and preserves rollback tags.
2. Stops frontend, API, task worker, Celery worker/beat, Flower and reranker.
3. Dumps the whole database, including LangGraph checkpoint tables, and archives
   media. Fully parses the database archive and checks media gzip integrity;
   records SHA-256 hashes. These checks do not replace a restore rehearsal.
4. Runs `agent db upgrade` and LangGraph checkpoint schema setup in one-shot
   containers from the new backend image while writers remain stopped.
5. Starts matching API/workers/frontend/reranker, checks exact image IDs, waits
   for readiness and checks the local Celery worker responds.

Logs, backups and manifests have restrictive permissions and are Git-ignored.
Copy validated backups to separately managed storage. Never publish interpolated
Compose configuration: it contains credentials.

## Acceptance and recovery

API `/api/v1/health` is liveness; `/api/v1/health/ready` checks database and Redis
readiness. Container health uses readiness. The task worker's health requires
recent successful database progress from both dispatch loops; process existence
alone is insufficient. Frontend `/api/health/live` checks the frontend process;
`/api/health` retains the backend connectivity check used by the UI.

Before reopening ingress, verify the expected Alembic revision, login, a normal
chat turn, tool streaming, reload/reconnect recovery, a waiting clarification,
source citations and generated file access where enabled. Check logs and queue
state. Readiness alone does not establish model or sandbox availability.

Failure before migrations restart only the previously running existing containers.
After migration starts, failure keeps all writers stopped for investigation. Keep
proxy maintenance enabled and inspect the private evidence; do not simply rerun
an apply with the same backup directory.

Older runtimes may not understand newly written LangGraph checkpoints. There is
no automatic `alembic downgrade -1` or image-only rollback. Prefer a forward fix.
If restoring is necessary, stop all writers and restore the matched pre-release
database **and media** into an isolated environment first, verify the old image
and schema/checkpoint compatibility, then perform a reviewed full recovery. Work
accepted after the backup needs reconciliation. Do not delete volumes, flush
queues, or prune shared-host images as part of rollback.

GitHub upload and production deployment are separate operations. The release
script performs neither a Git push nor reverse-proxy maintenance changes.
