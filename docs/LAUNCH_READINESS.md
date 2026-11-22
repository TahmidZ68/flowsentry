# FlowSentry — Phase 10 Production Launch Readiness & Operations Runbook

**Launch Gate Date:** 2026-11-22  
**Phase Status:** Phase 10 Prepared (Local Docker `--profile prod` Verified; External Cloud Deployment & Paid Services Pending Explicit Authorization)

---

## 1. Release Gate Summary (Phases 6–10)

| Gate Area | Verification Basis | Outcome |
|---|---|---|
| **Security & Dependency CVEs** | `pip-audit -r requirements.txt` (0 CVEs), `npm audit` (0 CVEs across 552 packages), SSRF IPv4-mapped IPv6 & DNS-pinned `httpcore` guard, Supabase `issuer` enforcement, `X-API-Key` scoped ingestion auth, 1 MB webhook limit, inline secret redaction, `x-goog-api-key` header hygiene | **PASS** |
| **Backend Automated Tests & Lint** | `pytest -v` (37 passed, 0 failed), `ruff check app tests` (`All checks passed!`) | **PASS** |
| **Frontend Checks & Production Build** | `tsc --noEmit` (0 errors), `vitest run` (10/10 passed), `eslint .` (0 errors), `next build` (exit 0) | **PASS** |
| **Docker Compose Full Stack (`--profile prod`)** | All 7 containers (`postgres:16-alpine`, `redis:7-alpine`, `backend`, `worker`, `beat`, `frontend`, `nginx:1.27-alpine`) built & running healthy; Alembic `upgrade -> downgrade -> upgrade` on Postgres 16; `pg_dump` backup & restore verified; Celery Beat -> Worker live task execution verified | **PASS** |
| **End-to-End Workflows & Browser UI** | Live API E2E (`phase8_live_e2e.py`), live browser UI walkthrough (`/login`, `/overview`, `/incidents`, `/incidents/[id]`, Global Search, `/integrations`, `/monitors`, `/notifications`, `/settings`), and live containerized SMTP delivery (`axllent/mailpit`) | **PASS** |
| **Live External Cloud Credentials** | Supabase Cloud Auth (`SUPABASE_URL`), live external n8n instance (`X-N8N-API-KEY`), live OpenAI/Gemini API keys, live Slack Incoming Webhook, external production SMTP relay, Stripe Billing, and remote production VPS deployment | **UNVERIFIED** (Credentials / Authorization Pending) |

---

## 2. Production Deployment Configuration Checklist

Set these exact environment variables in `.env` (never committed) before deploying to a production host:

```dotenv
ENVIRONMENT=production
DEBUG=false
AUTH_MODE=supabase
ALLOW_PRIVATE_INTEGRATION_HOSTS=false

ENCRYPTION_KEY=<generated via python scripts/generate_keys.py>
SUPABASE_URL=https://<your-project-ref>.supabase.co
SUPABASE_ANON_KEY=<your-supabase-anon-key>
SUPABASE_JWT_SECRET=<optional-if-jwks-used>

ALLOWED_ORIGINS=https://app.<your-domain>
NEXT_PUBLIC_API_URL=https://app.<your-domain>
NEXT_PUBLIC_AUTH_MODE=supabase
NEXT_PUBLIC_SUPABASE_URL=https://<your-project-ref>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<your-supabase-anon-key>

DATABASE_URL=postgresql+psycopg://<db-user>:<strong-password>@postgres:5432/flowsentry
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2
```

### Startup & Health Verification
1. Build and start:
   ```bash
   docker compose --profile prod up -d --build --wait
   ```
2. Verify edge & readiness:
   - `GET https://app.<your-domain>/health` -> `200 {"status":"ok","service":"flowsentry-api"}`
   - `GET https://app.<your-domain>/ready` -> `200 {"status":"ready","checks":{"database":"ok","redis":"ok"}}`
3. Verify Alembic revision:
   ```bash
   docker compose exec -T backend alembic current
   ```

---

## 3. Incident Response & Rollback Runbook

### Application / Migration Rollback
1. Always take a pre-deploy snapshot before upgrading:
   ```bash
   ./scripts/backup_db.sh
   ```
2. Verify the backup into an isolated verification DB before relying on it:
   ```bash
   ./scripts/restore_db.sh backups/flowsentry_<timestamp>.sql.gz
   ```
3. If an application release regresses:
   - Check logs: `docker compose logs --tail=100 backend worker beat frontend nginx`
   - Roll back code to the previous Git tag/commit (`git checkout <prev-ref>`) and run `docker compose --profile prod up -d --build --wait`.
   - Only run `alembic downgrade -1` if schema rollback is explicitly required and verified against a backup snapshot first.

### Production Hardening Reminders
- Terminate TLS (HTTPS) in front of Nginx using Caddy, Certbot, or Cloudflare Proxy, and enforce HSTS at the TLS edge.
- Restrict firewall rules so ports `5432` and `6379` are **never** bound to public interfaces (`127.0.0.1` or internal VPC only).
- Rotate `ENCRYPTION_KEY` only with a re-encryption migration script, and keep `ENVIRONMENT=production` so `/api/v1/auth/dev-token` and Swagger `/docs` remain disabled (`403`/`404`).
