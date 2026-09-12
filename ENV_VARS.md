# Environment variables

Reference for `agent` runtime configuration. The
authoritative source is `backend/.env.example` — this doc explains what each
group is for and which are required vs optional.

> Quick start: copy `backend/.env.example` to `backend/.env` and fill in the
> blanks marked **Required**. Defaults are sensible for local development.

## Project

| Variable | Required | Default | Description |
|---|---|---|---|
| `PROJECT_NAME` | optional | `agent` | Used in logs, OpenAPI title, email templates |
| `DEBUG` | optional | `true` | When `true`, FastAPI returns full tracebacks |
| `ENVIRONMENT` | optional | `local` | Free-form tag: `local` / `staging` / `production` |
| `TIMEZONE` | optional | `Asia/Shanghai` | IANA TZ name (e.g. `Europe/Warsaw`) |
| `BACKEND_URL` | optional | `http://localhost:38001` | Used by frontend BFF + email link generation |
| `FRONTEND_URL` | optional | `http://localhost:38000` | Used by password-reset / magic-link emails |

## Auth & secrets

| Variable | Required | Default | Description |
|---|---|---|---|
| `SECRET_KEY` | **required in prod** | (generated) | JWT signing key. Rotating invalidates all tokens |
| `API_KEY` | **required in prod** | (generated) | Static admin/service-to-service key for `X-API-Key` header |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | optional | `30` | JWT access token lifetime |
| `REFRESH_TOKEN_EXPIRE_MINUTES` | optional | `10080` | JWT refresh token lifetime (7 days) |

## Database
| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | **required** | `postgresql+asyncpg://...` | Full async connection string |
| `DB_POOL_SIZE` | optional | `5` | Number of long-lived connections |
| `DB_MAX_OVERFLOW` | optional | `10` | Burst capacity above pool size |

## LLM / AI

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | **required** | — | From platform.openai.com |
| `OPENAI_BASE_URL` | optional | `https://api.openai.com/v1` | OpenAI-compatible API base URL |
| `AI_MODEL` | optional | `gpt-5.5` | Default model used by agent (provider-specific) |
| `AI_AVAILABLE_MODELS` | optional | JSON list | Models shown in the chat model selector |
| `LOGFIRE_TOKEN` | optional | — | When set, ships traces to Logfire (logfire.pydantic.dev) |

## Redis

| Variable | Required | Default | Description |
|---|---|---|---|
| `REDIS_URL` | **required** | `redis://localhost:6379/0` | Used by Celery broker, session store |

## Frontend (`frontend/.env.local`)

Separate from the backend `.env` above — `frontend/README.md` has the full table.
The two that decide whether a deployment works at all:

| Variable | Read by | Description |
|---|---|---|
| `NEXT_PUBLIC_WS_URL` | browser | WebSocket origin for chat. Inlined at **build** time, so it needs a rebuild to change, and it must be an address the browser can reach — not a Docker service name |
| `COOKIE_SECURE` | server | `Secure` flag on the auth cookies. Unset follows `NODE_ENV`. A browser drops a `Secure` cookie served over plain `http://`, which makes every request after login return 401 — set `false` only for `http://` on a trusted network |

## Validation

```bash
# Confirm settings load without errors:
cd backend && uv run python -c "from app.core.config import settings; print(settings.model_dump_json(indent=2))"
```

If any **Required** var is missing, FastAPI raises `pydantic_settings.SettingsError` on startup — check the message for which field.
