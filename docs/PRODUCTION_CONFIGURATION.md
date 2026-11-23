# FlowSentry — Production Configuration Reference

This document maps every runtime, security, proxy, database, worker, and frontend configuration knob in FlowSentry to exact code paths.

Use [`.env.production.example`](../.env.production.example) as the starting template for staging and production hosts. **Never commit `.env` or `.env.production`**.

---

## 1. Environment Variables Reference (`backend/app/core/config.py`)

| Variable | Required in Production | Example / Default | Purpose & Constraints |
|---|---|---|---|
| `APP_NAME` | No | `FlowSentry` | API title |
| `ENVIRONMENT` | **Yes** | `production` (or `staging`) | Enables fail-closed `validate_production_guards`, disables OpenAPI/Swagger (`/docs`, `/redoc`, `/openapi.json`) when `production` |
| `DEBUG` | **Yes (`false`)** | `false` | Must be `false` when `ENVIRONMENT=production`; controls log verbosity (`INFO` vs `DEBUG`) |
| `API_V1_PREFIX` | No | `/api/v1` | REST API base prefix |
| `ALLOWED_ORIGINS` | **Yes** | `https://app.flowsentry.example` | Comma-separated CORS allowlist; `*` is forbidden when `ENVIRONMENT=production` |
| `ENCRYPTION_KEY` | **Yes** | Generated via `scripts/generate_keys.py` | 32-byte URL-safe base64 Fernet key encrypting n8n API keys and Slack/Email notification configs; rotating invalidates stored encrypted blobs unless migrated |
| `LOCAL_DEV_JWT_SECRET` | **No (leave blank)** | `""` | Strictly rejected in `ENVIRONMENT=production` (`/api/v1/auth/dev-token` returns `404`) |
| `ALLOW_PRIVATE_INTEGRATION_HOSTS` | No (`false`) | `false` | Keep `false` to block RFC1918/loopback SSRF targets; cloud metadata (`169.254.0.0/16`, `fe80::/10`, `0.0.0.0/8`, `100.64.0.0/10`) is **always** blocked |
| `AUTH_MODE` | **Yes (`supabase`)** | `supabase` | Must equal `supabase` when `ENVIRONMENT=production` |
| `SUPABASE_URL` | **Yes** | `https://<ref>.supabase.co` | Used to derive expected issuer (`${SUPABASE_URL}/auth/v1`) and JWKS URI |
| `SUPABASE_JWT_SECRET` | Optional | `""` | Only needed for legacy `HS256` Supabase projects; `RS256`/`ES256` projects use JWKS automatically |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | **Yes** | Strong unique password | PostgreSQL container credentials |
| `DATABASE_URL` | **Yes** | `postgresql+psycopg://...` | SQLAlchemy engine (`pool_pre_ping=True`, `pool_size=10`, `max_overflow=20`, `pool_recycle=1800`, `pool_timeout=30`) |
| `REDIS_URL` | **Yes** | `redis://redis:6379/0` | API rate limiter & `/ready` connectivity check |
| `CELERY_BROKER_URL` | **Yes** | `redis://redis:6379/1` | Celery task queue |
| `CELERY_RESULT_BACKEND` | **Yes** | `redis://redis:6379/2` | Celery task result backend |
| `AI_PROVIDER` | Optional | `openai` \| `gemini` \| `none` | Selects live AI provider; falls back to `DeterministicFallbackAnalyzer` if keys absent or provider fails |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | Optional | `gpt-4o-mini` | OpenAI chat completions key & model |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | Optional | `gemini-2.5-flash` | Gemini `generateContent` key (`x-goog-api-key` header) & model |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` | Optional | Port `587` or `465` | External SMTP relay for email alerts (`SMTP_USE_TLS=true`) |
| `SMTP_FROM_EMAIL` | Optional | `alerts@yourdomain.com` | Verified sender address |
| `NEXT_PUBLIC_API_URL` | **Yes (build-time)** | `""` (same-origin) or `https://api.yourdomain.com` | Inlined during `next build`; set empty (`NEXT_PUBLIC_API_URL=`) when serving behind same-origin Nginx |
| `NEXT_PUBLIC_AUTH_MODE` | **Yes (build-time)** | `supabase` | Enables Supabase login/register UI |
| `NEXT_PUBLIC_SUPABASE_URL` | **Yes (build-time)** | `https://<ref>.supabase.co` | Public Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | **Yes (build-time)** | Supabase anon public key | Public client key only (NEVER put secrets in `NEXT_PUBLIC_*`) |

---

## 2. Reverse Proxy, TLS & Trusted Proxy Rules

- **TLS Template:** Use [`infrastructure/nginx/nginx.tls.conf.example`](../infrastructure/nginx/nginx.tls.conf.example) when terminating TLS directly on the Docker host (e.g., Let's Encrypt/Certbot), or keep [`infrastructure/nginx/nginx.conf`](../infrastructure/nginx/nginx.conf) behind a managed TLS load balancer (Cloudflare/ALB/Caddy).
- **Firewall Isolation (Important):** Because FastAPI extracts client IPs for rate limiting (`backend/app/api/deps.py`: `_extract_client_ip`) from `X-Real-IP` / `X-Forwarded-For` and Uvicorn runs with `--proxy-headers`, **do NOT expose ports `8000`, `3000`, `5432`, or `6379` directly to the public internet**. Expose only Nginx ports `80`/`443` publicly and keep internal ports bound to `127.0.0.1` or internal VPC security groups.
- **Security Headers:** Both Nginx (`nginx.conf` / `nginx.tls.conf.example`) and FastAPI (`backend/app/main.py`) set `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, and `Permissions-Policy`. `nginx.tls.conf.example` adds `Strict-Transport-Security` over HTTPS.

---

## 3. Infrastructure Persistence, Logging & Health Checks (`docker-compose.yml`)

- **PostgreSQL 16:** Persisted in named volume `postgres_data`; healthcheck via `pg_isready`. Schema migrations run automatically on `backend` startup (`alembic upgrade head`).
- **Redis 7:** Configured with `--appendonly yes` (AOF persistence) persisted in `redis_data` so queued Celery jobs survive container restarts.
- **Container Log Rotation:** All services use `json-file` driver with `max-size: "10m"` and `max-file: "5"`.
- **Health Endpoints & Worker Checks:**
  - `GET /health` -> lightweight process liveness (`{"status": "ok", "service": "flowsentry-api"}`).
  - `GET /ready` -> checks PostgreSQL (`SELECT 1`) and Redis (`PING`); returns HTTP `503` if PostgreSQL is unreachable.
  - `worker` healthcheck -> `celery -A app.workers.celery_app inspect ping`.
  - `beat` healthcheck -> verifies `/tmp/celerybeat.pid` created by `--pidfile=/tmp/celerybeat.pid`.
- **Background Schedules (`backend/app/workers/celery_app.py`):**
  - `poll_enabled_integrations`: every `120s`
  - `evaluate_due_outcome_monitors`: every `60s`
  - `evaluate_frequency_anomalies`: every `180s`
  - `cleanup_expired_records`: every `86400s` (prunes old executions & monitor runs per `Workspace.plan` retention limits)

---

## 4. Backup & Restore Verification

- Backup script: [`scripts/backup_db.sh`](../scripts/backup_db.sh) creates timestamped gzipped `pg_dump` archives under `./backups/` (gitignored).
- Restore verification script: [`scripts/restore_db.sh`](../scripts/restore_db.sh) restores an archive into a scratch verification database (`flowsentry_restore_verify` by default) so backups can be tested non-destructively before touching live production databases.
