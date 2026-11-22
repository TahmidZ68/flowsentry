# FlowSentry — Product Requirements Document (PRD)

**Tagline:** *Your workflows run. Make sure they work.*  
**Category:** Commercial SaaS / Developer Observability Tool  
**Status:** Phase 0 — Architecture & Planning  
**Date:** 2026-11-22

---

## 1. Product Vision & Positioning

FlowSentry is an automation reliability and intelligence platform that detects workflow failures, identifies recurring problems, investigates root causes, monitors business outcomes, and recommends actionable recovery strategies.

It provides a centralized reliability layer across automation platforms and custom integrations.

**What FlowSentry is NOT:**
- It is **not** a workflow builder or orchestrator.
- It does **not** replace n8n, Make, Zapier, or custom automation systems.
- It does **not** automatically execute destructive recovery actions on customer workflows.

**What FlowSentry IS:**
- A reliability, root-cause intelligence, and business-outcome verification layer that helps teams know whether their existing automated processes are actually delivering intended business results.

---

## 2. Target Customers & Market

### Primary Customers
- Automation agencies managing workflows for multiple clients.
- Freelance automation developers and n8n consultants.
- Small software engineering teams operating business-critical automations.
- Businesses running multiple interconnected automated processes.

### Secondary Customers
- Internal IT and RevOps teams.
- AI automation companies validating agentic outputs.
- SaaS businesses operating API-driven background workflows.

---

## 3. Core Product Promise & Differentiators

FlowSentry differentiates from generic uptime/log dashboards through four integrated capabilities:

### A. Execution Intelligence
Ingest, normalize, and track workflow executions across integrations:
- Execution statuses (`success`, `failed`, `running`, `waiting`, `canceled`, `crashed`).
- Failed node names, normalized error types, error messages, duration (`duration_ms`), retry context, and historical trends.

### B. Root-Cause Investigation
Analyze sanitized execution evidence to explain:
- What failed and where it failed (node/step).
- What preceded the failure.
- Potential underlying cause (with explicit confidence and uncertainty).
- Whether the signature has occurred previously in the workspace.
- Verifiable evidence supporting the explanation (never fabricated).
- Actionable, non-destructive recovery recommendations.
- Provider-independent AI (OpenAI, Google Gemini) plus a **deterministic fallback analyzer** so investigation works even when AI is unconfigured or unavailable.

### C. Business Outcome Monitoring
Detect silent failures where a workflow reports technical success (`200 OK` / `success`) yet the intended business outcome fails to materialize. Users explicitly configure outcome monitors using:
1. **Expected execution interval** (heartbeat / schedule miss detection).
2. **Expected execution count** (volume threshold within a time window).
3. **Required output fields** (schema/field presence and validation on execution payload).
4. **HTTP endpoint verification** (SSRF-safe outbound check against a verification URL).
5. **Webhook confirmation** (expecting a downstream confirmation event within a deadline).
6. **External record existence** (configurable connector query/API check where safely supported).

### D. Incident Intelligence
Group related failures into deduplicated, actionable incidents:
- Fingerprinted by `workflow_id`, `error_type`, `failed_node`, and normalized error signature within a configurable grouping window.
- Tracks first seen, last seen, occurrence count, severity, assignee, internal notes, root-cause hypothesis, evidence, recommended actions, and resolution verification rules.

---

## 4. Functional Requirements

### 4.1 Authentication & Multi-Tenant Workspaces
- **Auth:** Supabase Auth (email/password signup, login, email verification, password recovery). Backend independently validates JWTs on every protected endpoint.
- **Workspaces:** Users can create and switch between workspaces (supporting agency multi-client isolation).
- **Roles (RBAC):**
  - `owner`: Full workspace control, billing/plan settings, member management, deletion.
  - `admin`: Manage integrations, projects, workflows, monitors, notifications, members (non-owner).
  - `member`: View data, acknowledge/investigate/resolve incidents, create/edit outcome monitors, trigger investigations.
  - `viewer`: Read-only access to dashboards, workflows, executions, and incidents.
