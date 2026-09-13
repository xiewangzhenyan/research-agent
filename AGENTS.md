# AGENTS.md

This file provides guidance for AI coding agents (Codex, Copilot, Cursor, Zed, OpenCode).

## Project Overview

**Research Agent** — LSPRAI's research knowledge base and AI assistant, with native
knowledge retrieval, persistent tasks, source citations, and bounded multi-role collaboration.

**Stack:** FastAPI + Pydantic v2, PostgreSQL
, JWT + API Key auth, Redis
, pydantic_ai (openai), Next.js 15 (i18n)

## Commands

```bash
# Run server
cd backend && uv run uvicorn app.main:app --reload

# Tests & lint
pytest
ruff check . --fix && ruff format .

# Migrations
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "Description"
```

## Project Structure

```
backend/app/
├── api/routes/v1/    # Endpoints
├── services/         # Business logic
├── repositories/     # Data access
├── schemas/          # Pydantic models
├── db/models/        # DB models
├── agents/           # AI agents
└── commands/         # CLI commands
```

## Key Conventions

- `db.flush()` in repositories, not `commit()`
- Services raise `NotFoundError`, `AlreadyExistsError`
- Separate `Create`, `Update`, `Response` schemas
- Commands auto-discovered from `app/commands/`

## Deployment disk budget

- Reuse build cache; rebuild only changed services. Do not use `--no-cache` routinely.
- Keep all images referenced by any container, plus the newest two unused rollback
  images for each of `agent_backend` and `agent-frontend`. After a healthy release,
  review `python3 infrastructure/maintenance/prune_images.py` before applying its plan.
- Never use host-wide image/volume/system prune for project cleanup. Preserve model
  caches, uploads, databases and source/database backups. Other projects share this host.
- Build cache may be trimmed after builds finish with
  `docker builder prune --force --filter until=24h --max-used-space 4GB` (this is host-wide
  regenerable cache; recent/in-use records can keep usage above the target).
- Avoid recursive ownership changes on dependency trees in runtime images; use
  `COPY --chown` and keep source separate from dependencies.
- See `docs/storage-maintenance.md` for the retention and audit procedure.

## GitHub synchronization

- Canonical public repository: `https://github.com/xiewangzhenyan/research-agent`.
- The owner's updated preference (2026-09-13) is batched delivery. Accumulate local
  changes and run relevant tests; do not push to GitHub, rebuild Docker images or
  deploy after every individual improvement. Local checkpoint commits are optional.
- Batch upload and deployment at a coherent feature/release milestone or when the
  owner asks to publish. State what is included, review the combined diff and run
  the relevant regression checks. Do not treat every small task as a release milestone.
- Keep actual credentials, `.env` files, databases, uploads, model caches, deployment
  evidence and internal research notes out of Git. Preserve required license notices.
- Keep `git config --local researchAgent.autoPush false`. The existing installer
  enables auto-push, so restore this setting immediately after any hook reinstall.
  Keep the pre-push audit hook enabled. Do not re-enable auto-push without an explicit
  change to the owner's preference.
- Never force-push, silently discard remote changes or claim an unpushed change is synced.
  At a batch release, push explicitly with `git push origin main` and verify the remote
  result; a failed push does not undo local commits. The auto-push helper intentionally
  does nothing while auto-push is disabled.
- Git sync does not deploy the application. Report code upload and live deployment separately.
- See `docs/github-sync.md` for setup, pause controls and verification.

## More Info

- `docs/architecture.md` - Architecture details
- `docs/adding_features.md` - How to add features
- `docs/testing.md` - Testing guide
- `docs/patterns.md` - Code patterns
