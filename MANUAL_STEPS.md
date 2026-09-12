# Manual setup steps for agent

The generator created the code. These are the **one-time external setup steps**
that can't be automated — accounts to create, keys to copy, services to provision.

> Skip ahead to "After every deploy" at the bottom for things you'll re-do
> regularly. Items above are one-time per environment.

---

## Secrets

```bash
cp backend/.env.example backend/.env
```

Then in `backend/.env`:

- [ ] **`SECRET_KEY`** — replace with a fresh value: `openssl rand -hex 32`
- [ ] **`API_KEY`** — replace with a fresh value: `openssl rand -hex 32`

These are used to sign JWTs and authenticate service-to-service calls. Rotate at every environment promotion (dev → staging → prod each get their own).

## PostgreSQL

- [ ] Provision a PostgreSQL ≥ 14 instance (local: `docker compose up -d db`; managed: Neon / Supabase / RDS / Cloud SQL).
- [ ] Set `DATABASE_URL` in `.env` to the **async** connection string: `postgresql+asyncpg://user:pass@host:5432/dbname`.
- [ ] Run migrations: `cd backend && uv run alembic upgrade head`.

## OpenAI

- [ ] Create API key at https://platform.openai.com/api-keys.
- [ ] Set `OPENAI_API_KEY` in `.env`.
- [ ] (Optional) Set spending limit on OpenAI dashboard to avoid surprise bills.

## Redis

- [ ] Local: `docker compose up -d redis` (already in compose file).
- [ ] Managed: Upstash / Redis Cloud / ElastiCache. Set `REDIS_URL` in `.env`.

## Logfire (Pydantic observability)

- [ ] Create account at https://logfire.pydantic.dev.
- [ ] Run `uv run logfire auth` once locally to bootstrap.
- [ ] Get write token → set `LOGFIRE_TOKEN` in `.env` for non-local environments.

---

## After every deploy

- [ ] Run database migrations: `alembic upgrade head` (CI step or post-deploy job).
- [ ] Smoke test `/api/v1/health` returns `{"status": "ok"}`.
- [ ] Frontend loads, login → dashboard flow works.
- [ ] Logs flowing to your aggregator.

---

## Where to find more

- `ENV_VARS.md` — exhaustive env var reference
- `docs/deploy.md` — platform-specific deployment recipes
- `SECURITY.md` — security model + production hardening checklist
- `CONTRIBUTING.md` — dev environment setup
- `docs/architecture.md` — codebase layered architecture rules