- **Projects & Environments:** Workspaces contain Projects segmented by environment (`production`, `staging`, `development`).
- **Strict Isolation:** Every workspace-owned database query and API handler enforces membership validation. Knowing a UUID never grants cross-tenant access.

### 4.2 Integrations (Initial Target: n8n)
- **Connection configuration:** Instance URL, `X-N8N-API-KEY` credential (encrypted at rest using authenticated encryption), optional connection name, project/environment assignment.
- **Validation:** Live connection test against `GET /api/v1/workflows?limit=1` (SSRF-protected). Never simulate a successful production connection.
- **Dual Ingestion:**
  1. **Error-Workflow Webhook Ingestion:** Workspace-scoped authenticated webhook endpoint accepting n8n Error Trigger payloads, with rate limiting, schema validation, and idempotency.
  2. **API Polling Synchronization:** Periodic Celery worker polling `GET /api/v1/workflows` and `GET /api/v1/executions` using `nextCursor` pagination, tracking sync cursors, and avoiding duplicates.
- **Setup Guidance:** Built-in n8n Error Workflow setup guide and testable sample payload / local mock test utility.

### 4.3 Normalized Event Model & Ingestion Pipeline
- Canonical versioned event schema (`schema_version = "1.0"`).
- Provider adapters translate platform payloads into normalized executions + execution events.
- Duplicate detection via `(workflow_id, external_execution_id)` uniqueness constraint and idempotency handling.
- Payload sanitization strips secrets, `Authorization` headers, cookies, API keys, bearer tokens, passwords, and unnecessary PII before persistence or AI transmission.

### 4.4 Deterministic Failure Detection Engine
Runs synchronously/asynchronously on every ingested execution **without requiring AI**:
- **Execution Failure:** Failed status, node error, unhandled exception, HTTP 4xx/5xx error classification.
- **Performance Anomaly:** Execution duration exceeding static threshold or configurable deviation from rolling baseline.
- **Frequency Anomaly:** Missing scheduled runs (missed heartbeat) or unexpected execution spikes.
- **Repeated Failure:** Multiple occurrences matching the same fingerprint within a configured window.
- **Silent Failure:** Technical success failing a configured Outcome Monitor.
- **Severity Rules:** Configurable mapping to `critical`, `high`, `medium`, `low`, `informational`.
- **Recovery Verification:** Configurable policy (e.g., N consecutive successful executions or monitor passes) before auto-resolving an incident, recording why and when auto-resolution occurred.

### 4.5 Incident Management
- Lifecycle states: `open`, `acknowledged`, `investigating`, `resolved`, `reopened`.
- Capabilities: Search, filter (severity, status, workflow, project, date), timeline of occurrences and status changes, internal notes, user assignment, manual resolve/reopen, and full audit logging.

### 4.6 AI Investigation Engine
- Asynchronous Celery task bounded by workspace quota and token limits.
- Provider abstraction supporting OpenAI and Google Gemini via environment configuration (no hardcoded model names in business logic).
- Structured JSON output: `summary`, `root_cause_hypothesis`, `confidence`, `evidence`, `possible_causes`, `recommended_actions`, `severity_assessment`, `requires_human_review`.
- Strict guardrails: separates observed facts from hypotheses, states uncertainty, never fabricates evidence, never claims unverified fixes, and falls back gracefully to deterministic analysis when AI is unavailable.

### 4.7 Outcome Monitoring Engine
- Create, edit, enable/disable, list, and manually execute checks.
- Stores evaluation schedule, last check timestamp, last success/failure timestamps, status (`healthy`, `failing`, `unknown`), and structured failure evidence.
- Creates or updates incidents on monitor failure when configured.

### 4.8 Notifications
- Channels: **Email** (SMTP/transactional adapter) and **Slack** (Incoming Webhooks).
- Events: Critical incident, High-severity incident, Repeated failure, Outcome monitor failure, Incident resolved.
- Features: Per-workspace channel config, per-severity triggers, duplicate notification suppression window, delivery status tracking, retry on transient failure, and delivery history. Webhook URLs and credentials are never returned in plaintext to the frontend.

