# FlowSentry — Open-Source Release Readiness Checklist

**Assessment Date:** 2026-11-23  
**Baseline Commit:** `main` (`96b8f87` + Open-Core Decoupling & Release Governance Commit)  
**Release Gate Status:** **`READY FOR OPEN-SOURCE RELEASE`** *(Core decoupling, `AGPL-3.0-only` `LICENSE`, `NOTICE`, `CLA.md`, `.github/workflows/ci.yml`, and trademark notices added; configure `git remote origin` to push)*

---

## 1. Repository, Secret & Data Hygiene Inspection

| Check | Observed Evidence in Repository | Status | Action Required Before Public Release |
|---|---|---|---|
| **Secret Exposure in Working Tree & `.env`** | Only `.env.example` and `.env.production.example` (placeholder values only) are tracked. Local `.env` exists untracked and is excluded by `.gitignore`. `backups/` is empty locally. | **PASS** | Double-check `.gitignore` remains untouched; never `git add -f .env`. |
| **Git History Secret Scan (13 Commits)** | Full history grep (`sk-`, `sk_live`, `AIza`, `xoxb-`, `BEGIN PRIVATE KEY`, `supabase.co`, `192.168.`, `10.0.`) found **zero real secrets**—only placeholder test fixtures (`test_normalization_and_detection.py`, `test_phase11_security_and_monitors.py`, `test_security_foundation.py`) and SSRF test CIDRs (`ssrf.py`). | **PASS** | Optional: run `gitleaks` / `trufflehog` in CI prior to public launch as automated guard. |
| **Private Infra & Internal Endpoints** | `docker-compose.yml` & `.env.production.example` use generic container names and `.example` domains; no production IPs, server hostnames, or customer domains appear in source. | **PASS** | Keep host-specific `infrastructure/nginx/nginx.tls.conf` gitignored (verified). |
| **Sample Customer Data (`demo_service.py`)** | `backend/app/services/demo_service.py` contains clearly synthetic demo data (`[DEMO] Inbound Lead to HubSpot CRM`, `demo-inv-ok-*`, `FlowSentry Demo Sandbox`). No real customer names or PII exist. | **PASS** | Safe for public release. |
| **Author Identity in Git Commits** | All 13 commits list `Tahmid Zoayed <mdtahmidzoayed@gmail.com>`. | **INFO** | Confirm owner is comfortable exposing personal email in permanent public Git history (or configure GitHub no-reply + squash/rewrite before initial public push if desired). |
| **Internal Phase & Commercial Docs (`docs/`)** | `docs/` currently contains internal phase logs (`PRODUCTION_READINESS.md`, `COMMERCIAL_READINESS.md`, `REAL_WORLD_VALIDATION.md`, `STAGING_DEPLOYMENT_REPORT.md`) detailing internal pricing assumptions and test environments. | **ACTION NEEDED** | Curate `docs/` before public launch: keep public architecture, API, security, integration, and self-hosting docs; archive or move internal commercial/pricing strategy docs to private company repo. |
| **Missing `LICENSE`, `NOTICE` & `CLA`** | No root `LICENSE` file exists (`README.md` currently forbids commercial redistribution); no `CLA.md` or `NOTICE` exists; `CONTRIBUTING.md` lacks CLA/license terms. | **BLOCKER** | Owner must approve and add `LICENSE` (`AGPL-3.0-only`), `NOTICE` (third-party attributions incl. `psycopg` LGPLv3, `certifi`/`@vercel/og` MPL-2.0, `caniuse-lite` CC-BY-4.0, `@img/sharp` Apache-2.0/LGPL-3.0-or-later), `CLA.md`, and update `README.md` + `CONTRIBUTING.md`. |
| **Trademark & Non-Affiliation Notices** | Docs reference `n8n`, `Supabase`, `OpenAI`, `Gemini`, `Slack`, `HubSpot`, `Stripe` without an explicit trademark disclaimer. | **ACTION NEEDED** | Add standard third-party trademark disclaimer in `README.md`. |

---

## 2. Pre-Release Architectural Refactor Checklist (Required Before Public Release)

