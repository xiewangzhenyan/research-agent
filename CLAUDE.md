# CLAUDE.md

## Project Overview

**agent** - An AI workspace with native knowledge retrieval, persistent tasks,
source citations, and bounded multi-role collaboration.

**Stack:** FastAPI + Pydantic v2, PostgreSQL (async via asyncpg)
, JWT + API Key auth, Redis, PydanticAI, Celery, Next.js 15 (i18n)

## Commands

```bash
# Backend
cd backend
uv run uvicorn app.main:app --reload --port 38001
uv run pytest
uv run pytest tests/test_file.py::test_name -v
uv run ruff check . --fix && uv run ruff format .
uv run ty check

# Database migrations
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "Description"

# Frontend
cd frontend
bun dev
bun test
bun run lint

# Docker
docker compose up -d
```

## Hard Boundaries

Non-obvious rules that are easy to violate and cross-cutting enough to state up front:

- Repositories use `db.flush()` + `db.refresh()`, **never** `db.commit()` — the session auto-commits via `get_db_session`.
- Routes call services only — **never** import or call repositories directly.
- Route handlers return `-> Any`; serialization is handled by `response_model` (avoids double Pydantic validation).
- `datetime.now(UTC)`, never `datetime.utcnow()`.
- `secrets.compare_digest()` for API key comparison, never `==`.

## Detailed Conventions

Path-scoped guidance lives in `.claude/rules/*` and loads automatically when you edit matching files — it is intentionally NOT repeated here:

- `architecture.md` — Routes → Services → Repositories, dependency injection, thin vs. thick domains
- `schemas-models.md` — Pydantic v2 schemas (`*Create`/`*Update`/`*Read`/`*List`), SQLAlchemy models
- `api-conventions.md` — REST structure, status codes, response format, pagination, auth
- `exceptions-security.md` — domain exceptions (`NotFoundError`, etc.), JWT, RBAC
- `code-style.md` — formatting, naming, imports, type hints
- `testing.md` — test structure, fixtures, async patterns
- `frontend.md` — Next.js 15 conventions

Longer-form docs: `docs/architecture.md`, `docs/adding_features.md`, `docs/testing.md`, `docs/patterns.md`.
