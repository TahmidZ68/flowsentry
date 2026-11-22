import React from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import NotificationsPage from "@/app/(app)/notifications/page";
import * as authContextModule from "@/features/auth/auth-context";
import { apiService } from "@/services/api";

function renderWithQuery(ui: React.ReactElement) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

const mockAuth = {
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

describe("Phase 4 Notifications UI", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(authContextModule, "useAuth").mockReturnValue(mockAuth);
  });

  it("renders masked notification preferences, delivery history, and saves Slack settings", async () => {
    vi.spyOn(apiService, "listNotificationPreferences").mockResolvedValue([
      {
        id: "pref-1",
        workspace_id: "w1",
        channel: "slack",
        enabled: true,
        has_config: true,
        masked_target: "https://hooks.slack.com/...1234",
        events: ["critical_incident"],
        min_severity: "high",
        suppression_minutes: 30,
        updated_at: "2026-11-22T00:00:00Z",
      },
    ]);
    vi.spyOn(apiService, "listNotifications").mockResolvedValue({
      items: [
        {
          id: "notif-1",
          workspace_id: "w1",
          incident_id: "inc-1",
          channel: "slack",
          event_type: "critical_incident",
          dedup_key: "k1",
          status: "sent",
          attempt_count: 1,
          error_message: null,
          sent_at: "2026-11-22T12:00:00Z",
          created_at: "2026-11-22T12:00:00Z",
        },
      ],
      total: 1,
      limit: 50,
      offset: 0,
    });
    const upsertSpy = vi.spyOn(apiService, "upsertNotificationPreference").mockResolvedValue({
      id: "pref-1",
      workspace_id: "w1",
      channel: "slack",
      enabled: true,
      has_config: true,
      masked_target: "https://hooks.slack.com/...9999",
      events: ["critical_incident"],
      min_severity: "critical",
      suppression_minutes: 30,
      updated_at: "2026-11-22T00:00:00Z",
    });

    renderWithQuery(<NotificationsPage />);
    expect(await screen.findByText(/hooks\.slack\.com\/\.\.\.1234/)).toBeInTheDocument();
    expect(await screen.findByText("critical_incident")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Webhook URL/i), {
      target: { value: "https://hooks.slack.com/services/T/B/9999" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save slack settings/i }));

    await waitFor(() => {
      expect(upsertSpy).toHaveBeenCalledWith(
        "w1",
        expect.objectContaining({
          channel: "slack",
          slack_webhook_url: "https://hooks.slack.com/services/T/B/9999",
        })
      );
    });
  });
});
