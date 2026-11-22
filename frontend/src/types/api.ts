export type WorkspaceRole = "owner" | "admin" | "member" | "viewer";
export type ProjectEnvironment = "production" | "staging" | "development";
export type ExecutionStatus = "success" | "failed" | "running" | "waiting" | "canceled" | "unknown";
export type IncidentSeverity = "critical" | "high" | "medium" | "low" | "informational";
export type IncidentStatus = "open" | "acknowledged" | "investigating" | "resolved" | "reopened";

export interface User {
  id: string;
  email: string;
  name: string | null;
  avatar_url: string | null;
  created_at: string;
}

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  owner_id: string;
  plan: string;
  is_demo: boolean;
  settings: Record<string, unknown>;
  role: WorkspaceRole | null;
  created_at: string;
}

export interface AuthMeResponse {
  user: User;
  workspaces: Workspace[];
}

export interface Project {
  id: string;
  workspace_id: string;
  name: string;
  description: string | null;
  environment: ProjectEnvironment;
  created_at: string;
}

export interface WorkspaceMember {
  id: string;
  workspace_id: string;
  user_id: string;
  email: string;
  name: string | null;
  role: WorkspaceRole;
  joined_at: string;
}

export interface APIKey {
  id: string;
  workspace_id: string;
  name: string;
  key_prefix: string;
  scopes: string[];
  last_used_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

export interface APIKeyCreateResponse {
  api_key: APIKey;
  plaintext_key: string;
}

export interface PlanLimits {
  name: string;
  display_name: string;
  price_monthly_usd: number;
  max_projects: number;
  max_integrations: number;
  max_monthly_executions: number;
  max_monthly_ai_investigations: number;
  max_outcome_monitors: number;
  max_members: number;
  retention_days: number;
}

export interface UsageSummary {
  workspace_id: string;
  period_month: string;
  plan: PlanLimits;
  executions_count: number;
  ai_investigations_count: number;
  ai_tokens_used: number;
  projects_count: number;
  integrations_count: number;
  outcome_monitors_count: number;
  members_count: number;
}

export interface AuditLog {
  id: string;
  workspace_id: string;
  user_id: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  metadata_json: Record<string, unknown>;
  created_at: string;
}

export interface Integration {
  id: string;
  workspace_id: string;
  project_id: string;
  provider: "n8n" | "custom_webhook";
  connection_name: string;
  base_url: string | null;
  polling_enabled: boolean;
  polling_interval_seconds: number;
  status: "pending" | "connected" | "error" | "disconnected";
  last_error: string | null;
  last_connected_at: string | null;
  last_synced_at: string | null;
  has_credentials: boolean;
  created_at: string;
}

export interface IntegrationCreateResponse {
  integration: Integration;
  webhook_secret: string;
  webhook_url_path: string;
}

export interface IntegrationValidationResult {
  ok: boolean;
  status: string;
  message: string;
  workflows_accessible: number;
}

export interface IntegrationSyncResult {
  workflows_synced: number;
  executions_ingested: number;
  executions_deduplicated: number;
  incidents_created: number;
  incidents_updated: number;
}

export interface Workflow {
  id: string;
  workspace_id: string;
  project_id: string;
  integration_id: string;
  external_workflow_id: string;
  name: string;
  description: string | null;
  enabled: boolean;
  max_duration_ms: number | null;
  expected_interval_seconds: number | null;
  is_demo: boolean;
  execution_count: number;
  failed_count: number;
  failure_rate: number;
  avg_duration_ms: number | null;
  last_execution_at: string | null;
  last_execution_status: string | null;
  active_incidents_count: number;
  created_at: string;
}

export interface Execution {
  id: string;
  workspace_id: string;
  workflow_id: string;
  external_execution_id: string;
  schema_version: string;
  status: ExecutionStatus;
  started_at: string;
  finished_at: string | null;
  duration_ms: number | null;
  failed_node: string | null;
  error_type: string | null;
  error_summary: string | null;
  normalized_payload: Record<string, unknown>;
  is_demo: boolean;
  created_at: string;
}

export interface IncidentNote {
  id: string;
  incident_id: string;
  author_id: string | null;
  note_type: "comment" | "status_change" | "system";
  content: string;
  created_at: string;
}

export interface Incident {
  id: string;
  workspace_id: string;
  workflow_id: string;
  workflow_name: string | null;
  title: string;
  description: string | null;
  severity: IncidentSeverity;
  status: IncidentStatus;
  fingerprint: string;
  first_seen_at: string;
  last_seen_at: string;
  occurrence_count: number;
  assigned_to_user_id: string | null;
  resolved_at: string | null;
  resolution_reason: string | null;
  resolution_notes: string | null;
  is_demo: boolean;
  created_at: string;
}

export interface IncidentDetail extends Incident {
  notes: IncidentNote[];
  recent_executions: Execution[];
}

export interface TrendPoint {
  date: string;
  total: number;
  success: number;
  failed: number;
}

export type MonitorType =
  | "expected_interval"
  | "expected_count"
  | "required_output_fields"
  | "http_endpoint"
  | "webhook_confirmation"
  | "external_record_check";

export interface AIInvestigation {
  id: string;
  incident_id: string;
  workspace_id: string;
  provider: string;
  model: string;
  analysis_status: string;
  summary: string | null;
  root_cause_hypothesis: string | null;
  confidence: number | null;
  evidence: string[];
  possible_causes: string[];
  recommended_actions: string[];
  severity_assessment: string | null;
  requires_human_review: boolean;
  token_usage: Record<string, number>;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface OutcomeMonitor {
  id: string;
  workspace_id: string;
  workflow_id: string;
  workflow_name: string | null;
  name: string;
  description: string | null;
  monitor_type: MonitorType;
  configuration: Record<string, unknown>;
  expected_result: Record<string, unknown>;
  schedule_seconds: number;
  severity: "critical" | "high" | "medium" | "low";
  enabled: boolean;
  status: "healthy" | "failing" | "unknown";
  last_checked_at: string | null;
  last_success_at: string | null;
  last_failure_at: string | null;
  failure_evidence: Record<string, unknown> | null;
  is_demo: boolean;
  created_at: string;
}

export interface OutcomeMonitorRun {
  id: string;
  monitor_id: string;
  workspace_id: string;
  passed: boolean;
  evidence: Record<string, unknown>;
  duration_ms: number | null;
  checked_at: string;
}

export interface OutcomeCheckResult {
  monitor: OutcomeMonitor;
  run: OutcomeMonitorRun;
  incident_id: string | null;
}

export interface OverviewMetrics {
  total_workflows: number;
  healthy_workflows: number;
  total_executions: number;
  successful_executions: number;
  failed_executions: number;
  active_incidents: number;
  critical_incidents: number;
  monitors_total: number;
  monitors_failing: number;
  trends: TrendPoint[];
  recent_incidents: Incident[];
  recent_executions: Execution[];
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}
