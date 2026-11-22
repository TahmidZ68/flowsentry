# FlowSentry — Phase 7 Infrastructure & Database Verification Report

**Verification Date:** 2026-11-22  
**Phase Status:** Phase 7 Complete  
**Target Stack:** Docker Compose (`postgres:16-alpine`, `redis:7-alpine`, `flowsentry-backend`, `flowsentry-worker`, `flowsentry-beat`, `flowsentry-frontend`, `nginx:1.27-alpine`)

---

## 1. Infrastructure & Runtime Issues Discovered & Resolved

Running the full Docker Compose stack live revealed 6 concrete infrastructure/packaging issues that unit tests did not catch:

| ID | Component | Issue Discovered During Live Runtime | Fix Applied | File(s) |
|---|---|---|---|---|
| **INF-01** | Docker Build Context | Missing `.dockerignore` caused Docker to send ~785 MB of `backend/.venv`, `frontend/node_modules`, and `.next` cache into every build. | Added root `.dockerignore` excluding `.venv/`, `node_modules/`, `.next/`, `.git/`, `.env*`, and `backups/`. Build context dropped to `<10 KB` (frontend ~730 KB). | `.dockerignore` |
| **INF-02** | Frontend `npm ci` | `frontend/package-lock.json` had an `ajv@6.15.0` vs `ajv@^8.12.0` peer conflict between `eslint@9` and `@hookform/resolvers@7.0.8`, causing Docker `npm ci` to fail (`EUSAGE`). | Added `"ajv": "^8.18.0"` in `frontend/package.json` `devDependencies` and regenerated `frontend/package-lock.json` via `npm@10.8.2`; verified `npm ci --dry-run` exits `0` and `npm audit` reports `0 vulnerabilities`. | `frontend/package.json`, `frontend/package-lock.json` |
| **INF-03** | Next.js Standalone Bind | `frontend` container started Next.js `server.js` bound only to the container hostname IP (`http://1a04689689e9:3000`), causing `127.0.0.1:3000` healthchecks to fail (`unhealthy`). | Set `HOSTNAME="0.0.0.0"` in `infrastructure/docker/frontend.Dockerfile` runner stage and passed `NEXT_PUBLIC_*` build args in `docker-compose.yml`. | `infrastructure/docker/frontend.Dockerfile`, `docker-compose.yml` |
| **INF-04** | Celery / Redis Transport | `celery==5.4.0` installed `kombu==5.7.0`, which raised `kombu.exceptions.VersionMismatch: Redis transport requires redis-py versions 6.1.0 or later. You have 5.2.0` on live worker startup. | Upgraded to `redis==7.4.1` and `celery==5.7.0` in `backend/requirements.txt`; re-verified `pip-audit` (0 CVEs) and 37 backend `pytest` tests. | `backend/requirements.txt` |
| **INF-05** | Compose Startup & Health | `worker`/`beat` lacked dependency on `backend` health (risking queries before `alembic upgrade head`); `frontend` lacked a healthcheck; ports `5432`/`6379`/`8000`/`3000`/`80` were hardcoded. | Ordered `worker`, `beat`, `frontend`, and `nginx` startup behind `backend: condition: service_healthy`; added healthchecks on `backend` (`/ready`), `worker` (`celery inspect ping`), and `frontend`; parameterized host ports via env vars (`POSTGRES_PORT`, `REDIS_PORT`, `BACKEND_PORT`, `FRONTEND_PORT`, `NGINX_PORT`). | `docker-compose.yml` |
| **INF-06** | PostgreSQL Pooling & Proxy | `session.py` lacked explicit non-SQLite connection pool limits; Nginx omitted `Permissions-Policy` and `X-Request-ID` forwarding across `/api/`, `/health`, and `/ready`. | Added `pool_size=10`, `max_overflow=20`, `pool_recycle=1800`, `pool_timeout=30` for PostgreSQL in `backend/app/db/session.py`; added `X-Request-ID` forwarding and `Permissions-Policy` in `infrastructure/nginx/nginx.conf`. | `backend/app/db/session.py`, `infrastructure/nginx/nginx.conf` |

