# FlowSentry — Phase 11 Real-World Validation Report

**Validation Date:** 2026-11-23  
**Git Commit Base:** `8854730` + Phase 11 fixes (`outcomes/service.py` silent-failure recovery, `integrations/page.tsx` copyable full webhook URL, `test_phase11_security_and_monitors.py`)  
**Final Gate Decision:** **READY FOR STAGING**

---

## 1. Classification Summary

| Category | Executed / Evaluated | Outcome |
|---|---|---|
| **Real Service Tests** | Real `n8nio/n8n:latest` (v2.48.7) 15-step API + Error Trigger workflow suite; live PostgreSQL 16 + Alembic + `pg_dump`/restore; live Redis 7 + Celery Worker & Beat; live Next.js 16 + Browser E2E; local containerized SMTP (`axllent/mailpit`) | **PASS** (100% of locally runnable real services) |
| **Mocked Tests** | OpenAI & Gemini resilience (`MockTransport`: timeout, HTTP 429, invalid JSON, retry, token accounting); Slack delivery (`MockTransport`: suppression, retry, recovery); RSA JWKS RS256 JWT; `http_endpoint` & `external_record_check` (`MockTransport`); DNS rebinding (`getaddrinfo` mock) | **PASS** (explicitly classified as mocked, not live external SaaS) |
| **Automated Test Suites** | Backend `pytest` (`40 passed`), `ruff check` (`All checks passed!`), `pip-audit` (`0` CVEs); Frontend `tsc --noEmit` (`0` errors), `vitest` (`10 passed`), `eslint` (`0` errors), `next build` (`exit 0`), `npm audit` (`0` CVEs) | **PASS** |
| **Blocked External / Remote Tests** | Remote cloud n8n instance, live Supabase Cloud Auth, live OpenAI API, live Gemini API, live Slack Incoming Webhook, external production SMTP relay (SES/SendGrid/Postmark), remote VPS/cloud staging deployment | **BLOCKED** (external credentials / remote host / paid infra absent) |
| **Failed Tests (Final Run)** | None | **0 failed** |

---

## 2. Real n8n Integration Validation (`n8nio/n8n:latest`, v2.48.7)

Executed against a real containerized n8n v2.48.7 instance (`flowsentry-n8n-real` on Docker network `flowsentry_default`) communicating directly with `flowsentry-backend`, PostgreSQL 16, and Redis 7 (`phase11_real_n8n.py`):

1. **Default SSRF Block Verified (`ALLOW_PRIVATE_INTEGRATION_HOSTS=false`):** Creating an n8n integration pointing to internal IP `http://flowsentry-n8n-real:5678` (`172.20.0.6`) returned `HTTP 422 INVALID_URL: Blocked private/loopback IP target: 172.20.0.6`.
2. **Self-Hosted VPC Validation (`ALLOW_PRIVATE_INTEGRATION_HOSTS=true` temporarily during test, restored to `false` afterward):**
   - **Negative Cases:** Invalid `X-N8N-API-KEY` -> `validate` returned `ok=false`, `"Authentication failed against n8n API (HTTP 401)"`; unavailable port (`:59999`) -> `ok=false` network error; malformed webhook `{}` -> `HTTP 422 INVALID_WEBHOOK_PAYLOAD`; disconnecting those two test integrations freed Free-plan quota (`max_integrations=2`).
   - **Steps 1–4 (Connect, Validate, Sync Workflows, Error Trigger):** Connected `Live Docker n8n`, validated credentials (`ok=true, status="connected"`), confirmed plaintext `n8n_api_key` absent from create JSON and backend logs (`NO_N8N_API_KEY_IN_BACKEND_LOGS`), created a real n8n **Error Trigger -> HTTP Request** handler workflow and a **Webhook -> Code** workflow (`Customer Lead Sync`), and synced workflows (`workflows_synced=2`).
   - **Steps 5–10 (Real Execution Failure -> Webhook Ingestion -> Grouping -> Dedup):** Triggered `/webhook/phase11-lead-sync` 3 times with `{"fail": true}` throwing `HTTP 429 Rate limit exceeded calling HubSpot CRM`. Real n8n Error Trigger pushed all 3 events to FlowSentry's webhook endpoint -> normalized (`error_type="HTTP_429"`), grouped into 1 incident (`occurrence_count=3`, escalated to `severity="critical"`). Subsequent `POST /integrations/{id}/sync` deduplicated all 3 webhook-ingested failures (`executions_deduplicated=3`).
   - **Steps 11–15 (Investigation, Fix, Recovery):** Ran investigation (`analysis_status="completed"`, `requires_human_review=true`), updated the real n8n workflow via `PUT /api/v1/workflows/{id}` to succeed, triggered 3 healthy runs (`HTTP 200`), ran `POST /integrations/{id}/sync` (`executions_ingested=3`), and confirmed automatic incident transition to `status="resolved"`.

> **Boundary Note:** Verified against a self-hosted `n8nio/n8n` v2.48.7 Docker container. External customer n8n Cloud / remote instances remain **BLOCKED** pending external instance credentials.

---

## 3. Live AI Validation Status

