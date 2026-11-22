import { apiRequest } from "@/lib/api-client";
import type {
  APIKey,
  APIKeyCreateResponse,
  AuditLog,
  AuthMeResponse,
  Execution,
  Incident,
  IncidentDetail,
  IncidentNote,
  Integration,
  IntegrationCreateResponse,
  IntegrationSyncResult,
  IntegrationValidationResult,
  OverviewMetrics,
  PaginatedResponse,
  Project,
  ProjectEnvironment,
  UsageSummary,
  Workflow,
  Workspace,
  WorkspaceMember,
  WorkspaceRole,
} from "@/types/api";

export const apiService = {
  getMe: () => apiRequest<AuthMeResponse>("/auth/me"),

  issueDevToken: (email: string, name?: string) =>
    apiRequest<{ access_token: string; token_type: string }>("/auth/dev-token", {
      method: "POST",
      token: null,
      body: JSON.stringify({ email, name }),
    }),

  listWorkspaces: () => apiRequest<Workspace[]>("/workspaces"),

  createWorkspace: (name: string, slug?: string) =>
    apiRequest<Workspace>("/workspaces", {
      method: "POST",
      body: JSON.stringify({ name, slug: slug || undefined }),
    }),

  updateWorkspace: (workspaceId: string, data: { name?: string }) =>
    apiRequest<Workspace>(`/workspaces/${workspaceId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  getOverview: (workspaceId: string) =>
    apiRequest<OverviewMetrics>(`/workspaces/${workspaceId}/overview`),

  listProjects: (workspaceId: string, environment?: string) => {
    const query =
      environment && environment !== "all" ? `?environment=${encodeURIComponent(environment)}` : "";
    return apiRequest<PaginatedResponse<Project>>(`/workspaces/${workspaceId}/projects${query}`);
  },

  createProject: (
    workspaceId: string,
    data: { name: string; description?: string; environment: ProjectEnvironment }
  ) =>
    apiRequest<Project>(`/workspaces/${workspaceId}/projects`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  listMembers: (workspaceId: string) =>
    apiRequest<WorkspaceMember[]>(`/workspaces/${workspaceId}/members`),

  addMember: (workspaceId: string, email: string, role: Exclude<WorkspaceRole, "owner">) =>
    apiRequest<WorkspaceMember>(`/workspaces/${workspaceId}/members`, {
      method: "POST",
      body: JSON.stringify({ email, role }),
    }),

  removeMember: (workspaceId: string, memberId: string) =>
    apiRequest<void>(`/workspaces/${workspaceId}/members/${memberId}`, {
      method: "DELETE",
    }),

  listApiKeys: (workspaceId: string) =>
    apiRequest<APIKey[]>(`/workspaces/${workspaceId}/api-keys`),

  createApiKey: (workspaceId: string, name: string) =>
    apiRequest<APIKeyCreateResponse>(`/workspaces/${workspaceId}/api-keys`, {
      method: "POST",
      body: JSON.stringify({ name, scopes: ["ingest:write"] }),
    }),

  revokeApiKey: (workspaceId: string, keyId: string) =>
    apiRequest<void>(`/workspaces/${workspaceId}/api-keys/${keyId}`, {
      method: "DELETE",
    }),

  getUsage: (workspaceId: string) =>
    apiRequest<UsageSummary>(`/workspaces/${workspaceId}/usage`),

  listAuditLogs: (workspaceId: string) =>
    apiRequest<PaginatedResponse<AuditLog>>(`/workspaces/${workspaceId}/audit-logs?limit=25`),

  // Integrations
  listIntegrations: (workspaceId: string) =>
    apiRequest<Integration[]>(`/workspaces/${workspaceId}/integrations`),

  createIntegration: (
    workspaceId: string,
    data: {
      project_id: string;
      provider: "n8n" | "custom_webhook";
      connection_name: string;
      base_url?: string;
      api_key?: string;
      polling_enabled?: boolean;
      polling_interval_seconds?: number;
    }
  ) =>
    apiRequest<IntegrationCreateResponse>(`/workspaces/${workspaceId}/integrations`, {
      method: "POST",
      body: JSON.stringify(data),
    }),

  validateIntegration: (workspaceId: string, integrationId: string) =>
    apiRequest<IntegrationValidationResult>(
      `/workspaces/${workspaceId}/integrations/${integrationId}/validate`,
      { method: "POST" }
    ),

  syncIntegration: (workspaceId: string, integrationId: string) =>
    apiRequest<IntegrationSyncResult>(
      `/workspaces/${workspaceId}/integrations/${integrationId}/sync`,
      { method: "POST" }
    ),

  sendTestWebhook: (workspaceId: string, integrationId: string) =>
    apiRequest<{ execution_id: string; incident_id: string | null }>(
      `/workspaces/${workspaceId}/integrations/${integrationId}/test-webhook`,
      { method: "POST" }
    ),

  disconnectIntegration: (workspaceId: string, integrationId: string) =>
    apiRequest<void>(`/workspaces/${workspaceId}/integrations/${integrationId}`, {
      method: "DELETE",
    }),

  // Workflows & Executions
  listWorkflows: (workspaceId: string, environment?: string, search?: string) => {
    const params = new URLSearchParams();
    if (environment && environment !== "all") params.set("environment", environment);
    if (search) params.set("search", search);
    const qs = params.toString();
    return apiRequest<PaginatedResponse<Workflow>>(
      `/workspaces/${workspaceId}/workflows${qs ? `?${qs}` : ""}`
    );
  },

  getWorkflow: (workspaceId: string, workflowId: string) =>
    apiRequest<Workflow>(`/workspaces/${workspaceId}/workflows/${workflowId}`),

  updateWorkflow: (
    workspaceId: string,
    workflowId: string,
    data: { max_duration_ms?: number | null; expected_interval_seconds?: number | null; enabled?: boolean }
  ) =>
    apiRequest<Workflow>(`/workspaces/${workspaceId}/workflows/${workflowId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  listExecutions: (workspaceId: string, workflowId?: string, status?: string) => {
    const params = new URLSearchParams();
    if (workflowId) params.set("workflow_id", workflowId);
    if (status) params.set("status", status);
    const qs = params.toString();
    return apiRequest<PaginatedResponse<Execution>>(
      `/workspaces/${workspaceId}/executions${qs ? `?${qs}` : ""}`
    );
  },

  // Incidents
  listIncidents: (
    workspaceId: string,
    filters?: { search?: string; severity?: string; status?: string; workflow_id?: string }
  ) => {
    const params = new URLSearchParams();
    if (filters?.search) params.set("search", filters.search);
    if (filters?.severity) params.set("severity", filters.severity);
    if (filters?.status) params.set("status", filters.status);
    if (filters?.workflow_id) params.set("workflow_id", filters.workflow_id);
    const qs = params.toString();
    return apiRequest<PaginatedResponse<Incident>>(
      `/workspaces/${workspaceId}/incidents${qs ? `?${qs}` : ""}`
    );
  },

  getIncident: (workspaceId: string, incidentId: string) =>
    apiRequest<IncidentDetail>(`/workspaces/${workspaceId}/incidents/${incidentId}`),

  acknowledgeIncident: (workspaceId: string, incidentId: string) =>
    apiRequest<Incident>(`/workspaces/${workspaceId}/incidents/${incidentId}/acknowledge`, {
      method: "POST",
    }),

  investigateIncident: (workspaceId: string, incidentId: string) =>
    apiRequest<Incident>(`/workspaces/${workspaceId}/incidents/${incidentId}/investigate`, {
      method: "POST",
    }),

  resolveIncident: (workspaceId: string, incidentId: string, resolutionNotes?: string) =>
    apiRequest<Incident>(`/workspaces/${workspaceId}/incidents/${incidentId}/resolve`, {
      method: "POST",
      body: JSON.stringify({ resolution_notes: resolutionNotes || undefined }),
    }),

  reopenIncident: (workspaceId: string, incidentId: string) =>
    apiRequest<Incident>(`/workspaces/${workspaceId}/incidents/${incidentId}/reopen`, {
      method: "POST",
    }),

  addIncidentNote: (workspaceId: string, incidentId: string, content: string) =>
    apiRequest<IncidentNote>(`/workspaces/${workspaceId}/incidents/${incidentId}/notes`, {
      method: "POST",
      body: JSON.stringify({ content }),
    }),
};
