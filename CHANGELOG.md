# Changelog

## [0.1.0] - 2026-11-22
### Added
- **Phase 0:** PRD, System Architecture, PostgreSQL 16 Database Design, and Implementation Plan.
- **Phase 1:** Modular monorepo, Docker Compose stack, 19-table SQLAlchemy 2.x schema + Alembic migration, Supabase JWKS + gated local-dev JWT verification, multi-tenant workspaces/projects/RBAC, API keys, usage metering, audit logs, and dark-first Next.js UI.
- **Phase 2:** Canonical Normalized Event Model (`v1.0`), secret/PII payload sanitizer, n8n REST API v1 + Error Trigger webhook adapter, deterministic failure/latency detection, incident lifecycle API & UI, Workflows & Integrations screens.
- **Phase 3:** Provider-independent AI Investigation Engine (OpenAI, Gemini, deterministic fallback), 6 business outcome monitor evaluators, recovery verification, and isolated demo sandbox (`is_demo=true`).
- **Phase 4:** Encrypted Slack & Email notifications, duplicate suppression, failed delivery retries, and Notifications ledger UI.
- **Phase 5:** Per-plan retention cleanup worker, Nginx production Compose profile, backup script, and complete operational/API/security documentation.
