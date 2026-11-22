# FlowSentry — Implementation Plan & Risk Register

**Status:** Phase 0 — Planning Complete  
**Date:** 2026-11-22

---

## 1. Phased Delivery Roadmap

### Phase 1 — Foundation
**Goal:** Working monorepo, containerized local stack, database schema, authentication, workspace RBAC, and dark-first frontend shell.
- **Deliverables:**
  - Monorepo scaffolding (`frontend/`, `backend/`, `infrastructure/`, `scripts/`), `.gitignore`, `.env.example`, `docker-compose.yml`.
  - Backend FastAPI app with `/health` and `/ready`, Pydantic settings, structured JSON logging (header redaction), Fernet/AES-256-GCM encryption utility, SSRF URL validator, and Redis rate limiter.
  - SQLAlchemy 2.x models and initial Alembic migration matching `DATABASE.md`.
  - Supabase JWT verification (`PyJWKClient` RS256/ES256 + HS256 fallback) + isolated `local_dev` test mode for automated testing.
  - Workspace, Member (RBAC: `owner`, `admin`, `member`, `viewer`), Project, API Key, Usage, and Audit Log APIs (`/api/v1/auth/me`, `/api/v1/workspaces`, `/api/v1/projects`).
  - Next.js App Router + Tailwind + shadcn/ui dark-first design system, Auth pages (login, register, password reset), Workspace/Project switcher, and 9-screen navigation shell.
- **Verification Gate:** Unit & integration tests for auth, RBAC, encryption, SSRF validator, and strict cross-workspace isolation; Docker build & startup check; frontend lint/typecheck/component tests.

### Phase 2 — Core Monitoring & n8n Integration
**Goal:** Real n8n integration, idempotent normalized ingestion, execution tracking, deterministic failure detection, and full incident lifecycle UI/API.
- **Deliverables:**
  - Normalized Event Model (`v1.0`) and payload sanitizer (stripping secrets, auth headers, PII).
  - n8n integration adapter (`GET /api/v1/workflows`, `GET /api/v1/executions`, `X-N8N-API-KEY` header, `nextCursor` pagination) + connection validation endpoint.
  - Authenticated & rate-limited n8n Error Trigger webhook ingestion endpoint + Celery polling worker.
  - Deterministic failure detection engine (Execution failure, Performance anomaly, Frequency anomaly, Repeated failure) + configurable severity rules.
  - Incident management APIs and UI (Overview, Incidents, Incident Details, Workflows, Workflow Details, Integrations with n8n setup guide & safe local test webhook tool).
- **Verification Gate:** Tests for n8n API adapter (mocked HTTP transport + real endpoint schema contract), duplicate webhook idempotency (Scenario 7), HTTP 429 incident creation (Scenario 1), and UI state tests (loading/empty/error/filters).

### Phase 3 — Intelligence & Outcome Monitoring
**Goal:** Incident fingerprinting, AI + deterministic root-cause investigation, business outcome monitors, recovery verification, and isolated demo environment.
- **Deliverables:**
  - Incident fingerprinting & grouping window logic (Scenario 2).
  - Recovery verification engine (configurable N consecutive healthy runs + auto-resolution audit trail, Scenario 6).
  - AI Investigation Engine (`OpenAIProvider`, `GeminiProvider`, `DeterministicFallbackAnalyzer`) via async Celery tasks with strict JSON schema validation and quota enforcement (Scenario 5).
  - Outcome Monitoring Engine supporting all 6 monitor types (`expected_interval`, `expected_count`, `required_output_fields`, `http_endpoint`, `webhook_confirmation`, `external_record_check`) + Celery Beat scheduler + UI (Scenario 3).
  - Isolated Demo Environment seed & reset endpoints/scripts (`is_demo = true` workspace).
- **Verification Gate:** End-to-end tests covering all 7 core scenarios from the PRD.

### Phase 4 — Notifications & Commercial Readiness
**Goal:** Multi-channel alerting with suppression and retry, plus plan enforcement and Settings screens.
- **Deliverables:**
  - Email (SMTP) and Slack incoming webhook notifiers with encrypted channel config.
  - Per-workspace preferences, severity thresholds, duplicate suppression window, retry handling, and delivery ledger UI.
  - Server-side plan quota enforcement (`Free`, `Pro`, `Agency`, `Business`), usage counters, and Billing abstraction ready for Stripe.
  - Complete Settings screen (workspace profile, members, notifications, API keys, usage, audit log).
