export type WorkspaceRole = "owner" | "admin" | "member" | "viewer";
export type ProjectEnvironment = "production" | "staging" | "development";

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

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}
