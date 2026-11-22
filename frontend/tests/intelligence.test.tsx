import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import InvestigationsPage from "@/app/(app)/investigations/page";
import OutcomeMonitorsPage from "@/app/(app)/monitors/page";
import * as authContextModule from "@/features/auth/auth-context";
import { apiService } from "@/services/api";

function renderWithQuery(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const mockAuth = {
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
    slug: "acme",
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

describe("Phase 3 Intelligence & Outcome Monitors UI", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(authContextModule, "useAuth").mockReturnValue(mockAuth);
  });

  it("renders investigations list with evidence and recommended actions", async () => {
    vi.spyOn(apiService, "listInvestigations").mockResolvedValue({
      items: [
        {
          id: "inv-1",
          incident_id: "inc-1",
          workspace_id: "w1",
          provider: "deterministic",
          model: "rule-engine-v1",
          analysis_status: "completed",
          summary: "Rate limit exceeded on HubSpot",
          root_cause_hypothesis: "Burst webhook calls exceeded API quota",
          confidence: 0.86,
          evidence: ["Observed HTTP 429"],
          possible_causes: ["Burst traffic"],
          recommended_actions: ["Enable exponential backoff"],
          severity_assessment: "high",
          requires_human_review: true,
          token_usage: {},
          error_message: null,
          created_at: "2026-11-22T12:00:00Z",
          completed_at: "2026-11-22T12:00:01Z",
        },
      ],
      total: 1,
      limit: 50,
      offset: 0,
    });

    renderWithQuery(<InvestigationsPage />);
    expect(await screen.findByText("Rate limit exceeded on HubSpot")).toBeInTheDocument();
    expect(screen.getByText("Observed HTTP 429")).toBeInTheDocument();
    expect(screen.getByText("Enable exponential backoff")).toBeInTheDocument();
  });

  it("renders outcome monitors and creates a required_output_fields monitor", async () => {
    vi.spyOn(apiService, "listWorkflows").mockResolvedValue({
      items: [
        {
          id: "wf-1",
          workspace_id: "w1",
          project_id: "p1",
          integration_id: "int-1",
          external_workflow_id: "1",
          name: "Lead Capture",
          description: null,
          enabled: true,
          max_duration_ms: null,
          expected_interval_seconds: null,
          is_demo: false,
          execution_count: 5,
          failed_count: 0,
          failure_rate: 0,
          avg_duration_ms: 400,
          last_execution_at: null,
          last_execution_status: "success",
          active_incidents_count: 0,
          created_at: "2026-11-22T00:00:00Z",
        },
      ],
      total: 1,
      limit: 50,
      offset: 0,
    });
    vi.spyOn(apiService, "listOutcomeMonitors").mockResolvedValue([]);
    const createSpy = vi.spyOn(apiService, "createOutcomeMonitor").mockResolvedValue({
      id: "mon-1",
      workspace_id: "w1",
      workflow_id: "wf-1",
      workflow_name: "Lead Capture",
      name: "CRM Contact Created",
      description: null,
      monitor_type: "required_output_fields",
      configuration: { required_fields: ["metadata.crm_id"] },
      expected_result: { required_fields: ["metadata.crm_id"] },
      schedule_seconds: 300,
      severity: "high",
      enabled: true,
      status: "unknown",
      last_checked_at: null,
      last_success_at: null,
      last_failure_at: null,
      failure_evidence: null,
      is_demo: false,
      created_at: "2026-11-22T00:00:00Z",
    });

    renderWithQuery(<OutcomeMonitorsPage />);
    expect(await screen.findByText("Lead Capture")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Target workflow"), { target: { value: "wf-1" } });
    fireEvent.change(screen.getByLabelText("Monitor name"), {
      target: { value: "CRM Contact Created" },
    });
    fireEvent.change(screen.getByLabelText("Check target / threshold"), {
      target: { value: "metadata.crm_id" },
    });
    fireEvent.click(screen.getByRole("button", { name: /create monitor/i }));

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith(
        "w1",
        expect.objectContaining({
          workflow_id: "wf-1",
          name: "CRM Contact Created",
          monitor_type: "required_output_fields",
          configuration: { required_fields: ["metadata.crm_id"] },
        })
      );
    });
  });
});
