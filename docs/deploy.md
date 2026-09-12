# Deployment

The project uses Docker Compose, GitHub Actions and an external Nginx reverse proxy.

- ✅ Docker / `docker-compose.yml`
- ❌ No Kubernetes manifests
- CI: `github`
- Reverse proxy: Nginx


---


## Docker Compose (single host)

For staging or small production:

```bash
# 1. Configure
cp backend/.env.example backend/.env
# Edit backend/.env with production values (see ENV_VARS.md)

# 2. Build + start
docker compose up -d --build

# 3. Apply migrations
docker compose exec app uv run alembic upgrade head


# 4. Verify
curl http://localhost:38001/api/v1/health
# Frontend: http://localhost:38000
```


### Serving from a host that isn't localhost

The defaults assume the browser runs on the Docker host. Opening the app from
another machine (a LAN IP, a staging box, a tunnel) needs two things set, and
both fail in a way that looks like something else:

```bash
# In the .env next to docker-compose.prod.yml
PUBLIC_HOST=10.0.0.5     # an address the BROWSER can reach
COOKIE_SECURE=false      # ONLY if you serve over plain http:// (see below)
```

```bash
# NEXT_PUBLIC_* is inlined into the bundle, so this needs a real rebuild
docker compose -f docker-compose.prod.yml build frontend
docker compose -f docker-compose.prod.yml up -d frontend
```

1. **`NEXT_PUBLIC_*` is baked in at build time.** Next.js inlines those values
   into the JavaScript the browser downloads, so a runtime env var cannot change
   them — `docker-compose.prod.yml` passes them as `build:` args instead. Miss
   this and the chat socket dials `ws://localhost:38001` from
   the visitor's own machine and the input stays disabled ("Offline").
2. **The auth cookies are `Secure` in production, and a browser silently drops a
   `Secure` cookie that arrives over `http://`.** Login looks like it worked (the
   user comes back in the response body) and then every request carrying no
   cookie answers 401, `/api/auth/me` included, so the token never refreshes.
   TLS is the real fix; `COOKIE_SECURE=false` is the escape hatch for a trusted
   network.

Reaching the backend matters too: the chat socket is opened by the browser
directly against `NEXT_PUBLIC_WS_URL`, so either publish the backend port or
route `/api/v1/ws` through your proxy with the `Upgrade` headers set.

### Reverse proxy
Nginx config in `nginx/nginx.conf` proxies `/` → frontend, `/` on `api.DOMAIN` → backend, and `/api/v1/ws` → backend WebSocket. Update `server_name` and the TLS cert paths there.




## Platform-specific quickstarts

### Fly.io

```bash
fly launch --name agent-backend --region waw
fly postgres create --name agent-db
fly postgres attach agent-db
# Redis: use Upstash (`fly redis create`) or Fly's Tigris
fly secrets set $(cat backend/.env | grep -v '^#' | xargs)
fly deploy
```

### Railway

1. Connect repo, pick Dockerfile-based deploy.
2. Add env vars from `backend/.env` to Railway service.
3. Provision PostgreSQL plugin → `DATABASE_URL` auto-injected.
4. Provision Redis plugin → `REDIS_URL` auto-injected.
5. Deploy.

### Render

1. Create Web Service → docker, point at `backend/Dockerfile`.
2. Create Static Site for frontend (build cmd: `bun install && bun run build`, output dir: `.next`).
3. Create PostgreSQL → copy DATABASE_URL.
4. Add env vars; deploy.

### Vercel (frontend only)

The frontend is a Next.js app — works on Vercel out of the box.

```bash
cd frontend
vercel
```

Set `BACKEND_URL`, `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_WS_URL` (`wss://…`) and
`NEXT_PUBLIC_SITE_URL` in the Vercel dashboard, pointing at your backend host,
then redeploy — the `NEXT_PUBLIC_*` ones are only picked up by a fresh build.


---

## Environment validation in production

Before promoting to prod, run:

```bash
docker compose exec app uv run python -c "from app.core.config import settings; print('OK')"
```

Catches missing required env vars early. See `ENV_VARS.md` for the full list.

## Post-deploy checks

- [ ] `/api/v1/health` returns `{"status": "ok"}`
- [ ] `alembic current` matches expected revision
- [ ] Frontend renders, login flow works end-to-end
- [ ] Logs flowing to your aggregator + Logfire receiving traces
- [ ] Reverse proxy enforces HTTPS

## Rollback

- **Schema:** `alembic downgrade -1` rolls back one migration. Test on staging first.
- **Code:** redeploy previous image tag. Pin tags (`v1.2.3`), never deploy `latest` to prod.
- **Data:** restore from your most recent backup; verify `alembic current` matches the data version.
