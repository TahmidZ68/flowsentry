# FlowSentry — External Service Setup Guide

This document provides step-by-step operator instructions for configuring external dependencies before staging or controlled beta deployment.

> [!NOTE]
> Live external connections to Supabase Cloud, OpenAI, Google Gemini, Slack Incoming Webhooks, External SMTP relays, and remote HTTPS n8n instances remain **UNVERIFIED / BLOCKED** until executed with real credentials on a staging/production host. Code paths, security controls, and mocked/local behavior have been verified locally.

---

## 1. Supabase Cloud Authentication (`AUTH_MODE=supabase`)

FlowSentry verifies Supabase JWTs in `backend/app/core/security.py` (`verify_jwt_token`) using either:
- **JWKS (`RS256` / `ES256`, recommended):** Fetched from `${SUPABASE_URL}/auth/v1/.well-known/jwks.json` via PyJWT `PyJWKClient` (`cache_keys=True`, `cache_jwk_set=True`, `lifespan=300`, `timeout=10`, automatic key-rotation refresh by `kid`).
- **Shared secret (`HS256`, legacy Supabase projects):** Validated with `SUPABASE_JWT_SECRET` when `alg == "HS256"`.

Every JWT MUST satisfy:
- Valid signature (JWKS public key or `SUPABASE_JWT_SECRET`).
- `aud == "authenticated"`.
- `iss == "${SUPABASE_URL}/auth/v1"` (when `SUPABASE_URL` is set).
- Present and valid `exp` (not expired) and `sub` (valid UUID) and `email` claims.

### Supabase Setup Steps
1. Create a Supabase project in the Supabase Dashboard (`Authentication -> Providers`).
2. Under **Authentication -> URL Configuration**:
   - Set **Site URL** to your deployed domain (e.g. `https://app.flowsentry.example`).
   - Add Redirect URLs for `/login`, `/register`, `/forgot-password`, and `/overview`.
3. Under **Authentication -> Email**:
   - Enable email/password sign-in and configure email confirmation + custom SMTP relay in Supabase for reliable transactional auth emails.
4. Retrieve from **Project Settings -> API**:
   - **Project URL** -> `SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_URL`
   - **anon public key** -> `NEXT_PUBLIC_SUPABASE_ANON_KEY` (public client-side key only; NEVER expose `service_role` key to the frontend).
   - **JWT Secret** (optional fallback only if using HS256 projects) -> `SUPABASE_JWT_SECRET`.
5. Configure environment variables:
   - Backend: `ENVIRONMENT=production` (or `staging`), `AUTH_MODE=supabase`, `SUPABASE_URL=https://<project-ref>.supabase.co`, `LOCAL_DEV_JWT_SECRET=` (empty).
   - Frontend build args (`docker-compose.yml` -> `frontend.build.args`): `NEXT_PUBLIC_AUTH_MODE=supabase`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`.
   - Rebuild frontend image whenever `NEXT_PUBLIC_*` build arguments change (`docker compose build frontend`), because Next.js inlines `NEXT_PUBLIC_*` variables during `next build`.

### User Provisioning, Refresh & Production Guardrails
- **Provisioning & Workspace Association:** On first authenticated API call (`GET /api/v1/auth/me` via `get_current_user`), FlowSentry reconciles `sub` / lowercase `email` in `users` (`get_or_create_user`). Invited users pre-provisioned in `workspace_members` by email automatically match on login.
- **Role Assignment:** Workspace membership and roles (`owner`, `admin`, `member`, `viewer`) are stored in `workspace_members` and enforced server-side via `require_workspace_role`.
- **Session Refresh:** `frontend/src/features/auth/auth-context.tsx` queries `supabase.auth.getSession()` on auth refresh and listens to `supabase.auth.onAuthStateChange` (`TOKEN_REFRESHED`, `SIGNED_IN`, `SIGNED_OUT`) to keep the Bearer token synchronized across 1-hour JWT expirations.
- **Fail-Closed Local Dev Guard:** `backend/app/core/config.py` (`validate_production_guards`) raises `ValueError` at startup if `ENVIRONMENT=production` and `AUTH_MODE!=supabase`, `DEBUG=true`, `ENCRYPTION_KEY` is blank, `SUPABASE_URL` & `SUPABASE_JWT_SECRET` are both blank, or `*` is in `ALLOWED_ORIGINS`. Additionally, `POST /api/v1/auth/dev-token` returns `404` when `ENVIRONMENT=production` or `AUTH_MODE!=local_dev`.

---

## 2. AI Provider Setup (OpenAI & Google Gemini)

AI investigation is implemented in `backend/app/intelligence/providers.py` and `backend/app/intelligence/service.py`.

### Supported Providers & Configuration
- `AI_PROVIDER`: `"openai"`, `"gemini"`, or `"none"`.
- **OpenAI:** Set `AI_PROVIDER=openai`, `OPENAI_API_KEY`, and `OPENAI_MODEL` (default `gpt-4o-mini`). Calls `https://api.openai.com/v1/chat/completions` with `Authorization: Bearer <key>` header (`timeout=20.0`, `temperature=0.1`, `max_tokens=900`, `response_format={"type": "json_object"}`).
- **Google Gemini:** Set `AI_PROVIDER=gemini`, `GEMINI_API_KEY`, and `GEMINI_MODEL` (default `gemini-2.5-flash`). Calls `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent` passing `x-goog-api-key` in the request header (never in URL query parameters), `timeout=20.0`, `maxOutputTokens=900`, `responseMimeType="application/json"`.
- **Deterministic Fallback:** When `AI_PROVIDER=none`, keys are unset, monthly quota is exceeded, or the external AI call fails after 1 retry (`0.2s` backoff), `DeterministicFallbackAnalyzer` (`provider="deterministic"`, `model="rule-engine-v1"`) completes the investigation without failing the incident workflow.

