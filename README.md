# FlowSentry

> **Your workflows run. Make sure they work.**

**FlowSentry** is an automation reliability and intelligence platform that detects workflow failures, identifies recurring problems, investigates root causes, monitors business outcomes, and recommends actionable recovery strategies.

It provides a centralized reliability layer across automation platforms (starting with **n8n**) and custom API-driven integrations—without replacing your workflow orchestrator.

---

## Why FlowSentry Exists

Workflow runners tell you when a job crashed—but teams running production automations hit deeper problems:
1. **Silent business failures:** A workflow finishes with `200 OK` / `success`, yet no CRM contact was created or no invoice was generated.
2. **Alert fatigue:** Identical rate-limit (`HTTP 429`) or auth (`HTTP 401`) errors fire dozens of fragmented alerts instead of one grouped incident.
3. **Slow root-cause triage:** Engineers dig through raw JSON logs across executions to piece together what changed.

FlowSentry solves all three through **Execution Intelligence**, **Business Outcome Monitoring**, **Incident Fingerprinting**, and **Evidence-Backed Root-Cause Investigations**.

---

## Main Capabilities

- **Multi-Tenant Workspaces & RBAC:** Agency-ready workspace isolation (`owner`, `admin`, `member`, `viewer`), environment-scoped projects (`production`, `staging`, `development`), scoped API keys, and audit logs.
- **n8n Integration (API v1 + Error Trigger Webhooks):** Encrypted credential storage, cursor-paginated `GET /api/v1/workflows` & `GET /api/v1/executions` sync, rate-limited Error Trigger webhook ingestion, and safe local test webhook simulation.
- **Normalized Event Model (`v1.0`) & Payload Sanitization:** Idempotent ingestion (`(workflow_id, external_execution_id)` uniqueness) with automatic stripping of `Authorization`, `X-N8N-API-KEY`, cookies, tokens, and secrets.
- **Deterministic Failure & Anomaly Detection:** Execution failures, latency SLA / >3x baseline anomalies, missed schedule frequency checks, repeated failure escalation, and configurable consecutive-success recovery verification.
- **Business Outcome Monitoring:** 6 configurable monitors (`expected_interval`, `expected_count`, `required_output_fields`, `http_endpoint`, `webhook_confirmation`, `external_record_check`) to catch silent failures.
- **Root-Cause Investigations:** Provider-independent AI (`OpenAI`, `Google Gemini`) bounded by quotas and strict non-fabrication rules, plus a built-in **deterministic fallback engine** that works even without AI keys.
- **Notifications:** Encrypted **Slack** incoming webhooks and **Email (SMTP)** alerts with per-severity rules, duplicate suppression windows, and retryable delivery history.
- **Isolated Demo Sandbox:** Dedicated `is_demo=true` workspace (`POST /api/v1/demo/seed`) clearly separated from production customer data.

---

## Architecture

Modular monolith stack:
- **Frontend:** Next.js 14 (App Router), TypeScript, Tailwind CSS, Recharts, React Hook Form, Zod, TanStack Query.
- **Backend:** Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2.x, Alembic.
- **Workers & Infra:** PostgreSQL 16, Redis 7, Celery Worker & Beat, Docker Compose, Nginx.
- **Auth:** Supabase Auth (`RS256`/`ES256` JWKS + `HS256`) with gated `local_dev` mode for offline evaluation.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/DATABASE.md](docs/DATABASE.md) for full details.

---

## Installation & Local Development

1. Copy environment template and generate cryptographic keys:
   ```bash
   cp .env.example .env
   python scripts/generate_keys.py
   ```
2. Start services or run locally:
   - **Docker Compose:** `docker compose up --build` (add `--profile prod` to include Nginx on port 80)
   - **Manual local dev:** See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

---

## n8n Integration

See [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md) for configuring `X-N8N-API-KEY`, setting up the n8n **Error Trigger** workflow securely without exposing private n8n instances, and running safe local webhook tests.

---

## Testing

```bash
# Backend unit, integration, security & E2E scenario tests
cd backend
pytest -v
ruff check app tests

# Frontend typecheck, component tests & production build
cd frontend
npm run typecheck
npm test
npm run build
```

---

## Documentation Index
- [PRD](docs/PRD.md)
- [System Architecture](docs/ARCHITECTURE.md)
- [Database Schema](docs/DATABASE.md)
- [REST API Reference](docs/API.md)
- [Integrations Guide](docs/INTEGRATIONS.md)
- [Security Controls](docs/SECURITY.md) & [Vulnerability Reporting](SECURITY.md)
- [Development Guide](docs/DEVELOPMENT.md)
- [Deployment & Backups](docs/DEPLOYMENT.md)
- [Phase 6 Production Readiness Audit](docs/PRODUCTION_READINESS.md)
- [Phase 7 Infrastructure Verification](docs/INFRASTRUCTURE_VERIFICATION.md)
- [Phase 8 E2E Verification](docs/E2E_VERIFICATION.md)
- [Phase 9 Commercial Readiness](docs/COMMERCIAL_READINESS.md)
- [Phase 10 Launch Readiness & Runbook](docs/LAUNCH_READINESS.md)
- [Phase 11 Real-World Validation](docs/REAL_WORLD_VALIDATION.md)
- [Phase 11 Security Test Results](docs/SECURITY_TEST_RESULTS.md)
- [Phase 11 Beta Readiness](docs/BETA_READINESS.md)
- [Phase 11 Known Limitations](docs/KNOWN_LIMITATIONS.md)
- [Phase 12 External Service Setup](docs/EXTERNAL_SERVICE_SETUP.md)
- [Phase 12 Staging Deployment Checklist](docs/STAGING_DEPLOYMENT_CHECKLIST.md)
- [Phase 12 Production Configuration](docs/PRODUCTION_CONFIGURATION.md)
- [Phase 12 Production Status](docs/PRODUCTION_STATUS.md)

---

## Roadmap
- Additional automation platform connectors (Make, Zapier, Temporal) using the canonical `NormalizedExecutionEvent` interface.
- Stripe subscription checkout & webhook billing activation via `BillingProvider`.
- SAML/SSO enterprise workspace authentication.

---

## License
Licensing terms are pending final confirmation by the project owner. Do not redistribute commercially until `LICENSE` is added.
