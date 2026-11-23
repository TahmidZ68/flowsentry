# FlowSentry — Open-Core Architecture Audit

**Audit Date:** 2026-11-23  
**Repository Baseline:** `main` at `96b8f87` + Open-Core Architectural Decoupling & Release Prep  
**Proposed Direction:** Community Edition (`AGPL-3.0-only`) + Proprietary Commercial / Cloud Offering  
**Initial Audit Outcome:** `REQUIRES ARCHITECTURAL CHANGES` -> **Post-Refactor Status: `READY FOR OPEN-SOURCE RELEASE`** *(Entitlement separation, extension SPIs, `LICENSE`, `NOTICE`, `CLA.md`, and `.github/` CI completed)*

---

## 1. Executive Summary

FlowSentry is a well-structured FastAPI + Next.js 16 + PostgreSQL 16 + Redis 7 + Celery modular monolith with genuine end-to-end reliability intelligence, strong multi-tenant isolation, SSRF protection, secret sanitization, and clean single-author copyright ownership. From a code quality and dependency licensing perspective, there are no fatal legal blockers to releasing an `AGPL-3.0-only` Community Edition.

However, **FlowSentry cannot safely transition to an open-core model (`AGPL-3.0-only` Core + Proprietary Commercial/Cloud) in its current monolith state without targeted architectural refactoring**:

1. **Commercial SaaS Quotas & Pricing Are Hardcoded Inside Core Paths:** [`backend/app/core/plans.py`](../backend/app/core/plans.py) embeds commercial SaaS tiers (`Free $0`, `Pro $19`, `Agency $59`, `Business $149`) and restrictive limits (`max_members=1`, `max_projects=2`, `max_integrations=2`, `max_monthly_executions=1000`, `max_outcome_monitors=3`) directly into core domain services and frontend UI ([`frontend/src/app/(app)/settings/page.tsx`](../frontend/src/app/(app)/settings/page.tsx)). Self-hosted Community users would hit `PLAN_LIMIT_REACHED` after 1 member—defeating self-hosted team RBAC—while SaaS deployments rely on the exact same module.
2. **No Extension / Plugin Boundary Exists for Commercial Modules:** All routers (`backend/app/api/v1/router.py`), models (`backend/app/models/`), auth verification (`backend/app/core/security.py`), connector adapters (`backend/app/services/integration_service.py`), notification channels (`backend/app/notifications/service.py`), and Next.js navigation items (`frontend/src/components/layout/app-shell.tsx`) are statically wired in one package. Dropping proprietary Enterprise modules (e.g., SAML SSO, Make/Zapier connectors, PagerDuty, Stripe billing, cross-workspace agency fleet analytics) into this process without an extension contract or dual-licensing isolation risks making them derivative works under `AGPL-3.0-only`.
3. **Database Schema & Alembic History Are Single-Tenant-App Coupled:** A single Alembic revision ([`56bf9a530d98_initial_schema.py`](../backend/migrations/versions/56bf9a530d98_initial_schema.py)) mixes Community telemetry tables (`workflows`, `executions`, `incidents`, `outcome_monitors`) with SaaS metering (`usage_records`, `workspaces.plan`).
4. **Licensing & Contributor Governance Missing Before Public Release:** No `LICENSE` file or Contributor License Agreement (`CLA`) exists yet (`README.md` explicitly marks licensing pending).

---

## 2. Verified Codebase Inventory (Observed Against Source)