| Aspect | Mode | Outcome & Observed Evidence |
|---|---|---|
| OpenAI (`gpt-4o-mini`) & Gemini (`gemini-2.5-flash`) Live API | **BLOCKED** | `OPENAI_API_KEY` and `GEMINI_API_KEY` are unset on this host; live upstream LLM responses could not be executed. |
| Timeout, Rate Limit (429), Invalid JSON, Retry & Fallback | **PASS (Mocked `MockTransport`)** | Verified in `test_ai_resilience_timeout_ratelimit_invalid_json_retry_and_fallback`: `ReadTimeout` on attempt 1 retried and succeeded on attempt 2 (`total_tokens=170` persisted to `UsageRecord.ai_tokens_used`); persistent `429` fell back to `DeterministicFallbackAnalyzer` (`analysis_status="completed_fallback"`, `requires_human_review=true`); `GeminiProvider` sends key via `"x-goog-api-key"` header (absent from URL); invalid JSON raises `AIProviderError`; destructive recovery actions are never executed automatically. |
| Deterministic Fallback (No API Keys) | **PASS (Real Live Stack)** | Verified live in Docker against PostgreSQL 16 (`provider="deterministic"`, sanitized evidence, `requires_human_review=true`). |

---

## 4. Notification Validation Status

| Channel / Behavior | Mode | Outcome & Observed Evidence |
|---|---|---|
| **Local SMTP (`axllent/mailpit`)** | **PASS (Local Container SMTP)** | Sent real SMTP message from `flowsentry-backend` to `flowsentry-mailpit-e2e:1025`; Mailpit `/api/v1/messages` confirmed `MAILPIT_TOTAL=1` (`Subject: FlowSentry Live SMTP Check`). *Classified strictly as local SMTP verification.* |
| **External Production SMTP Relay (SES/SendGrid/Postmark)** | **BLOCKED** | No external SMTP credentials configured on host. |
| **Live Slack Webhook Delivery** | **BLOCKED** | No real Slack webhook URL configured (`SLACK_WEBHOOK_URL` unset). |
| **Slack Suppression, Retry, Failure & Recovery Notifications** | **PASS (Mocked `MockTransport` + DB)** | Verified in `test_notifications.py` & `test_phase11_security_and_monitors.py`: masked webhook URLs, 30–60 min duplicate suppression (`status="suppressed"`), failed delivery (`status="failed"`, `attempt_count=1`) -> `retry_failed_notification` (`status="sent"`, `attempt_count=2`), and `incident_resolved` notifications dispatched on recovery. |

---

## 5. Outcome Monitor Validation (All 6 Types)

Code audit + automated verification in `test_phase11_security_and_monitors.py` discovered and fixed a lifecycle gap in `backend/app/outcomes/service.py`: previously, passing outcome monitors updated `monitor.status = "healthy"` without resolving open `SILENT_FAILURE` incidents. Added automatic resolution of matching open `: Silent failure (<monitor.name>)` incidents with `IncidentNote` and `"incident_resolved"` notification dispatch.

| Monitor Type | Failure Detection | Incident & Duplicate Suppression | Recovery & Notification |
|---|---|---|---|
| `expected_interval` | **PASS** (`age_seconds > max_interval_seconds`) | **PASS** (`SILENT_FAILURE` grouped, alert suppressed within window) | **PASS** (resolved after fresh execution + `incident_resolved`) |
| `expected_count` | **PASS** (`actual_count < min_count` in window) | **PASS** | **PASS** (resolved after meeting count + `incident_resolved`) |
| `required_output_fields` | **PASS** (verified both live on Postgres 16 + unit suite) | **PASS** | **PASS** |
| `http_endpoint` | **PASS** (`MockTransport` HTTP 503 + HTTP 302 redirect non-follow) | **PASS** | **PASS** (`MockTransport` HTTP 200 JSON match -> auto-resolved) |
| `webhook_confirmation` | **PASS** (`grace_period_seconds` expired without `/confirm`) | **PASS** | **PASS** (`record_webhook_confirmation` -> auto-resolved) |
| `external_record_check` | **PASS** (`MockTransport` empty array / 503) | **PASS** | **PASS** (`min_records >= 1` met -> auto-resolved) |

---

## 6. Remote Staging Deployment Status

| Pre-Deploy Check | Status | Notes |
|---|---|---|
| Local Staging (`docker compose --profile prod` + Nginx + Postgres 16 + Redis 7 + Celery Beat/Worker) | **PASS** | Validated in Phase 7 & Phase 11 (Alembic cycle, `pg_dump`/restore, healthchecks, non-root containers, security headers). |
| Production Env & Auth Fail-Closed Guards | **PASS** | `Settings(ENVIRONMENT="production", AUTH_MODE="local_dev")` fails closed (`ValidationError`). |
| Remote VPS / Cloud Staging Provisioning, Real DNS/TLS/HTTPS, External Firewall | **BLOCKED** | No remote VPS, cloud account, domain, or deployment authorization available in this environment. Deployment artifacts (`docker-compose.yml`, `nginx.conf`, `backup_db.sh`, `restore_db.sh`, `LAUNCH_READINESS.md`) are prepared. |