1. **[MUST] Decouple SaaS Quotas (`plans.py`) from Community Core:**
   - Remove hardcoded `$19/$59/$149` pricing and `max_members=1` / `max_projects=2` SaaS caps from default self-hosted paths (`workspace_service.py`, `project_service.py`, `integration_service.py`, `ingestion_service.py`, `outcomes/service.py`, `intelligence/service.py`, `workers/tasks.py`, `settings/page.tsx`).
   - Introduce an `EntitlementProvider` / `QuotaPolicy` abstraction defaulting to unmetered/self-hosted mode in Community Core.
2. **[MUST] Extract Commercial Extension Contracts (SPI):**
   - Introduce `ConnectorAdapter` registry (`integrations/`), `NotificationChannel` registry (`notifications/`), `AuthProvider` hook (`core/security.py`), and `EditionConfig` feature-flag API (`frontend/`) so Commercial/Enterprise modules can register cleanly without modifying Core files.
3. **[MUST] Neutralize Self-Hosted Auth Options:**
   - Ensure Community Core supports turnkey local username/password or generic OIDC alongside optional Supabase Auth so self-hosters are not forced into external Supabase Cloud accounts (`AUTH_MODE=local_dev` is currently framed only for local testing).
4. **[SHOULD] Separate `BillingProvider` Out of Core:**
   - Move `BillingProvider` / `NoopBillingProvider` and SaaS pricing metadata out of `backend/app/core/plans.py` into the Cloud control-plane service.
5. **[SHOULD] Remove Unused Sharp / Verify Container Attribution:**
   - Confirm Next.js `.next/standalone` builds preserve upstream notices (`sharp` / `@img/sharp-*` if bundled, `caniuse-lite`, `next`), or disable unused image optimization binaries if not required.

---

## 3. Proposed Public Repository Structure (`flowsentry` Community Edition)

```text
flowsentry/
├── .github/
│   ├── workflows/               # Public CI (pytest, ruff, tsc, vitest, next build, gitleaks)
│   ├── ISSUE_TEMPLATE/
│   └── PULL_REQUEST_TEMPLATE.md # Includes CLA / DCO check reminder
├── backend/
│   ├── app/
│   │   ├── api/v1/              # Core REST API + plugin router hook
│   │   ├── core/                # config, security, encryption, ssrf, rate_limit, logging, entitlements (SPI)
│   │   ├── db/                  # SQLAlchemy base/session
│   │   ├── detection/           # Incident grouping, fingerprinting, latency/frequency anomaly, recovery
│   │   ├── incidents/           # Incident lifecycle & notes
│   │   ├── integrations/        # Connector SPI + built-in n8n & custom_webhook + normalizer/sanitizer
│   │   ├── intelligence/        # BaseAIProvider SPI + OpenAI, Gemini, DeterministicFallbackAnalyzer
│   │   ├── models/              # Core 19-table schema (without commercial billing tables)
│   │   ├── notifications/       # NotificationChannel SPI + Slack & SMTP
│   │   ├── outcomes/            # 6 Business Outcome Monitor evaluators
│   │   ├── schemas/             # Pydantic contracts
│   │   ├── services/            # Workspaces, projects, ingestion, demo, audit, usage metrics
│   │   └── workers/             # Celery app & scheduled tasks
│   ├── migrations/              # Core Alembic history
│   └── tests/
├── frontend/                    # Next.js 16 Community UI (slot/feature-flag aware)
├── infrastructure/
│   ├── docker/
│   └── nginx/
├── scripts/                     # generate_keys.py, backup_db.sh, restore_db.sh
├── docs/                        # Public docs ONLY: architecture, API, self-hosting, integrations, security
├── .env.example
├── .env.production.example
├── CHANGELOG.md
├── CLA.md                       # Contributor License Agreement (before accepting PRs)
├── CODE_OF_CONDUCT.md
├── CONTRIBUTING.md
├── LICENSE                      # AGPL-3.0-only (added only upon explicit owner approval)
├── NOTICE                       # Third-party attributions (LGPLv3, MPL-2.0, Apache-2.0, CC-BY-4.0)
├── README.md                    # Community framing + Cloud/Enterprise link + trademark disclaimer
├── SECURITY.md
├── docker-compose.yml
└── docker-compose.staging.yml
```

*(Private companion repositories kept closed-source: `flowsentry-enterprise` for dual-licensed Enterprise extensions, and `flowsentry-cloud` for Stripe billing, hosted control plane, agency fleet portal, and Cloud infrastructure.)*
