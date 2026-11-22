# FlowSentry — REST API Reference (`/api/v1`)

Interactive OpenAPI documentation is available at `/docs` and `/openapi.json` when `ENVIRONMENT != "production"`.

## Authentication & Authorization
- All `/api/v1/workspaces/*` endpoints require `Authorization: Bearer <jwt>`.
- Backend verifies JWTs independently using Supabase JWKS (`RS256` / `ES256`) or `HS256` (`SUPABASE_JWT_SECRET`), or `LOCAL_DEV_JWT_SECRET` when `AUTH_MODE=local_dev` (blocked in production).
- Every workspace-scoped route enforces membership and role hierarchy (`owner > admin > member > viewer`).
- Webhook ingestion (`/api/v1/ingest/webhooks/n8n/{integration_id}`) authenticates using `X-FlowSentry-Webhook-Secret`.

## Health & Readiness
| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `GET` | `/ready` | Database (`SELECT 1`) and Redis connectivity check |

## Auth & Demo
| Method | Path | Role | Description |
|---|---|---|---|
| `GET` | `/api/v1/auth/me` | Authenticated | Current user profile and workspaces |
| `POST` | `/api/v1/auth/dev-token` | Public (`local_dev` only) | Issues local dev JWT (disabled in production) |
| `POST` | `/api/v1/demo/seed` | Authenticated | Creates or resets isolated `is_demo=true` workspace |

## Workspaces, Members, API Keys, Usage & Audit Logs
| Method | Path | Min Role | Description |
|---|---|---|---|
| `GET` | `/api/v1/workspaces` | Authenticated | List workspaces user belongs to |
| `POST` | `/api/v1/workspaces` | Authenticated | Create workspace (assigns caller as `owner`) |
| `GET` | `/api/v1/workspaces/{workspace_id}` | `viewer` | Workspace details |
| `PATCH` | `/api/v1/workspaces/{workspace_id}` | `admin` | Update workspace name/settings |
| `GET` | `/api/v1/workspaces/{workspace_id}/members` | `viewer` | List workspace members |
| `POST` | `/api/v1/workspaces/{workspace_id}/members` | `admin` | Add member by email |
| `PATCH` | `/api/v1/workspaces/{workspace_id}/members/{member_id}` | `admin` / `owner` | Update member role |
| `DELETE` | `/api/v1/workspaces/{workspace_id}/members/{member_id}` | `admin` | Remove non-owner member |
| `GET/POST/DELETE` | `/api/v1/workspaces/{workspace_id}/api-keys` | `admin` | Manage hashed API keys |
| `GET` | `/api/v1/workspaces/{workspace_id}/usage` | `viewer` | Current month usage & plan limits |
| `GET` | `/api/v1/workspaces/{workspace_id}/audit-logs` | `admin` | Paginated security audit log |

## Projects & Overview
| Method | Path | Min Role | Description |
|---|---|---|---|
| `GET` | `/api/v1/workspaces/{workspace_id}/projects` | `viewer` | List/filter projects by environment |
| `POST` | `/api/v1/workspaces/{workspace_id}/projects` | `admin` | Create project (enforces plan quota) |
| `PATCH` | `/api/v1/workspaces/{workspace_id}/projects/{project_id}` | `admin` | Update project |
| `GET` | `/api/v1/workspaces/{workspace_id}/overview` | `viewer` | Real KPIs, 14-day trend, recent incidents/executions |

## Integrations & Ingestion
| Method | Path | Min Role | Description |
|---|---|---|---|
| `GET/POST` | `/api/v1/workspaces/{workspace_id}/integrations` | `viewer` / `admin` | List or create n8n / webhook connection |
| `PATCH/DELETE` | `/api/v1/workspaces/{workspace_id}/integrations/{id}` | `admin` | Update or disconnect (scrubs credentials) |
| `POST` | `/api/v1/workspaces/{workspace_id}/integrations/{id}/validate` | `admin` | Live n8n API connectivity check |
| `POST` | `/api/v1/workspaces/{workspace_id}/integrations/{id}/sync` | `member` | Poll workflows & executions from n8n |
| `POST` | `/api/v1/workspaces/{workspace_id}/integrations/{id}/test-webhook` | `member` | Safe local test webhook trigger |
| `POST` | `/api/v1/ingest/webhooks/n8n/{integration_id}` | Webhook Secret | Idempotent n8n Error Trigger ingestion |
| `POST` | `/api/v1/workspaces/{workspace_id}/executions/ingest` | `member` | Direct canonical execution ingestion |