### 4.9 Frontend Application (Dark-First Developer UI)
Nine core application views plus Auth views:
1. **Overview:** Real backend KPIs, workflow health, execution & failure trends (Recharts), recent incidents, recent executions, outcome monitor status. Explicit loading, empty, and error states.
2. **Incidents:** Searchable, filterable incident table.
3. **Incident Details:** Overview, failure timeline, related executions, sanitized error evidence, AI investigation panel, recommended actions, internal notes, resolution controls.
4. **Workflows:** Table with integration, environment, execution count, success rate, failure count, avg duration, last run, health status.
5. **Workflow Details:** Metadata, execution history, duration trends, related incidents, outcome monitors, config.
6. **Investigations:** AI and deterministic investigation queue/history across incidents.
7. **Integrations:** Catalog (n8n active, upcoming adapters clearly labeled as not yet connected), connected integrations, sync status, validate/sync/disconnect actions, webhook setup instructions.
8. **Outcome Monitors:** List, status, failure evidence, creation and editing forms.
9. **Settings:** Workspace profile, members & roles, notification preferences, API keys, plan & usage counters, security/audit logs, account settings.

### 4.10 Demo Environment
- Isolated evaluation dataset clearly flagged (`is_demo = true` / dedicated demo workspace).
- Never mixed with real customer production data.
- Includes sample workflows, executions (success + HTTP 429/401/500 failures), grouped incidents, investigations, and outcome monitors.
- One-click reset capability for evaluation.

### 4.11 Commercial Readiness
- Subscription plan metadata (`free`, `pro`, `agency`, `business` — provisional tiers: \$0, \$19, \$59, \$149/mo).
- Server-side plan feature gating and usage counters (monthly executions ingested, AI investigations run, active monitors, team seats).
- Billing provider abstraction interface prepared for future Stripe integration (no fake checkout or client-side plan spoofing).

---

## 5. Non-Functional Requirements

- **Security:** JWT signature & expiry verification, RBAC on every endpoint, AES-256-GCM / Fernet encrypted credentials, SSRF protection on all user-supplied URLs, Redis-backed rate limiting, strict CORS, SQL injection prevention via parameterized SQLAlchemy queries, audit logs for sensitive mutations.
- **Reliability:** Idempotent ingestion, transactional incident grouping, graceful degradation when Redis/AI/external APIs fail.
- **Deployment:** Fully containerized with Docker Compose (`frontend`, `backend`, `worker`, `beat`, `postgres`, `redis`, `nginx`), `/health` and `/ready` endpoints, Alembic migrations.

---

## 6. MVP Acceptance Criteria (Gate to Release)

1. User registration, login, email verification/recovery flow works end-to-end.
2. User can create a workspace and invite/manage members with roles.
3. Cross-workspace isolation is enforced and verified by security tests.
4. Projects and environments can be created and filtered.
5. An n8n integration can be configured, encrypted, and validated (with real API when reachable, and documented safe local test harness when offline).
6. Workflow executions are ingested via webhook and/or polling sync.
7. Duplicate execution deliveries are handled idempotently without duplicate rows or duplicate incidents.
8. Executions are stored, sanitized, and displayed accurately.
9. Deterministic failure detection flags failures, anomalies, and repeated errors.
10. Related failures group into a single incident via fingerprinting.
11. Incidents support full investigation, notes, assignment, acknowledgment, resolution, and reopening.
12. AI investigation analyzes sanitized evidence asynchronously when configured, and falls back deterministically when unavailable.
13. Outcome monitors can be created, evaluated, and trigger silent-failure incidents.
14. Email and Slack notifications can be configured, suppressed for duplicates, and audited.
15. Application runs cleanly via Docker Compose.
16. Unit, integration, frontend, security, and E2E scenario tests pass.
17. Documentation accurately reflects verified behavior and explicitly notes any unverified external integrations.
