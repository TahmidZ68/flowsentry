"use client";

import React, { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Mail, MessageSquare, RefreshCw, Send } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/input";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { useAuth } from "@/features/auth/auth-context";
import { formatRelativeDate } from "@/lib/utils";
import { apiService } from "@/services/api";

const ALL_EVENTS = [
  { id: "critical_incident", label: "Critical incident" },
  { id: "high_incident", label: "High-severity incident" },
  { id: "repeated_failure", label: "Repeated failure" },
  { id: "outcome_failure", label: "Outcome monitor failure" },
  { id: "incident_resolved", label: "Incident resolved" },
];

export default function NotificationsPage() {
  const { activeWorkspace } = useAuth();
  const queryClient = useQueryClient();
  const wsId = activeWorkspace?.id;
  const isAdmin = activeWorkspace?.role === "owner" || activeWorkspace?.role === "admin";

  const [slackUrl, setSlackUrl] = useState("");
  const [slackMinSeverity, setSlackMinSeverity] = useState("high");
  const [slackSuppression, setSlackSuppression] = useState(30);
  const [slackEnabled, setSlackEnabled] = useState(true);

  const [emailRecipients, setEmailRecipients] = useState("");
  const [emailMinSeverity, setEmailMinSeverity] = useState("high");
  const [emailSuppression, setEmailSuppression] = useState(30);
  const [emailEnabled, setEmailEnabled] = useState(true);

  const [feedback, setFeedback] = useState<string | null>(null);

  const prefsQuery = useQuery({
    queryKey: ["notification-prefs", wsId],
    queryFn: () => apiService.listNotificationPreferences(wsId!),
    enabled: Boolean(wsId),
  });

  const historyQuery = useQuery({
    queryKey: ["notifications-history", wsId],
    queryFn: () => apiService.listNotifications(wsId!),
    enabled: Boolean(wsId),
  });

  const saveSlackMutation = useMutation({
    mutationFn: () =>
      apiService.upsertNotificationPreference(wsId!, {
        channel: "slack",
        enabled: slackEnabled,
        slack_webhook_url: slackUrl.trim() || undefined,
        events: ALL_EVENTS.map((e) => e.id),
        min_severity: slackMinSeverity,
        suppression_minutes: Number(slackSuppression) || 30,
      }),
    onSuccess: async () => {
      setSlackUrl("");
      setFeedback("Slack notification preferences saved.");
      await queryClient.invalidateQueries({ queryKey: ["notification-prefs", wsId] });
    },
    onError: (err: Error) => setFeedback(err.message),
  });

  const saveEmailMutation = useMutation({
    mutationFn: () =>
      apiService.upsertNotificationPreference(wsId!, {
        channel: "email",
        enabled: emailEnabled,
        email_recipients: emailRecipients
          .split(",")
          .map((e) => e.trim())
          .filter(Boolean),
        events: ALL_EVENTS.map((e) => e.id),
        min_severity: emailMinSeverity,
        suppression_minutes: Number(emailSuppression) || 30,
      }),
    onSuccess: async () => {
      setEmailRecipients("");
      setFeedback("Email notification preferences saved.");
      await queryClient.invalidateQueries({ queryKey: ["notification-prefs", wsId] });
    },
    onError: (err: Error) => setFeedback(err.message),
  });

  const testMutation = useMutation({
    mutationFn: (channel: "slack" | "email") => apiService.testNotification(wsId!, channel),
    onSuccess: async (res) => {
      setFeedback(
        res.status === "sent"
          ? `Test ${res.channel} notification delivered.`
          : `Test ${res.channel} delivery status: ${res.status} (${res.error_message || ""})`
      );
      await queryClient.invalidateQueries({ queryKey: ["notifications-history", wsId] });
    },
    onError: (err: Error) => setFeedback(err.message),
  });

  const retryMutation = useMutation({
    mutationFn: (id: string) => apiService.retryNotification(wsId!, id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["notifications-history", wsId] });
    },
  });

  if (!activeWorkspace) {
    return <EmptyState title="No workspace selected" description="Select a workspace first." />;
  }

  const prefs = prefsQuery.data || [];
  const slackPref = prefs.find((p) => p.channel === "slack");
  const emailPref = prefs.find((p) => p.channel === "email");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight text-foreground">Notifications</h1>
        <p className="text-xs text-muted">
          Configure Slack and Email alert channels, severity thresholds, and duplicate suppression
        </p>
      </div>

      {feedback ? (
        <div className="rounded-md border border-border bg-surface-elevated px-3.5 py-2.5 text-xs text-foreground">
          {feedback}
        </div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Slack Channel */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <MessageSquare className="h-4 w-4 text-accent" />
              <div>
                <CardTitle>Slack Incoming Webhook</CardTitle>
                <CardDescription>
                  {slackPref?.has_config
                    ? `Configured: ${slackPref.masked_target}`
                    : "Webhook URLs are encrypted and never exposed"}
                </CardDescription>
              </div>
            </div>
            {slackPref ? (
              <Badge variant={slackPref.enabled ? "healthy" : "default"}>
                {slackPref.enabled ? "Enabled" : "Disabled"}
              </Badge>
            ) : null}
          </CardHeader>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              saveSlackMutation.mutate();
            }}
            className="space-y-3.5"
          >
            <div>
              <label htmlFor="slack-url" className="mb-1 block text-xs font-medium text-muted">
                Webhook URL {slackPref?.has_config ? "(leave blank to keep existing)" : ""}
              </label>
              <Input
                id="slack-url"
                type="password"
                placeholder="https://hooks.slack.com/services/..."
                value={slackUrl}
                onChange={(e) => setSlackUrl(e.target.value)}
                disabled={!isAdmin}
              />
            </div>

            <div className="grid grid-cols-3 gap-2">
              <div>
                <label htmlFor="slack-sev" className="mb-1 block text-xs font-medium text-muted">
                  Min severity
                </label>
                <Select
                  id="slack-sev"
                  value={slackMinSeverity}
                  onChange={(e) => setSlackMinSeverity(e.target.value)}
                  disabled={!isAdmin}
                >
                  <option value="critical">Critical</option>
                  <option value="high">High</option>
                  <option value="medium">Medium</option>
                  <option value="low">Low</option>
                </Select>
              </div>
              <div>
                <label htmlFor="slack-supp" className="mb-1 block text-xs font-medium text-muted">
                  Suppress (min)
                </label>
                <Input
                  id="slack-supp"
                  type="number"
                  min={0}
                  value={slackSuppression}
                  onChange={(e) => setSlackSuppression(Number(e.target.value))}
                  disabled={!isAdmin}
                />
              </div>
              <div className="flex items-end pb-1">
                <label className="flex items-center gap-2 text-xs text-foreground">
                  <input
                    type="checkbox"
                    checked={slackEnabled}
                    onChange={(e) => setSlackEnabled(e.target.checked)}
                    disabled={!isAdmin}
                  />
                  Enabled
                </label>
              </div>
            </div>

            {isAdmin ? (
              <div className="flex gap-2">
                <Button type="submit" size="sm" disabled={saveSlackMutation.isPending}>
                  Save Slack Settings
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => testMutation.mutate("slack")}
                  disabled={!slackPref?.has_config || testMutation.isPending}
                >
                  <Send className="h-3.5 w-3.5" />
                  Test
                </Button>
              </div>
            ) : null}
          </form>
        </Card>

        {/* Email Channel */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Mail className="h-4 w-4 text-accent" />
              <div>
                <CardTitle>Email Alerts (SMTP)</CardTitle>
                <CardDescription>
                  {emailPref?.has_config
                    ? `Recipients: ${emailPref.masked_target}`
                    : "Configure recipient addresses for incident digests"}
                </CardDescription>
              </div>
            </div>
            {emailPref ? (
              <Badge variant={emailPref.enabled ? "healthy" : "default"}>
                {emailPref.enabled ? "Enabled" : "Disabled"}
              </Badge>
            ) : null}
          </CardHeader>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              saveEmailMutation.mutate();
            }}
            className="space-y-3.5"
          >
            <div>
              <label htmlFor="email-recips" className="mb-1 block text-xs font-medium text-muted">
                Recipient emails (comma-separated)
              </label>
              <Input
                id="email-recips"
                placeholder="oncall@company.com, ops@company.com"
                value={emailRecipients}
                onChange={(e) => setEmailRecipients(e.target.value)}
                disabled={!isAdmin}
              />
            </div>

            <div className="grid grid-cols-3 gap-2">
              <div>
                <label htmlFor="email-sev" className="mb-1 block text-xs font-medium text-muted">
                  Min severity
                </label>
                <Select
                  id="email-sev"
                  value={emailMinSeverity}
                  onChange={(e) => setEmailMinSeverity(e.target.value)}
                  disabled={!isAdmin}
                >
                  <option value="critical">Critical</option>
                  <option value="high">High</option>
                  <option value="medium">Medium</option>
                  <option value="low">Low</option>
                </Select>
              </div>
              <div>
                <label htmlFor="email-supp" className="mb-1 block text-xs font-medium text-muted">
                  Suppress (min)
                </label>
                <Input
                  id="email-supp"
                  type="number"
                  min={0}
                  value={emailSuppression}
                  onChange={(e) => setEmailSuppression(Number(e.target.value))}
                  disabled={!isAdmin}
                />
              </div>
              <div className="flex items-end pb-1">
                <label className="flex items-center gap-2 text-xs text-foreground">
                  <input
                    type="checkbox"
                    checked={emailEnabled}
                    onChange={(e) => setEmailEnabled(e.target.checked)}
                    disabled={!isAdmin}
                  />
                  Enabled
                </label>
              </div>
            </div>

            {isAdmin ? (
              <div className="flex gap-2">
                <Button type="submit" size="sm" disabled={saveEmailMutation.isPending}>
                  Save Email Settings
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => testMutation.mutate("email")}
                  disabled={!emailPref?.has_config || testMutation.isPending}
                >
                  <Send className="h-3.5 w-3.5" />
                  Test
                </Button>
              </div>
            ) : null}
          </form>
        </Card>
      </div>

      {/* Delivery History */}
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Delivery History</CardTitle>
            <CardDescription>Sent, suppressed, and failed notification attempts</CardDescription>
          </div>
          <Bell className="h-4 w-4 text-slate-500" />
        </CardHeader>

        {historyQuery.isLoading ? (
          <LoadingState label="Loading delivery ledger..." />
        ) : historyQuery.isError ? (
          <ErrorState
            message={(historyQuery.error as Error).message}
            onRetry={() => void historyQuery.refetch()}
          />
        ) : (historyQuery.data?.items.length ?? 0) === 0 ? (
          <EmptyState
            title="No notifications dispatched yet"
            description="Configured alerts will appear here when incidents or outcome failures trigger."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-border text-muted">
                  <th className="pb-2 font-medium">Channel</th>
                  <th className="pb-2 font-medium">Event</th>
                  <th className="pb-2 font-medium">Status</th>
                  <th className="pb-2 font-medium">Attempts</th>
                  <th className="pb-2 font-medium">Details</th>
                  <th className="pb-2 font-medium">Time</th>
                  <th className="pb-2 font-medium"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {historyQuery.data!.items.map((n) => (
                  <tr key={n.id}>
                    <td className="py-2.5 pr-4 font-medium text-foreground">{n.channel}</td>
                    <td className="py-2.5 pr-4 font-mono text-muted">{n.event_type}</td>
                    <td className="py-2.5 pr-4">
                      <Badge
                        variant={
                          n.status === "sent"
                            ? "healthy"
                            : n.status === "failed"
                            ? "critical"
                            : n.status === "suppressed"
                            ? "warning"
                            : "default"
                        }
                      >
                        {n.status}
                      </Badge>
                    </td>
                    <td className="py-2.5 pr-4 font-mono text-muted">{n.attempt_count}</td>
                    <td className="py-2.5 pr-4 text-red-400">{n.error_message || "—"}</td>
                    <td className="py-2.5 pr-4 text-muted">
                      {formatRelativeDate(n.sent_at || n.created_at)}
                    </td>
                    <td className="py-2.5 text-right">
                      {isAdmin && n.status === "failed" ? (
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => retryMutation.mutate(n.id)}
                          disabled={retryMutation.isPending}
                        >
                          <RefreshCw className="h-3 w-3" />
                          Retry
                        </Button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
