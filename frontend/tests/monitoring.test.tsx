import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import IncidentsPage from "@/app/(app)/incidents/page";
import IntegrationsPage from "@/app/(app)/integrations/page";
import OverviewPage from "@/app/(app)/overview/page";
import * as authContextModule from "@/features/auth/auth-context";
import { apiService } from "@/services/api";

function renderWithQuery(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const mockAuthValue = {
  user: {
    id: "u1",
    email: "ops@acme.dev",
    name: "Ops",
    avatar_url: null,
    created_at: "2026-11-22T00:00:00Z",
  },
  workspaces: [],
  activeWorkspace: {
    id: "w1",
    name: "Acme Ops",
    slug: "acme-ops",
    owner_id: "u1",
    plan: "pro",
    is_demo: false,
    settings: {},
    role: "owner" as const,
    created_at: "2026-11-22T00:00:00Z",
  },
  activeEnvironment: "all" as const,
  isLoading: false,
  error: null,
  setActiveWorkspaceId: vi.fn(),
  setActiveEnvironment: vi.fn(),
  refreshAuth: vi.fn(),
  signInWithDevToken: vi.fn(),
  signInWithSupabase: vi.fn(),
  signUpWithSupabase: vi.fn(),
  signOut: vi.fn(),
};

describe("Phase 2 Monitoring UI", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(authContextModule, "useAuth").mockReturnValue(mockAuthValue);
  });

  it("renders real overview metrics and empty trend state when 0 executions", async () => {
    vi.spyOn(apiService, "getOverview").mockResolvedValue({
      total_workflows: 2,
      healthy_workflows: 1,
      total_executions: 0,
      successful_executions: 0,
      failed_executions: 0,
      active_incidents: 1,
      critical_incidents: 0,
      monitors_total: 0,
      monitors_failing: 0,
      trends: [],
      recent_incidents: [],
      recent_executions: [],
    });

    renderWithQuery(<OverviewPage />);
    expect(await screen.findByText("Monitored Workflows")).toBeInTheDocument();
    expect(screen.getByText("No execution history recorded yet")).toBeInTheDocument();
  });

  it("filters incidents by severity and status", async () => {
    vi.spyOn(apiService, "listWorkflows").mockResolvedValue({
      items: [],
      total: 0,
      limit: 50,
      offset: 0,
    });
    const listIncSpy = vi.spyOn(apiService, "listIncidents").mockResolvedValue({
      items: [
        {
          id: "inc-1",
          workspace_id: "w1",
          workflow_id: "wf-1",
          workflow_name: "Lead Sync",
          title: "Lead Sync: HTTP_429 at node 'HubSpot'",
          description: "Rate limit exceeded",
          severity: "critical",
          status: "open",
          fingerprint: "fp1",
          first_seen_at: "2026-11-22T12:00:00Z",
          last_seen_at: "2026-11-22T12:10:00Z",
          occurrence_count: 3,
          assigned_to_user_id: null,
          resolved_at: null,
          resolution_reason: null,
          resolution_notes: null,
          is_demo: false,
          created_at: "2026-11-22T12:00:00Z",
        },
      ],
      total: 1,
      limit: 50,
      offset: 0,
    });

    renderWithQuery(<IncidentsPage />);
    expect(await screen.findByText(/Lead Sync: HTTP_429/)).toBeInTheDocument();
    expect(screen.getByText("3x")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Filter by severity"), {
      target: { value: "critical" },
    });

    await waitFor(() => {
      expect(listIncSpy).toHaveBeenLastCalledWith("w1", {
        search: undefined,
        severity: "critical",
        status: undefined,
        workflow_id: undefined,
      });
    });
  });

  it("renders integrations setup guide and submits new webhook integration", async () => {
    vi.spyOn(apiService, "listProjects").mockResolvedValue({
      items: [
        {
          id: "proj-1",
          workspace_id: "w1",
          name: "Default Project",
          description: null,
          environment: "production",
          created_at: "2026-11-22T00:00:00Z",
        },
      ],
      total: 1,
      limit: 50,
      offset: 0,
    });
    vi.spyOn(apiService, "listIntegrations").mockResolvedValue([]);
    const createIntSpy = vi.spyOn(apiService, "createIntegration").mockResolvedValue({
      integration: {
        id: "int-1",
        workspace_id: "w1",
        project_id: "proj-1",
        provider: "custom_webhook",
        connection_name: "Error Hook",
        base_url: null,
        polling_enabled: false,
        polling_interval_seconds: 120,
        status: "connected",
        last_error: null,
        last_connected_at: null,
        last_synced_at: null,
        has_credentials: false,
        created_at: "2026-11-22T00:00:00Z",
      },
      webhook_secret: "fs_whsec_test123",
      webhook_url_path: "/api/v1/ingest/webhooks/n8n/int-1",
    });

    renderWithQuery(<IntegrationsPage />);
    expect(await screen.findByText("n8n Error Trigger Setup Guide")).toBeInTheDocument();
    expect(await screen.findByText(/Default Project/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Project"), { target: { value: "proj-1" } });
    fireEvent.change(screen.getByLabelText("Provider"), { target: { value: "custom_webhook" } });
    fireEvent.change(screen.getByLabelText("Connection name"), { target: { value: "Error Hook" } });
    fireEvent.click(screen.getByRole("button", { name: /connect integration/i }));

    await waitFor(() => {
      expect(createIntSpy).toHaveBeenCalled();
    });
    expect(await screen.findByText(/fs_whsec_test123/)).toBeInTheDocument();
  });
});
