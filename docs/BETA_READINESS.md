# FlowSentry — Phase 11 Beta Readiness & Onboarding Review

**Review Date:** 2026-11-23  
**Target Persona:** New n8n Automation Agency / Freelance Automation Engineer  
**Final Readiness Decision:** **2. READY FOR STAGING**

---

## 1. Customer Journey Walkthrough (8-Step Agency Onboarding)

| Step | User Journey | Verification Status | Friction Identified & Action Taken |
|---|---|---|---|
| **1. Register** | `/register` -> Supabase Auth signup (`AUTH_MODE=supabase`) or Local Dev Mode (`local_dev`) | Local Dev: **PASS** (live browser + Vitest); Supabase Cloud: **BLOCKED** | Works cleanly in `local_dev`; Supabase signup/email confirmation requires live `SUPABASE_URL` & `SUPABASE_ANON_KEY` in staging. |
| **2. Create Workspace** | First-run onboarding card in `/overview` creates workspace (`POST /api/v1/workspaces`) + auto-creates default `Production` project | **PASS** (live browser + API) | Auto-creates default project to eliminate setup dead-end; 3-step Quickstart card guides empty workspaces. |
| **3. Create Project** | `/projects` lists environment-filtered projects and creates `production` / `staging` / `development` projects | **PASS** (live API + build/typecheck) | Server enforces plan project quotas cleanly (`403 PLAN_LIMIT_REACHED`). |
| **4. Connect n8n** | `/integrations` supports n8n REST API v1 (`base_url` + `X-N8N-API-KEY`) and Webhook-Only Error Trigger ingestion | **PASS** (verified against live Dockerized `n8nio/n8n` v2.48.7 + browser UI) | **Fixed friction:** `integrations/page.tsx` previously showed only a relative path (`/api/v1/ingest/webhooks/n8n/<id>`) with no copy button. Updated to show full copyable `${API_BASE_URL}${path}` + **Copy URL** / **Copy Secret** buttons. |
| **5. Configure Monitoring** | `/monitors` creates any of the 6 outcome monitor types against synced workflows | **PASS** (all 6 types verified) | **Fixed lifecycle gap:** Passing outcome monitors previously left prior `SILENT_FAILURE` incidents `open`; now auto-resolves them on recovery. |
| **6. Receive Incident Notification** | `/notifications` configures Slack webhook & Email recipients with severity filters and cooldown suppression | Local SMTP: **PASS** (`Mailpit`); Live Slack / External SMTP: **BLOCKED** | Requires external SMTP host (`SMTP_*`) and real Slack webhook for beta customers; UI includes masked target display, **Send Test**, and **Retry** controls. |
| **7. Understand Investigation** | `/incidents/[id]` displays observed error evidence, fingerprint, related executions, timeline notes, and RCA | **PASS** (live browser + API) | Deterministic fallback works cleanly without AI keys (`requires_human_review=true`, evidence separated from hypothesis). |
| **8. Verify Recovery** | Automatic resolution after 3 consecutive healthy executions (or outcome monitor pass) + `incident_resolved` notification | **PASS** (verified live against `n8nio/n8n` v2.48.7) | Works cleanly across both n8n polling recovery and outcome monitor recovery. |

---

## 2. Why the Gate Decision Is `2. READY FOR STAGING` (Not Yet `CONTROLLED BETA` or `PUBLIC PRODUCTION`)

Per strict Phase 11 criteria (*"A controlled beta requires successful verification of the core customer journey and documented handling of outstanding risks. Do not award a higher readiness status based on successful compilation or local Docker execution alone"*):

- **What IS ready:** The core product, multi-tenant PostgreSQL 16 data model, Redis 7 / Celery worker/beat scheduling, real `n8nio/n8n` v2.48.7 integration, all 6 outcome monitor types with recovery, security controls, and agency onboarding UI are implemented and verified.
- **What blocks `READY FOR CONTROLLED BETA` right now:**
  1. **No remote staging environment deployed with HTTPS/TLS** (cannot verify real external webhooks from customer cloud n8n instances over the public internet).
  2. **Live Supabase Cloud Auth is `BLOCKED`/`UNVERIFIED`** (beta users cannot register/sign in securely until a live Supabase project is connected and tested).
  3. **Live External SMTP Relay & Live Slack Webhook are `BLOCKED`/`UNVERIFIED`** (only local containerized Mailpit SMTP was tested; external email deliverability and real Slack delivery remain unverified).
  4. **Live OpenAI / Gemini API calls are `BLOCKED`/`UNVERIFIED`** (deterministic fallback is ready and verified, but live LLM responses/costs are unverified).

Once a remote HTTPS staging environment is provisioned with live Supabase Auth, an external SMTP relay, a Slack test channel, and optionally an OpenAI/Gemini API key — and those 4 blocked validations pass — FlowSentry can immediately advance from **READY FOR STAGING** to **READY FOR CONTROLLED BETA**.
