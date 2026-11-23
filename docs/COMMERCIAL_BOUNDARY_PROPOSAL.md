# FlowSentry — Commercial Boundary & Licensing Strategy Proposal

**Assessment Date:** 2026-11-23  
**Scope:** Architectural separation feasibility (`Community Core` vs `Commercial Extension` vs `Managed Cloud`) and license selection (`AGPL-3.0-only` vs `Apache-2.0` vs `MIT`)

---

## 1. Licensing Strategy Comparison

| Criterion | `AGPL-3.0-only` *(Dual-Licensed w/ Commercial)* | `Apache-2.0` | `MIT` |
|---|---|---|---|
| **Developer & Agency Adoption** | High among self-hosters who run internal ops tools (like Grafana/n8n/PostHog ecosystems); slight friction for enterprise legal review if modifying code. | Very high enterprise/cloud adoption; zero network-copyleft friction. | Highest raw frictionless adoption across libraries/startups. |
| **Cloud / SaaS Competitor Protection** | **Strong:** Any third-party cloud vendor hosting a modified/extended FlowSentry SaaS must open-source their modifications under AGPL-3.0 unless buying a Commercial license. | **Weak:** A cloud hyperscaler or SaaS competitor can fork FlowSentry, bundle proprietary billing/UI/connectors, and host a competing SaaS with zero code give-back. | **None:** Competitors can take the entire platform closed-source and sell it commercially overnight. |
| **Enterprise Procurement Acceptance** | Moderate to Good when paired with a **Commercial License** (enterprises buy Commercial license to avoid AGPL audit scope when extending or white-labeling). | Excellent (default enterprise preference). | Excellent. |
| **Contributor Expectations** | Expect open-source parity for core monitoring/n8n; strongly resist artificial feature crippling (like `max_members=1` in self-hosted). Requires transparent **CLA** if dual-licensed. | Expect permissive upstream; no CLA strictly needed unless keeping private forks (though Apache-2.0 already has patent grant). | Expect permissive usage; lowest CLA willingness. |
| **Dual-Licensing Feasibility** | **High right now** (`git log` shows 100% single author `Tahmid Zoayed`). Becomes impossible later unless every external PR signs a **CLA** granting commercial relicensing rights. | Unnecessary (third parties can already commercialize forks without dual licensing). | Unnecessary (anyone can take it proprietary). |

### Recommended Licensing Strategy

**Adopt `AGPL-3.0-only` for FlowSentry Community + Dual-Licensed Commercial / Enterprise Edition (with a mandatory CLA before accepting outside PRs).**

**Why this fits FlowSentry best:**
1. FlowSentry is an end-user SaaS/self-hosted application—not a low-level developer SDK—so preventing unreciprocated SaaS cloning (`AGPL-3.0-only`) directly protects FlowSentry Cloud revenue.
2. FlowSentry's primary initial users (n8n automation agencies and developers) are already comfortable with strong source-available/copyleft operational tools.
3. Because 100% of existing commits (`13/13`) belong to a single author (`Tahmid Zoayed`), establishing dual licensing (`AGPL-3.0-only` public repo + Commercial Enterprise/Cloud rights) and a **Contributor License Agreement (CLA)** *prior to public launch* avoids the relicensing dead-end that traps multi-contributor OSS projects later.

> [!IMPORTANT]
> Do **not** mix `AGPL-3.0-only` core with `Open-Core` false scarcity (such as locking Community Edition to `max_members=1` or `1,000` executions/month). A crippled AGPL core damages community trust and invites hostile forks. Keep core reliability, RBAC, n8n integration, all 6 outcome monitors, and BYO-key AI **unmetered** in Community Edition, and monetize **Hosted Cloud convenience, Enterprise Governance (SAML/SCIM), Agency Fleet Management, and Commercial Platform Connectors**.

---

## 2. Commercial Separation Feasibility (Observed Architecture vs Target State)

