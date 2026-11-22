# FlowSentry — Phase 9 Commercial SaaS Readiness

**Assessment Date:** 2026-11-22  
**Phase Status:** Phase 9 Complete  
**Positioning:** *"Your workflows run. Make sure they work."* — Workflow reliability, root-cause investigation, and silent-failure outcome monitoring for automation agencies, n8n consultants, and technical teams.

---

## 1. Commercial Product Completeness

| Commercial Pillar | Implementation Status | Details & Evidence |
|---|---|---|
| **Multi-Tenant Workspaces & RBAC** | Implemented & Verified | Isolated workspaces (`owner`, `admin`, `member`, `viewer`), member management (`GET/POST/PATCH/DELETE /api/v1/workspaces/{id}/members`), and strict `403` cross-tenant boundary checks. |
| **Plan Tiers & Quota Enforcement** | Implemented & Verified | Defined in `backend/app/core/plans.py`: **Free** (`$0`, 2 projects, 2 integrations, 1,000 executions/mo, 10 AI investigations/mo, 3 outcome monitors, 1 member, 30d retention), **Pro** (`$19/mo`, 5/5/25k/100/15/3/90d), **Agency** (`$59/mo`, 25/25/150k/500/75/15/180d), **Business** (`$149/mo`, 100/100/1M/2.5k/300/50/365d). Server-side quotas enforced across ingestion, AI investigations, outcome monitors, and member invites; visible in `/settings`. |
| **Customer Onboarding Flow** | Implemented & Verified | First-run workspace creation wizard (`/overview`), 3-step Quickstart Checklist when a workspace has 0 workflows/executions, one-click isolated **Demo Sandbox** (`POST /api/v1/demo/seed`), inline n8n Error Trigger setup guide (`/integrations`), and safe `Test Webhook` trigger. |
| **API & SDK Ingestion** | Implemented & Verified | Scoped workspace API keys (`X-API-Key` with `ingest:write` scope, `fs_live_` prefix, SHA-256 hashed at rest, revocable) for direct execution ingestion (`POST /api/v1/workspaces/{id}/executions/ingest`), plus `X-FlowSentry-Webhook-Secret` authentication for n8n Error Triggers. |
| **Auditability & Data Retention** | Implemented & Verified | Security audit logs (`GET /api/v1/workspaces/{id}/audit-logs`) capture workspace/integration/monitor/incident/key actions; Celery beat daily task `flowsentry.cleanup_expired_records` prunes executions and monitor runs beyond each workspace plan's `retention_days`. |
| **AI Cost & Provider Independence** | Implemented & Verified | Optional `openai` (`gpt-4o-mini`) and `gemini` (`gemini-2.5-flash`) provider abstractions with automatic sanitized evidence payloads, token usage accounting (`usage_records`), and deterministic rule-based fallback (`DeterministicFallbackAnalyzer`) so every core workflow works at zero LLM cost. |
| **Billing / Checkout (Stripe)** | Deferred (`UNVERIFIED`) | `BillingProvider` protocol and `NoopBillingProvider` stub exist in `backend/app/core/plans.py`. Live Stripe Checkout / customer portal / webhook signature handling is intentionally unimplemented until a commercial Stripe account & webhook secret are provisioned and authorized. |
| **Repository Licensing & Legal** | Pending Authorization | No `LICENSE` file has been published without explicit owner authorization; Terms of Service / Privacy Policy URLs must be supplied for production public signup. |

---

## 2. Customer Onboarding & Operations Runbook

1. **Agency / Customer Sign-Up:** User authenticates via Supabase Auth (`AUTH_MODE=supabase` in production) and creates their workspace (e.g., per client or internal team).
2. **Integration Setup:**
   - **Cloud/Accessible n8n:** Add n8n REST API v1 URL + `X-N8N-API-KEY`, validate connection, enable polling (`polling_interval_seconds`).
   - **Firewalled / Self-Hosted n8n:** Select Webhook-Only mode and configure n8n's Error Workflow (`Error Trigger -> HTTP Request`) with `X-FlowSentry-Webhook-Secret`.
   - **Custom Pipelines / Make / Zapier / Python / Node:** Generate a workspace `X-API-Key` in `/settings` and POST normalized execution events to `/api/v1/workspaces/{workspace_id}/executions/ingest`.
3. **Silent Failure Protection:** Configure outcome monitors in `/monitors` (`expected_interval`, `expected_count`, `required_output_fields`, `http_endpoint`, `webhook_confirmation`, `external_record_check`) to catch workflows that exit `success` without creating the business record.
4. **Incident Triage & Resolution:** Grouped incidents surface in `/incidents`, trigger Slack/SMTP alerts with cooldown deduplication, provide sanitized evidence + root-cause hypotheses + non-destructive recovery recommendations in `/incidents/[id]`, and auto-verify recovery after 3 consecutive healthy executions.

---

## 3. Pre-Commercial Launch Checklist (Authorization Required)

Before opening public self-serve billing or marketing sign-ups:
- [ ] Provision managed Supabase project (`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET`), enable email confirmation & password reset templates.
- [ ] Connect Stripe Billing (`BillingProvider` implementation) if self-serve paid upgrades (`Pro`, `Agency`, `Business`) are required at launch; otherwise onboard initial agency customers manually via workspace `plan` assignment.
- [ ] Provision production transactional SMTP relay (AWS SES / Postmark / Resend) and verify SPF/DKIM/DMARC records for the sending domain.
- [ ] Configure TLS termination (Caddy / Certbot / Cloudflare) on custom domain (`https://app.<domain>`).
- [ ] Confirm and commit the chosen software `LICENSE` and publish Privacy Policy & Terms of Service pages.