---

## 2. Live Verification Results

All checks below were executed against the live 7-container Docker Compose `--profile prod` stack (with local non-colliding host ports configured in `.env`: Postgres `5433`, Redis `6381`, Backend `8001`, Frontend `3001`, Nginx `8088`).

| Check | Command / Probe | Observed Result | Status |
|---|---|---|---|
| Compose config | `docker compose --profile prod config --quiet` | Exit code `0` (`COMPOSE_PROD_CONFIG_OK`) | **PASS** |
| All 7 containers running & healthy | `docker compose --profile prod ps` | `postgres` (healthy), `redis` (healthy), `backend` (healthy), `worker` (healthy), `beat` (up/running), `frontend` (healthy), `nginx` (up/healthy) | **PASS** |
| Nginx -> Backend `/ready` | `curl.exe -sSi http://localhost:8088/ready` | `HTTP/1.1 200 OK`, `{"status":"ready","checks":{"database":"ok","redis":"ok"}}`, security headers + `x-request-id` | **PASS** |
| Nginx -> Frontend `/` | `curl.exe -sSI http://localhost:8088/` | `HTTP/1.1 200 OK`, `text/html; charset=utf-8` | **PASS** |
| Alembic current head | `docker compose exec -T backend alembic current` | `56bf9a530d98 (head)` on `PostgresqlImpl` | **PASS** |
| Alembic downgrade/upgrade roundtrip | Isolated `flowsentry_alembic_verify` DB: `alembic upgrade head && alembic downgrade base && alembic upgrade head` | Completed with `0` errors; returned `56bf9a530d98 (head)` | **PASS** |
| Schema tables in PostgreSQL 16 | `psql -U flowsentry -d flowsentry -c "\dt"` | All 20 tables created (`workspaces`, `users`, `projects`, `integrations`, `workflows`, `executions`, `execution_events`, `incidents`, `incident_occurrences`, `incident_notes`, `ai_investigations`, `outcome_monitors`, `outcome_monitor_runs`, `notification_preferences`, `notifications`, `workspace_members`, `workspace_api_keys`, `usage_records`, `audit_logs`, `alembic_version`) | **PASS** |
| Live API write -> Postgres | `POST http://localhost:8088/api/v1/auth/dev-token` + `POST /api/v1/workspaces` | Created workspace `Phase7 Verify WS` (`5bb916aa-0051-4c1f-8cdf-e83288c64cc2`) | **PASS** |
| Redis 7 live rate limiting | `docker compose exec -T redis redis-cli KEYS "rl:*"` | Observed live rate-limit key `rl:dev_auth:172.20.0.1` | **PASS** |
| Celery worker task ping | `health_ping.delay().get(timeout=10)` | Returned `CELERY_PING_RESULT: pong` | **PASS** |
| Celery Beat -> Worker schedule | `docker compose logs beat` & `docker compose logs worker` | Beat scheduled and worker executed `flowsentry.evaluate_due_outcome_monitors`, `flowsentry.poll_enabled_integrations`, and `flowsentry.evaluate_frequency_anomalies` cleanly | **PASS** |
| PostgreSQL backup & restore | `pg_dump` -> `flowsentry_restore_verify` restore -> `SELECT count(*), min(name) FROM workspaces` | Returned `1|Phase7 Verify WS`; test DB & temp file cleaned up | **PASS** |
| Restore script added | `scripts/restore_db.sh` | Restores `.sql.gz` safely into `flowsentry_restore_verify` by default | **ADDED** |

---

## 3. Notes & Boundaries

- **Email Validation Behavior Observed:** `POST /api/v1/auth/dev-token` with `.local` TLD (`infra-verify@flowsentry.local`) returned `422 VALIDATION_ERROR` from `email-validator` RFC special-use domain rules; standard valid domains (`infra-verify@flowsentry.io`) succeed.
- **External Integrations Scope:** Live Supabase, live n8n instance, OpenAI/Gemini APIs, and SMTP/Slack delivery were not exercised in Phase 7 and move into **Phase 8** validation.