## Workflows, Executions, Incidents & Investigations
| Method | Path | Min Role | Description |
|---|---|---|---|
| `GET` | `/api/v1/workspaces/{workspace_id}/workflows` | `viewer` | List workflows with failure rate & latency stats |
| `GET/PATCH` | `/api/v1/workspaces/{workspace_id}/workflows/{workflow_id}` | `viewer` / `member` | Workflow detail & SLA thresholds |
| `GET` | `/api/v1/workspaces/{workspace_id}/executions` | `viewer` | Filterable execution history |
| `GET` | `/api/v1/workspaces/{workspace_id}/executions/{execution_id}` | `viewer` | Execution detail & timeline events |
| `GET` | `/api/v1/workspaces/{workspace_id}/incidents` | `viewer` | Search/filter incidents |
| `GET` | `/api/v1/workspaces/{workspace_id}/incidents/{incident_id}` | `viewer` | Incident detail, notes & related executions |
| `POST` | `/api/v1/workspaces/{workspace_id}/incidents/{id}/acknowledge` | `member` | Acknowledge incident |
| `POST` | `/api/v1/workspaces/{workspace_id}/incidents/{id}/investigate` | `member` | Mark investigating |
| `POST` | `/api/v1/workspaces/{workspace_id}/incidents/{id}/assign` | `member` | Assign to workspace member |
| `POST` | `/api/v1/workspaces/{workspace_id}/incidents/{id}/resolve` | `member` | Resolve with notes |
| `POST` | `/api/v1/workspaces/{workspace_id}/incidents/{id}/reopen` | `member` | Reopen resolved incident |
| `POST` | `/api/v1/workspaces/{workspace_id}/incidents/{id}/notes` | `member` | Add internal comment |
| `GET` | `/api/v1/workspaces/{workspace_id}/investigations` | `viewer` | List root-cause investigations |
| `POST` | `/api/v1/workspaces/{workspace_id}/incidents/{id}/investigations` | `member` | Run AI or deterministic investigation |

## Outcome Monitors & Notifications
| Method | Path | Min Role | Description |
|---|---|---|---|
| `GET/POST` | `/api/v1/workspaces/{workspace_id}/outcome-monitors` | `viewer` / `member` | List or create outcome monitor |
| `PATCH/DELETE` | `/api/v1/workspaces/{workspace_id}/outcome-monitors/{id}` | `member` | Update or delete monitor |
| `POST` | `/api/v1/workspaces/{workspace_id}/outcome-monitors/{id}/enable` | `member` | Enable monitor |
| `POST` | `/api/v1/workspaces/{workspace_id}/outcome-monitors/{id}/disable` | `member` | Disable monitor |
| `POST` | `/api/v1/workspaces/{workspace_id}/outcome-monitors/{id}/check` | `member` | Execute monitor check now |
| `POST` | `/api/v1/workspaces/{workspace_id}/outcome-monitors/{id}/confirm` | `member` | Record downstream webhook confirmation |
| `GET` | `/api/v1/workspaces/{workspace_id}/outcome-monitors/{id}/runs` | `viewer` | Monitor evaluation history |
| `GET` | `/api/v1/workspaces/{workspace_id}/notifications` | `viewer` | Notification delivery ledger |
| `GET/PUT` | `/api/v1/workspaces/{workspace_id}/notifications/preferences` | `viewer` / `admin` | Masked Slack/Email preferences |
| `POST` | `/api/v1/workspaces/{workspace_id}/notifications/test` | `admin` | Send test alert |
| `POST` | `/api/v1/workspaces/{workspace_id}/notifications/{id}/retry` | `admin` | Retry failed delivery |