### Security, Quotas & Cost Controls
- Evidence payloads sent to AI providers pass through `build_sanitized_evidence()` + `sanitize_payload()` so credentials, bearer headers, and API keys are stripped before transmission.
- `AIInvestigation` persists `provider`, `model`, `token_usage` (`prompt_tokens`, `completion_tokens`, `total_tokens`), `analysis_status` (`completed` / `completed_fallback`), and `requires_human_review=true`.
- `UsageRecord` enforces monthly `max_monthly_ai_investigations` per plan (`backend/app/core/plans.py`) and accumulates `ai_tokens_used`.

---

## 3. Slack Incoming Webhooks

Configured per workspace via `PUT /api/v1/workspaces/{workspace_id}/notifications/preferences` (`notifications` page in the dashboard).

1. In Slack App Management, enable **Incoming Webhooks**, add a webhook to your target channel (e.g., `#flowsentry-alerts`), and copy the `https://hooks.slack.com/services/...` URL.
2. In FlowSentry (`/notifications`), paste the webhook URL, select subscribed events (`critical_incident`, `high_incident`, `outcome_failure`, `incident_resolved`), set `min_severity`, and set `suppression_minutes` cooldown (duplicate suppression window).
3. FlowSentry validates the webhook URL via `validate_outbound_url` (SSRF protection; private/loopback/metadata IPs blocked unless `ALLOW_PRIVATE_INTEGRATION_HOSTS=true`), encrypts it with `ENCRYPTION_KEY` (Fernet) in `NotificationPreference.encrypted_config`, and returns only a masked tail (`https://hooks.slack.com/...xxxx`).
4. Verify delivery using **Send Test** (`POST /api/v1/workspaces/{workspace_id}/notifications/test`) and inspect the **Delivery Ledger** (`status`: `sent`, `failed`, or `suppressed`, with manual retry via `POST /api/v1/workspaces/{workspace_id}/notifications/{notification_id}/retry`).
5. **Recovery Alerts:** Include `incident_resolved` in `events` to deliver recovery notifications even when the incident severity was lower than `min_severity`.

---

## 4. External SMTP Email Relay

Mailpit is strictly for local development/testing. For staging and production, configure an external transactional SMTP provider (e.g., Postmark, SendGrid, Amazon SES, Resend SMTP, or Mailgun):

1. Create a verified sending domain (SPF, DKIM, DMARC DNS records configured).
2. Configure backend environment variables:
   - `SMTP_HOST`: e.g., `smtp.sendgrid.net`, `email-smtp.us-east-1.amazonaws.com`, `smtp.resend.com`, or `smtp.postmarkapp.com`
   - `SMTP_PORT`: `587` (STARTTLS) or `465` (implicit SSL/TLS; `_deliver_email` selects `smtplib.SMTP_SSL` when `SMTP_PORT=465` and `SMTP_USE_TLS=true`, or `smtplib.SMTP` + `starttls()` otherwise)
   - `SMTP_USE_TLS=true`
   - `SMTP_USER` / `SMTP_PASSWORD`: provider SMTP credentials
   - `SMTP_FROM_EMAIL`: verified sender address matching your authenticated domain (e.g., `alerts@yourdomain.com`)
3. In FlowSentry `/notifications`, enable Email notifications, enter recipient addresses, enable duplicate suppression (`suppression_minutes`), and trigger **Send Test** to verify delivery and spam/DKIM alignment.

---

## 5. Remote n8n Integration (API v1 + Error Trigger Webhooks)

1. **n8n API Key & URL:**
   - Generate an n8n API key in n8n (`Settings -> n8n API -> Create API Key`).
   - Connect using your remote **HTTPS** n8n base URL (e.g., `https://n8n.agency.example`).
   - Keep `ALLOW_PRIVATE_INTEGRATION_HOSTS=false` in production so SSRF protections block private/loopback/cloud-metadata targets unless an internal VPC n8n deployment explicitly requires private access.
   - Credentials are encrypted at rest (`Integration.encrypted_credentials` using Fernet) and never exposed in API responses (`IntegrationRead` returns `has_credentials` boolean only).
   - Disconnecting an integration clears stored credentials (`{}`) and revokes `webhook_secret_hash`.
2. **Error Trigger Webhook:**
   - Upon creating an n8n integration, FlowSentry returns `webhook_url_path` and a one-time `webhook_secret` (`X-FlowSentry-Webhook-Secret`), and renders the full public `POST <origin>/api/v1/ingest/webhooks/n8n/{integration_id}` URL in `/integrations`.
   - In n8n, create an **Error Trigger -> HTTP Request** workflow targeting that HTTPS URL, setting header `X-FlowSentry-Webhook-Secret` to the copied secret, and assign it as the **Error Workflow** for monitored production workflows.
   - Payload size is capped at `1,048,576` bytes (`MAX_WEBHOOK_PAYLOAD_BYTES`) and rate-limited (`180` requests / `60s` per integration ID).
