"use client";

import React, { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Plus, Trash2, UserPlus } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/input";
import { EmptyState, LoadingState } from "@/components/ui/states";
import { useAuth } from "@/features/auth/auth-context";
import { formatRelativeDate } from "@/lib/utils";
import { apiService } from "@/services/api";
import type { WorkspaceRole } from "@/types/api";

export default function SettingsPage() {
  const { activeWorkspace, refreshAuth, setActiveWorkspaceId } = useAuth();
  const queryClient = useQueryClient();

  const [newWsName, setNewWsName] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<Exclude<WorkspaceRole, "owner">>("member");
  const [keyName, setKeyName] = useState("");
  const [revealedKey, setRevealedKey] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  const wsId = activeWorkspace?.id;
  const isAdmin = activeWorkspace?.role === "owner" || activeWorkspace?.role === "admin";

  const membersQuery = useQuery({
    queryKey: ["members", wsId],
    queryFn: () => apiService.listMembers(wsId!),
    enabled: Boolean(wsId),
  });

  const usageQuery = useQuery({
    queryKey: ["usage", wsId],
    queryFn: () => apiService.getUsage(wsId!),
    enabled: Boolean(wsId),
  });

  const apiKeysQuery = useQuery({
    queryKey: ["api-keys", wsId],
    queryFn: () => apiService.listApiKeys(wsId!),
    enabled: Boolean(wsId && isAdmin),
  });

  const auditQuery = useQuery({
    queryKey: ["audit-logs", wsId],
    queryFn: () => apiService.listAuditLogs(wsId!),
    enabled: Boolean(wsId && isAdmin),
  });

  const createWsMutation = useMutation({
    mutationFn: () => apiService.createWorkspace(newWsName.trim()),
    onSuccess: async (ws) => {
      setNewWsName("");
      setFeedback(`Workspace "${ws.name}" created.`);
      await refreshAuth();
      setActiveWorkspaceId(ws.id);
    },
    onError: (err: Error) => setFeedback(err.message),
  });

  const addMemberMutation = useMutation({
    mutationFn: () => apiService.addMember(wsId!, inviteEmail.trim(), inviteRole),
    onSuccess: async () => {
      setInviteEmail("");
      setFeedback("Member added to workspace.");
      await queryClient.invalidateQueries({ queryKey: ["members", wsId] });
      await queryClient.invalidateQueries({ queryKey: ["usage", wsId] });
    },
    onError: (err: Error) => setFeedback(err.message),
  });

  const removeMemberMutation = useMutation({
    mutationFn: (memberId: string) => apiService.removeMember(wsId!, memberId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["members", wsId] });
      await queryClient.invalidateQueries({ queryKey: ["usage", wsId] });
    },
    onError: (err: Error) => setFeedback(err.message),
  });

  const createKeyMutation = useMutation({
    mutationFn: () => apiService.createApiKey(wsId!, keyName.trim()),
    onSuccess: async (res) => {
      setKeyName("");
      setRevealedKey(res.plaintext_key);
      await queryClient.invalidateQueries({ queryKey: ["api-keys", wsId] });
      await queryClient.invalidateQueries({ queryKey: ["audit-logs", wsId] });
    },
    onError: (err: Error) => setFeedback(err.message),
  });

  const revokeKeyMutation = useMutation({
    mutationFn: (keyId: string) => apiService.revokeApiKey(wsId!, keyId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["api-keys", wsId] });
      await queryClient.invalidateQueries({ queryKey: ["audit-logs", wsId] });
    },
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight text-foreground">Settings</h1>
        <p className="text-xs text-muted">
          Workspace profile, team roles, API keys, usage quotas, and security audit log
        </p>
      </div>

      {feedback ? (
        <div className="rounded-md border border-border bg-surface-elevated px-3.5 py-2.5 text-xs text-foreground">
          {feedback}
        </div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Create Another Workspace */}
        <Card>
          <CardHeader>
            <div>
              <CardTitle>Create Workspace</CardTitle>
              <CardDescription>Isolate another client or organization</CardDescription>
            </div>
          </CardHeader>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (newWsName.trim()) createWsMutation.mutate();
            }}
            className="flex gap-2"
          >
            <Input
              value={newWsName}
              onChange={(e) => setNewWsName(e.target.value)}
              placeholder="Client Workspace Name"
              minLength={2}
              required
            />
            <Button type="submit" disabled={createWsMutation.isPending}>
              <Plus className="h-4 w-4" />
              Create
            </Button>
          </form>
        </Card>

        {/* Plan & Usage */}
        <Card>
          <CardHeader>
            <div>
              <CardTitle>
                {usageQuery.data?.saas_quotas_enabled === false ||
                usageQuery.data?.plan.name === "community"
                  ? "Edition & Usage"
                  : "Plan & Usage"}
              </CardTitle>
              <CardDescription>
                {usageQuery.data?.saas_quotas_enabled === false ||
                usageQuery.data?.plan.name === "community"
                  ? "Unmetered self-hosted telemetry usage"
                  : "Server-enforced workspace quotas"}
              </CardDescription>
            </div>
            {usageQuery.data ? (
              usageQuery.data.saas_quotas_enabled === false ||
              usageQuery.data.plan.name === "community" ? (
                <Badge variant="healthy">{usageQuery.data.plan.display_name}</Badge>
              ) : (
                <Badge variant="accent">
                  {usageQuery.data.plan.display_name} (${usageQuery.data.plan.price_monthly_usd}/mo)
                </Badge>
              )
            ) : null}
          </CardHeader>

          {!activeWorkspace ? (
            <EmptyState title="No active workspace" description="Select or create a workspace." />
          ) : usageQuery.isLoading ? (
            <LoadingState label="Loading usage..." />
          ) : usageQuery.data ? (
            (() => {
              const showLimits =
                usageQuery.data.saas_quotas_enabled !== false &&
                usageQuery.data.plan.name !== "community";
              return (
                <div className="grid grid-cols-2 gap-3 text-xs">
                  <div className="rounded-md border border-border bg-background p-3">
                    <p className="text-muted">Monthly Executions</p>
                    <p className="mt-1 text-sm font-semibold text-foreground">
                      {showLimits
                        ? `${usageQuery.data.executions_count} / ${usageQuery.data.plan.max_monthly_executions}`
                        : usageQuery.data.executions_count}
                    </p>
                  </div>
                  <div className="rounded-md border border-border bg-background p-3">
                    <p className="text-muted">AI Investigations</p>
                    <p className="mt-1 text-sm font-semibold text-foreground">
                      {showLimits
                        ? `${usageQuery.data.ai_investigations_count} / ${usageQuery.data.plan.max_monthly_ai_investigations}`
                        : usageQuery.data.ai_investigations_count}
                    </p>
                  </div>
                  <div className="rounded-md border border-border bg-background p-3">
                    <p className="text-muted">Members</p>
                    <p className="mt-1 text-sm font-semibold text-foreground">
                      {showLimits
                        ? `${usageQuery.data.members_count} / ${usageQuery.data.plan.max_members}`
                        : usageQuery.data.members_count}
                    </p>
                  </div>
                  <div className="rounded-md border border-border bg-background p-3">
                    <p className="text-muted">Retention Window</p>
                    <p className="mt-1 text-sm font-semibold text-foreground">
                      {usageQuery.data.plan.retention_days} days
                    </p>
                  </div>
                </div>
              );
            })()
          ) : null}
        </Card>
      </div>

      {activeWorkspace ? (
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Members */}
          <Card>
            <CardHeader>
              <div>
                <CardTitle>Members & Roles</CardTitle>
                <CardDescription>Role-based access control for {activeWorkspace.name}</CardDescription>
              </div>
            </CardHeader>

            {isAdmin ? (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  if (inviteEmail.trim()) addMemberMutation.mutate();
                }}
                className="mb-4 flex flex-wrap gap-2"
              >
                <Input
                  type="email"
                  value={inviteEmail}
                  onChange={(e) => setInviteEmail(e.target.value)}
                  placeholder="teammate@company.com"
                  className="flex-1"
                  required
                />
                <Select
                  value={inviteRole}
                  onChange={(e) => setInviteRole(e.target.value as Exclude<WorkspaceRole, "owner">)}
                  className="w-28"
                >
                  <option value="viewer">Viewer</option>
                  <option value="member">Member</option>
                  <option value="admin">Admin</option>
                </Select>
                <Button type="submit" size="sm" disabled={addMemberMutation.isPending}>
                  <UserPlus className="h-3.5 w-3.5" />
                  Add
                </Button>
              </form>
            ) : null}

            <div className="divide-y divide-border">
              {(membersQuery.data || []).map((m) => (
                <div key={m.id} className="flex items-center justify-between py-2.5 text-sm">
                  <div>
                    <p className="font-medium text-foreground">{m.name || m.email}</p>
                    <p className="text-xs text-muted">{m.email}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant={m.role === "owner" ? "accent" : "default"}>{m.role}</Badge>
                    {isAdmin && m.role !== "owner" ? (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => removeMemberMutation.mutate(m.id)}
                        aria-label={`Remove ${m.email}`}
                      >
                        <Trash2 className="h-3.5 w-3.5 text-red-400" />
                      </Button>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          </Card>

          {/* API Keys */}
          <Card>
            <CardHeader>
              <div>
                <CardTitle>Workspace API Keys</CardTitle>
                <CardDescription>Used for ingestion clients and automation hooks</CardDescription>
              </div>
              <KeyRound className="h-4 w-4 text-slate-500" />
            </CardHeader>

            {!isAdmin ? (
              <EmptyState
                title="Admin access required"
                description="Only workspace admins and owners can manage API keys."
              />
            ) : (
              <>
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (keyName.trim()) createKeyMutation.mutate();
                  }}
                  className="mb-4 flex gap-2"
                >
                  <Input
                    value={keyName}
                    onChange={(e) => setKeyName(e.target.value)}
                    placeholder="Production ingestion key"
                    required
                  />
                  <Button type="submit" size="sm" disabled={createKeyMutation.isPending}>
                    Generate
                  </Button>
                </form>

                {revealedKey ? (
                  <div className="mb-4 rounded-md border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs">
                    <p className="font-medium text-emerald-300">
                      Copy this key now — it will not be shown again:
                    </p>
                    <code className="mt-1 block break-all font-mono text-emerald-200">
                      {revealedKey}
                    </code>
                  </div>
                ) : null}

                <div className="divide-y divide-border">
                  {(apiKeysQuery.data || []).map((k) => (
                    <div key={k.id} className="flex items-center justify-between py-2.5 text-sm">
                      <div>
                        <p className="font-medium text-foreground">{k.name}</p>
                        <p className="font-mono text-xs text-muted">{k.key_prefix}••••••••</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant={k.revoked_at ? "critical" : "healthy"}>
                          {k.revoked_at ? "Revoked" : "Active"}
                        </Badge>
                        {!k.revoked_at ? (
                          <Button
                            variant="danger"
                            size="sm"
                            onClick={() => revokeKeyMutation.mutate(k.id)}
                          >
                            Revoke
                          </Button>
                        ) : null}
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </Card>
        </div>
      ) : null}

      {/* Audit Logs */}
      {activeWorkspace && isAdmin ? (
        <Card>
          <CardHeader>
            <div>
              <CardTitle>Security Audit Log</CardTitle>
              <CardDescription>Immutable log of workspace actions</CardDescription>
            </div>
          </CardHeader>
          {(auditQuery.data?.items.length ?? 0) === 0 ? (
            <EmptyState title="No audit events" description="Actions will appear here." />
          ) : (
            <div className="divide-y divide-border text-xs">
              {auditQuery.data!.items.map((log) => (
                <div key={log.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                  <div className="flex items-center gap-2">
                    <Badge variant="default">{log.action}</Badge>
                    <span className="text-muted">
                      {log.resource_type} {log.resource_id ? `(${log.resource_id.slice(0, 8)})` : ""}
                    </span>
                  </div>
                  <span className="text-muted">{formatRelativeDate(log.created_at)}</span>
                </div>
              ))}
            </div>
          )}
        </Card>
      ) : null}
    </div>
  );
}