| Layer | Verified Modules & Capabilities | Architectural Coupling Notes |
|---|---|---|
| **Backend API (`FastAPI`)** | 13 route modules registered statically in [`backend/app/api/v1/router.py`](../backend/app/api/v1/router.py): `auth`, `demo`, `workspaces`, `projects`, `integrations`, `ingest`, `workflows`, `executions`, `incidents`, `investigations`, `outcome_monitors`, `notifications`, `overview`. Health probes `/health` & `/ready` in [`backend/app/main.py`](../backend/app/main.py). | No dynamic extension router discovery or optional enterprise feature mount point. |
| **Auth & Multi-Tenant RBAC** | JWT validation in [`backend/app/core/security.py`](../backend/app/core/security.py) (`supabase` RS256/ES256 JWKS + HS256, or gated `local_dev`). Workspace membership, 4 roles (`owner`, `admin`, `member`, `viewer`), scoped API keys (`fs_...`), audit logging, and `_extract_client_ip` rate limiting in [`backend/app/api/deps.py`](../backend/app/api/deps.py). | `AUTH_MODE` is strictly `Literal["supabase", "local_dev"]`; no `AuthProvider` interface for SAML/OIDC SSO or SCIM. |
| **Database Models (`SQLAlchemy 2.x`)** | 19 tables across 4 model files (`identity.py`, `monitoring.py`, `incidents.py`, `outcomes.py`) managed by [`backend/migrations/versions/56bf9a530d98_initial_schema.py`](../backend/migrations/versions/56bf9a530d98_initial_schema.py). Portable `JSONType` (JSONB on PostgreSQL, JSON on SQLite). | `workspaces.plan` (`free`) and `usage_records` sit inside core identity schema. |
| **n8n Integration & Normalizer** | [`backend/app/integrations/n8n.py`](../backend/app/integrations/n8n.py) (`N8nClient` REST API v1 + `parse_n8n_error_webhook`) and [`backend/app/integrations/normalizer.py`](../backend/app/integrations/normalizer.py) (`NormalizedExecutionEvent v1.0`, secret/PII payload sanitizer, error classifier). Protected by [`backend/app/core/ssrf.py`](../backend/app/core/ssrf.py) & Fernet [`backend/app/core/encryption.py`](../backend/app/core/encryption.py). | `integration_service.py` hardcodes `if payload.provider == "n8n"` branches; no dynamic `ConnectorRegistry`. |
| **Detection & Incident Engine** | [`backend/app/detection/engine.py`](../backend/app/detection/engine.py) (failure classification, SHA-256 fingerprinting, SLA & >3x median latency anomaly detection, `grouping_window_hours`, `recovery_consecutive_successes` auto-resolution) + [`backend/app/incidents/service.py`](../backend/app/incidents/service.py). | Cleanly isolated domain logic (`app/detection/`, `app/incidents/`) suitable for Community Core. |
| **Outcome Monitors (6 Types)** | [`backend/app/outcomes/service.py`](../backend/app/outcomes/service.py) implements `expected_interval`, `expected_count`, `required_output_fields`, `http_endpoint`, `webhook_confirmation`, and `external_record_check`, plus auto-resolution of `SILENT_FAILURE` incidents on recovery. | Clean core module, except `create_monitor` enforces `limits.max_outcome_monitors`. |
| **AI Investigation Engine** | [`backend/app/intelligence/providers.py`](../backend/app/intelligence/providers.py) (`OpenAIProvider`, `GeminiProvider`, `DeterministicFallbackAnalyzer`) & [`backend/app/intelligence/service.py`](../backend/app/intelligence/service.py) (sanitized evidence builder, retry, token usage). | Good `BaseAIProvider` `Protocol`, though `_check_and_consume_ai_quota` couples directly to `plans.py`. |
| **Notifications** | [`backend/app/notifications/service.py`](../backend/app/notifications/service.py) (`slack` webhook + `email` SMTP/SMTP_SSL, encrypted config, cooldown suppression, retry, `incident_resolved` alerts). | Hardcodes `if notification.channel == "slack"` / `"email"`; no extensible channel plugin interface. |
| **Billing & Plans** | [`backend/app/core/plans.py`](../backend/app/core/plans.py) defines `PLANS` tiers, `BillingProvider` protocol, and `NoopBillingProvider` stub (`NotImplementedError`). Zero Stripe SDK dependency or checkout route exists. | Billing UI is absent except displaying `${plan.price_monthly_usd}/mo` in Settings. Plan quotas block Community usability. |
| **Workers & Ops** | [`backend/app/workers/celery_app.py`](../backend/app/workers/celery_app.py) & `tasks.py` run 4 Beat schedules (`poll_enabled_integrations`, `evaluate_due_outcome_monitors`, `evaluate_frequency_anomalies`, `cleanup_expired_records`). | `cleanup_expired_records` uses `plans.py` `retention_days` instead of workspace/env retention config. |
| **Frontend (`Next.js 16` / React 18)** | 13 routes (`overview`, `incidents`, `incidents/[id]`, `workflows`, `workflows/[id]`, `monitors`, `investigations`, `integrations`, `projects`, `notifications`, `settings`, `login`, `register`, `forgot-password`). Static `NAV_ITEMS` in `app-shell.tsx`. | Direct client calls to `NEXT_PUBLIC_API_URL`; `NEXT_PUBLIC_AUTH_MODE` gates Supabase vs local_dev login. |

---

## 3. Open-Core Architecture Readiness Assessment

### What Works Today
- **Self-Contained Core Value:** Execution ingestion, deterministic detection, incident grouping, all 6 business outcome monitors, deterministic RCA fallback, BYO-key OpenAI/Gemini RCA, Slack/SMTP alerts, isolated demo sandbox (`demo_service.py`), and Docker deployment (`docker-compose.yml` + `docker-compose.staging.yml`) work without external proprietary services.
- **Security & Isolation Parity:** Encryption (`cryptography` Fernet), SSRF DNS pinning (`_SSRFSafeSyncBackend`), payload redaction (`normalizer.py` + `logging.py`), and multi-workspace RBAC are cleanly centralized.

### Architectural Blockers to Open-Core Transition
1. **Tight Plan-Quota Coupling in Self-Hosted Mode:** Self-hosted Community Core must default to an unmetered/self-hosted `EntitlementProvider` (or environment-configurable limits), while Cloud SaaS injects strict tier quotas (`free`/`pro`/`agency`/`business`).
2. **Lack of Extension / SPI Contracts for Commercial Modules:** Enterprise auth (`SAML`/`OIDC`), commercial connectors (`Make`, `Zapier`, `Temporal`, `Airflow`), enterprise alert channels (`PagerDuty`, `Opsgenie`, `Microsoft Teams`), and Stripe billing have no clean registration mechanism or decoupled extension package boundary.
3. **Lack of Control Plane / Telemetry API Separation:** Managed Cloud fleet features (multi-tenant agency rollups across workspaces, billing portal, hosted usage aggregation, remote agent sync) currently have no out-of-process API contract separating AGPL-3.0 runtime code from proprietary Cloud control-plane services.

---

## 4. Recommended Licensing & Separation Strategy (Summary)

- **Recommended License Model:** **Dual-Licensed `AGPL-3.0-only` Community Core + Proprietary Commercial / Cloud License** (backed by a mandatory **CLA** before merging external contributions), with commercial SaaS control plane, billing, SAML SSO, and proprietary enterprise connectors cleanly separated behind SPIs / out-of-process services.
- See companion documents for full evidence:
  - [`docs/FEATURE_LICENSING_MATRIX.md`](./FEATURE_LICENSING_MATRIX.md)
  - [`docs/THIRD_PARTY_LICENSE_AUDIT.md`](./THIRD_PARTY_LICENSE_AUDIT.md)
  - [`docs/COMMERCIAL_BOUNDARY_PROPOSAL.md`](./COMMERCIAL_BOUNDARY_PROPOSAL.md)
  - [`docs/OPEN_SOURCE_RELEASE_CHECKLIST.md`](./OPEN_SOURCE_RELEASE_CHECKLIST.md)