| Target Capability | Can It Separate Cleanly Today? | Observed Bottleneck in Current Repo | Required Architectural Refactoring |
|---|---|---|---|
| **1. Fully Functional Self-Hosted Community Edition** | **No (Minor Blocker)** | `backend/app/core/plans.py` defaults new workspaces to `plan="free"` (`max_members=1`, `max_projects=2`, `max_integrations=2`, `max_monthly_executions=1000`, `max_outcome_monitors=3`), enforced across 6 services + Celery Beat retention cleanup, and rendered as `$0/mo` SaaS plans in `frontend/src/app/(app)/settings/page.tsx`. | Introduce an **`EditionEntitlementProvider` / `QuotaPolicy` protocol**: `SelfHostedQuotaPolicy` (unmetered or operator-env configured limits, hiding SaaS pricing badges) vs `CloudPlanQuotaPolicy` (enforces `Free`/`Pro`/`Agency`/`Business` SaaS tiers). |
| **2. Separate Commercial Control Plane & Billing** | **Partially** | `BillingProvider` protocol exists in `plans.py`, but `workspaces.plan`, `usage_records`, and `get_plan_limits` are embedded in Core DB models (`identity.py`) and routes (`workspaces.py`). | Keep telemetry `UsageRecord` counters in Core as neutral metrics, move `PLANS` pricing & `StripeBillingProvider` out of `app/core/plans.py` into a separate **Cloud Control Plane service** communicating via signed service-to-service API / webhook sync (`POST /internal/entitlements`). |
| **3. Proprietary Enterprise Integrations (`Make`, `Zapier`, `Temporal`, `PagerDuty`, `SAML`)** | **No (Structural Gap)** | `integration_service.py` hardcodes `provider == "n8n"`/`"custom_webhook"`; `notifications/service.py` hardcodes `channel == "slack"`/`"email"`; `security.py` hardcodes `supabase`/`local_dev`; `api/v1/router.py` statically binds all 13 routers. | Define formal internal SPIs in Core (`ConnectorRegistry`, `NotificationChannelRegistry`, `AuthProviderProtocol`, `AIProviderProtocol`) + Python entry-points (`importlib.metadata.entry_points`) OR out-of-process ingestion microservices pushing `NormalizedExecutionEvent` (`POST /api/v1/ingest/executions`). |
| **4. Agency Cross-Workspace Fleet Management & Client Portals** | **Yes (Out-of-Process Recommended)** | Current UI handles one `activeWorkspace` at a time (`auth-context.tsx`), with no cross-workspace rollup endpoints. | Build Agency Fleet Portal as a **separate Commercial/Cloud frontend + aggregation API** reading workspace summaries via scoped API tokens or read-only replica/events—avoiding deep changes to single-workspace Core UI. |
| **5. Advanced Reporting, BI Exports & Warehouse Sync** | **Yes (Out-of-Process Recommended)** | `overview.py` computes 14-day counts inline via SQLAlchemy; no export pipelines exist. | Stream normalized execution/incident domain events from Core (webhook/Redis stream/CDC) to an out-of-process Enterprise Analytics worker writing Parquet/Snowflake/BigQuery/PDF SLA reports. |
| **6. Managed Cloud Infrastructure (`FlowSentry Cloud`)** | **Yes** | Currently uses single-server Docker Compose (`docker-compose.yml` + `docker-compose.staging.yml`). | Keep Docker Compose for self-hosted Community; build Cloud Terraform/Helm/K8s manifests, managed PostgreSQL/Redis, pooled AI gateway, and multi-tenant observability in a **separate private `flowsentry-cloud-infra` repository**. |

---

## 3. Recommended Two-Layer Boundary (Preventing Accidental Copyleft Leakage)

1. **In-Process Extension Boundary (Dual-Licensed EE Package, Same Author / CLA Covered):**
   - Core (`flowsentry` repo, `AGPL-3.0-only`) exposes clean Python `Protocol` registries and optional plugin entry points (`flowsentry.plugins`).
   - Only works for proprietary plugins if the vendor holding **Commercial dual-license rights** (FlowSentry, backed by sole ownership + CLAs) distributes/hosts the combined Enterprise Edition.
2. **Process & Network Boundary (Recommended for Cloud SaaS Control Plane, Billing, Fleet & Warehouse Sync):**
   - Separate services (`flowsentry-cloud-billing`, `flowsentry-agency-portal`, `flowsentry-connector-runners`) run in **independent containers/processes** communicating with FlowSentry Core strictly over documented **HTTP REST (`NormalizedExecutionEvent` ingestion API, `/api/v1/workspaces/{id}/usage`)** or queue contracts.
   - This guarantees zero shared Python/TypeScript runtime linking between closed operational SaaS tooling and the `AGPL-3.0-only` Core repository.
