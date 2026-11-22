import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import LoginPage from "@/app/login/page";
import ProjectsPage from "@/app/(app)/projects/page";
import { AppShell, NAV_ITEMS } from "@/components/layout/app-shell";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import * as authContextModule from "@/features/auth/auth-context";
import { apiService } from "@/services/api";

function renderWithQuery(ui: React.ReactElement) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe("FlowSentry Phase 1 Frontend", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders loading, empty, and error states", () => {
    render(
      <div>
        <LoadingState label="Loading telemetry" />
        <EmptyState title="Nothing here" description="Connect n8n to start" />
        <ErrorState message="Backend offline" />
      </div>
    );
    expect(screen.getByText("Loading telemetry")).toBeInTheDocument();
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
    expect(screen.getByText("Backend offline")).toBeInTheDocument();
  });

  it("validates login form and submits valid email in local dev mode", async () => {
    const signInWithDevToken = vi.fn().mockResolvedValue(undefined);
    vi.spyOn(authContextModule, "useAuth").mockReturnValue({
      user: null,
      workspaces: [],
      activeWorkspace: null,
      activeEnvironment: "all",
      isLoading: false,
      error: null,
      setActiveWorkspaceId: vi.fn(),
      setActiveEnvironment: vi.fn(),
      refreshAuth: vi.fn(),
      signInWithDevToken,
      signInWithSupabase: vi.fn(),
      signUpWithSupabase: vi.fn(),
      signOut: vi.fn(),
    });

    render(<LoginPage />);
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByText(/enter a valid email address/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/work email/i), {
      target: { value: "engineer@flowsentry.io" },
    });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

    await waitFor(() => {
      expect(signInWithDevToken).toHaveBeenCalledWith("engineer@flowsentry.io", "");
    });
  });

  it("renders AppShell with all 9 navigation items and workspace selector", () => {
    vi.spyOn(authContextModule, "useAuth").mockReturnValue({
      user: {
        id: "u1",
        email: "owner@acme.dev",
        name: "Owner",
        avatar_url: null,
        created_at: "2026-11-22T00:00:00Z",
      },
      workspaces: [
        {
          id: "w1",
          name: "Acme Agency",
          slug: "acme",
          owner_id: "u1",
          plan: "free",
          is_demo: false,
          settings: {},
          role: "owner",
          created_at: "2026-11-22T00:00:00Z",
        },
      ],
      activeWorkspace: {
        id: "w1",
        name: "Acme Agency",
        slug: "acme",
        owner_id: "u1",
        plan: "free",
        is_demo: false,
        settings: {},
        role: "owner",
        created_at: "2026-11-22T00:00:00Z",
      },
      activeEnvironment: "all",
      isLoading: false,
      error: null,
      setActiveWorkspaceId: vi.fn(),
      setActiveEnvironment: vi.fn(),
      refreshAuth: vi.fn(),
      signInWithDevToken: vi.fn(),
      signInWithSupabase: vi.fn(),
      signUpWithSupabase: vi.fn(),
      signOut: vi.fn(),
    });

    render(
      <AppShell>
        <div>Shell Child</div>
      </AppShell>
    );

    for (const item of NAV_ITEMS) {
      expect(screen.getByText(item.label)).toBeInTheDocument();
    }
    expect(screen.getByLabelText("Select workspace")).toBeInTheDocument();
    expect(screen.getByLabelText("Select environment")).toBeInTheDocument();
    expect(screen.getByText("Shell Child")).toBeInTheDocument();
  });

  it("lists projects and validates project creation", async () => {
    vi.spyOn(authContextModule, "useAuth").mockReturnValue({
      user: {
        id: "u1",
        email: "owner@acme.dev",
        name: "Owner",
        avatar_url: null,
        created_at: "2026-11-22T00:00:00Z",
      },
      workspaces: [],
      activeWorkspace: {
        id: "w1",
        name: "Acme Agency",
        slug: "acme",
        owner_id: "u1",
        plan: "free",
        is_demo: false,
        settings: {},
        role: "owner",
        created_at: "2026-11-22T00:00:00Z",
      },
      activeEnvironment: "all",
      isLoading: false,
      error: null,
      setActiveWorkspaceId: vi.fn(),
      setActiveEnvironment: vi.fn(),
      refreshAuth: vi.fn(),
      signInWithDevToken: vi.fn(),
      signInWithSupabase: vi.fn(),
      signUpWithSupabase: vi.fn(),
      signOut: vi.fn(),
    });

    vi.spyOn(apiService, "listProjects").mockResolvedValue({
      items: [
        {
          id: "p1",
          workspace_id: "w1",
          name: "Default Project",
          description: "Primary prod",
          environment: "production",
          created_at: "2026-11-22T00:00:00Z",
        },
      ],
      total: 1,
      limit: 50,
      offset: 0,
    });
    const createSpy = vi.spyOn(apiService, "createProject").mockResolvedValue({
      id: "p2",
      workspace_id: "w1",
      name: "Staging CRM",
      description: "",
      environment: "staging",
      created_at: "2026-11-22T00:00:00Z",
    });

    renderWithQuery(<ProjectsPage />);
    expect(await screen.findByText("Default Project")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/project name/i), {
      target: { value: "Staging CRM" },
    });
    fireEvent.change(screen.getByLabelText(/environment/i), {
      target: { value: "staging" },
    });
    fireEvent.click(screen.getByRole("button", { name: /create project/i }));

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith("w1", {
        name: "Staging CRM",
        description: "",
        environment: "staging",
      });
    });
  });
});
