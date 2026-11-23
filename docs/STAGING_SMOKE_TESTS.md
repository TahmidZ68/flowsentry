# FlowSentry — Phase 13 Staging Smoke Tests

**Status:** **PENDING EXECUTION ON REMOTE STAGING HOST** *(All 17 checks remain `NOT RUN / BLOCKED` until the staging VPS, domain/TLS, and external credentials are authorized and deployed)*

Use this verification ledger immediately after booting [`docker-compose.staging.yml`](../docker-compose.staging.yml) on the remote staging server. Do **not** mark any item `PASS` until actually executed against the live HTTPS staging URL.

---

## 17-Point Staging Smoke Test Matrix

Replace `STAGING_HOST="https://staging.flowsentry.example"` with your deployed domain.

| # | Check | Verification Command / Procedure | Expected Result | Status | Recorded Evidence / Notes |
|---|---|---|---|---|---|
| **1** | **Public frontend access** | `curl -fsSI $STAGING_HOST/login` | HTTP `200`, Next.js login page renders `Supabase Auth` badge | `BLOCKED` | Pending remote host |
| **2** | **HTTPS certificate validity** | `curl -vI $STAGING_HOST/health 2>&1 \| grep -E "subject:\|expire date:\|HTTP/"` | Valid Let's Encrypt cert matching domain, TLSv1.2/1.3, HTTP `80` returns `301` -> HTTPS | `BLOCKED` | Pending DNS & Certbot |
| **3** | **Backend health endpoint** | `curl -fsS $STAGING_HOST/health` | `{"status":"ok","service":"flowsentry-api"}` + security headers (`X-Frame-Options: DENY`, `Strict-Transport-Security`) | `BLOCKED` | Pending remote host |
| **4** | **Database readiness** | `curl -fsS $STAGING_HOST/ready` | HTTP `200`, `"database": "ok"`, Alembic `current` == `56bf9a530d98` | `BLOCKED` | Pending remote host |
| **5** | **Redis readiness** | Inspect `/ready` response (`"redis": "ok"`) & verify host `REDIS_PASSWORD` auth | `"redis": "ok"`; unauthenticated `redis-cli` rejected (`NOAUTH`) inside container | `BLOCKED` | Pending remote host |
| **6** | **Celery worker health** | `docker compose -f docker-compose.yml -f docker-compose.staging.yml exec worker celery -A app.workers.celery_app inspect ping` | Worker replies `pong`; `ps` shows `(healthy)` | `BLOCKED` | Pending remote host |
| **7** | **Celery beat health** | `docker compose -f docker-compose.yml -f docker-compose.staging.yml logs --tail=50 beat` | Beat scheduler running with `/tmp/celerybeat.pid` & `(healthy)` status | `BLOCKED` | Pending remote host |
| **8** | **Authentication** | Sign up on `/register`, verify email via Supabase Cloud, sign in on `/login`, reload `/overview` | Valid `RS256`/`ES256` JWT verified via Supabase JWKS; `/api/v1/auth/dev-token` returns `404` when `ENVIRONMENT=production` | `BLOCKED` | Pending Supabase Cloud config |
| **9** | **Workspace creation** | Create a workspace in `/overview` onboarding card | Workspace created (`role=owner`), default `Production` project auto-created | `BLOCKED` | Pending remote host |
| **10** | **Project creation** | Create a `staging` project in `/projects` | Project listed and filterable by environment | `BLOCKED` | Pending remote host |
| **11** | **Integration configuration** | Connect remote HTTPS n8n instance on `/integrations`, click **Validate** & **Sync** | API key stored encrypted; workflows synced; plaintext secret never in response/logs | `BLOCKED` | Pending remote HTTPS n8n |
| **12** | **Webhook ingestion** | Trigger n8n Error Trigger workflow (or signed `POST /api/v1/ingest/webhooks/n8n/<id>`) | Returns `200`, invalid secret rejected (`401`), payload >1 MiB rejected (`413`) | `BLOCKED` | Pending remote host |
| **13** | **Incident creation** | Send repeated failure executions for same error fingerprint | Single grouped incident created, `occurrence_count` incremented | `BLOCKED` | Pending remote host |
| **14** | **Incident investigation** | Open `/incidents/<id>` and click **Run Investigation** | Observed evidence separated from hypothesis; works via OpenAI/Gemini or deterministic fallback (`requires_human_review=true`) | `BLOCKED` | Pending remote host |
| **15** | **Outcome monitoring** | Create `expected_interval` or `required_output_fields` monitor in `/monitors` and run check | Missing/silent failure creates `SILENT_FAILURE` incident | `BLOCKED` | Pending remote host |
| **16** | **Notification processing** | Configure real Slack webhook & external SMTP recipients in `/notifications`, click **Send Test**, trigger alert | Delivery Ledger records `sent`; repeated event within window marks `suppressed` | `BLOCKED` | Pending Slack & external SMTP |
| **17** | **Recovery detection** | Execute healthy workflow runs (`recovery_consecutive_successes=3`) & passing monitor check | Incident transitions automatically to `resolved` and triggers `incident_resolved` notification | `BLOCKED` | Pending remote host |

---

## Quick Post-Smoke Security Probes (Non-Destructive)

Run from an external workstation against the live staging host:
1. Verify ports `5432`, `6379`, `8000`, `3000` time out / refuse external connections (`nc -zv <VPS_IP> 5432 6379 8000 3000`).
2. Confirm `/api/v1/workspaces/<other-workspace-id>/incidents` returns `403` for a non-member user token.
3. Confirm attempting to connect `http://169.254.169.254/latest/meta-data/` or `http://127.0.0.1:5678` in `/integrations` fails with `422` (`ALLOW_PRIVATE_INTEGRATION_HOSTS=false`).
4. If testing `ENVIRONMENT=production`, verify `/docs`, `/redoc`, `/openapi.json`, and `/api/v1/auth/dev-token` return `404`.