- **Verification Gate:** Notification delivery/suppression/retry tests, credential masking verification, and quota enforcement tests.

### Phase 5 — Quality, Security Hardening & Deployment
**Goal:** Production readiness, documentation completion, security audit, and repository hygiene.
- **Deliverables:**
  - Full automated test suite execution (backend unit + integration + cross-tenant security + E2E scenarios + frontend tests).
  - Nginx production reverse proxy config, production Compose profile, backup/restore scripts.
  - Complete docs (`API.md`, `INTEGRATIONS.md`, `SECURITY.md`, `DEVELOPMENT.md`, `DEPLOYMENT.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `CHANGELOG.md`, `README.md`, and confirmed `LICENSE`).
- **Verification Gate:** All tests green, Docker Compose full stack verified, zero leaked secrets, accurate acceptance criteria report.

---

## 2. Technical Risks & Mitigations

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| 1 | **n8n Self-Hosted Accessibility & SSRF Conflict** | Users running local/private n8n instances vs. SSRF rule blocking private IPs. | Default SSRF validator strictly blocks loopback/RFC1918/metadata IPs. Provide an explicit, documented configuration flag (`ALLOW_PRIVATE_INTEGRATION_HOSTS=false` by default) for self-hosted internal networks, plus clear security warnings in docs. Never allow cloud metadata `169.254.169.254`. |
| 2 | **n8n Payload Redaction & Missing Execution IDs** | n8n API can return `dataTooLargeToDisplay: true` or `redactionInfo`; Error Trigger fails on unsaved trigger errors without `execution.id`. | Normalize gracefully using optional fields; derive deterministic fallback `external_execution_id` from `(workflow_id, error_timestamp_bucket, lastNodeExecuted, message_hash)` when `execution.id` is absent. |
| 3 | **Supabase Auth Availability in Local/CI Environments** | Automated tests and offline Docker runs cannot rely on live Supabase Cloud calls. | Support Supabase JWKS (`RS256`/`ES256`) + `HS256` in production, and a strictly gated `AUTH_MODE=local_dev` (refuses to boot if `ENVIRONMENT=production`) for local dev and pytest suites. |
| 4 | **Host Docker Compose Subcommand Difference** | During Phase 0 host inspection inside the sandbox, `docker compose` returned `unknown command: docker compose` and `.docker/config.json` had sandbox access restrictions. | Verify `docker compose` / `docker-compose` outside sandbox or in Phase 1 setup; provide standard Compose v2 YAML compatible with both `docker compose` and `docker-compose`. |
| 5 | **AI Provider Outages, Latency, or Hallucination** | Unavailable keys, rate limits, or fabricated root causes undermine trust. | Execute AI asynchronously in Celery with bounded timeouts/quotas; enforce strict Pydantic schema validation; fall back automatically to `DeterministicFallbackAnalyzer` so incidents are always diagnosable without AI. |
| 6 | **Cross-Tenant Data Leakage** | Accidental omission of `workspace_id` filter exposes customer data. | Centralize authorization in FastAPI dependencies (`get_authorized_workspace`), filter all queries by `workspace_id`, and run automated cross-tenant access security tests in CI. |
| 7 | **Silent-Failure Monitor Abuse** | Outcome monitors making unbounded outbound HTTP calls could be abused for scanning/DoS. | Enforce SSRF validator, strict 5s timeout, max 256KB response cap, minimum polling intervals per plan, and disable unsafe HTTP redirects. |

---

## 3. Open Decisions Requiring Confirmation

1. **Software License (`LICENSE`):** Per project instructions, we will not assume an open-source license without confirmation. Please confirm whether FlowSentry should use a permissive open-source license (e.g., MIT / Apache-2.0), a source-available license, or proprietary terms before we generate `LICENSE` in Phase 5.
2. **Database & Auth for Local Development:** During Phases 1–4, we will wire full Supabase Auth (JWKS + email/password) and provide Dockerized PostgreSQL 16 + optional `local_dev` auth fallback for offline testing. If you have a Supabase project URL/anon key or managed Postgres URL you want to test against later, let us know when ready.
