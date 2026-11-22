import { apiRequest } from "@/lib/api-client";
import type {
  APIKey,
  APIKeyCreateResponse,
  AuditLog,
  AuthMeResponse,
  PaginatedResponse,
  Project,
  ProjectEnvironment,
  UsageSummary,
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

  listProjects: (workspaceId: string, environment?: string) => {
    const query = environment && environment !== "all" ? `?environment=${encodeURIComponent(environment)}` : "";
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
};
