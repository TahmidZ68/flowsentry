"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AlertOctagon, FolderKanban, GitBranch, Plug, Plus, Target } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { useAuth } from "@/features/auth/auth-context";
import { apiService } from "@/services/api";

export default function OverviewPage() {
  const { activeWorkspace, activeEnvironment, refreshAuth, setActiveWorkspaceId } = useAuth();
  const [newWsName, setNewWsName] = useState("");
  const [creatingWs, setCreatingWs] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const usageQuery = useQuery({
    queryKey: ["usage", activeWorkspace?.id],
    queryFn: () => apiService.getUsage(activeWorkspace!.id),
    enabled: Boolean(activeWorkspace?.id),
  });

  const projectsQuery = useQuery({
    queryKey: ["projects", activeWorkspace?.id, activeEnvironment],
    queryFn: () => apiService.listProjects(activeWorkspace!.id, activeEnvironment),
    enabled: Boolean(activeWorkspace?.id),
  });

  const handleCreateFirstWorkspace = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newWsName.trim()) return;
    setCreatingWs(true);
    setCreateError(null);
    try {
      const ws = await apiService.createWorkspace(newWsName.trim());
      setNewWsName("");
      await refreshAuth();
      setActiveWorkspaceId(ws.id);
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Failed to create workspace");
    } finally {
      setCreatingWs(false);
    }
  };

  if (!activeWorkspace) {
    return (
      <div className="mx-auto max-w-lg py-12">
        <Card>
          <CardHeader>
            <div>
              <CardTitle>Create your first workspace</CardTitle>
              <CardDescription className="mt-1">
                Workspaces isolate projects, n8n integrations, executions, and incidents per team or client.
              </CardDescription>
            </div>
          </CardHeader>
          <form onSubmit={handleCreateFirstWorkspace} className="space-y-4">
            <div>
              <label htmlFor="ws-name" className="mb-1.5 block text-xs font-medium text-muted">
                Workspace name
              </label>
              <Input
                id="ws-name"
                value={newWsName}
                onChange={(e) => setNewWsName(e.target.value)}
                placeholder="Acme Automation Agency"
                required
                minLength={2}
              />
            </div>
            {createError ? (
              <p className="text-xs text-red-400">{createError}</p>
            ) : null}
            <Button type="submit" disabled={creatingWs}>
              <Plus className="h-4 w-4" />
              {creatingWs ? "Creating..." : "Create workspace"}
            </Button>
          </form>
        </Card>
      </div>
    );
  }

  if (usageQuery.isLoading || projectsQuery.isLoading) {
    return <LoadingState label="Loading workspace telemetry..." />;
  }

  if (usageQuery.isError) {
    return (
      <ErrorState
        message={(usageQuery.error as Error)?.message || "Failed to load workspace usage"}
        onRetry={() => void usageQuery.refetch()}
      />
    );
  }

  const usage = usageQuery.data;
  const projects = projectsQuery.data?.items || [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold tracking-tight text-foreground">Overview</h1>
          <p className="text-xs text-muted">
            Real-time reliability summary for <span className="text-foreground">{activeWorkspace.name}</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link href="/projects">
            <Button variant="secondary" size="sm">
              <FolderKanban className="h-3.5 w-3.5" />
              Manage Projects
            </Button>
          </Link>
          <Link href="/integrations">
            <Button size="sm">
              <Plug className="h-3.5 w-3.5" />
              Connect n8n
            </Button>
          </Link>
        </div>
      </div>

      {/* Real Backend KPI Cards — Zero fabricated metrics */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Card>
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted">Projects</span>
            <FolderKanban className="h-4 w-4 text-slate-500" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-semibold text-foreground">{usage?.projects_count ?? 0}</span>
            <span className="text-xs text-muted">/ {usage?.plan.max_projects ?? 0} limit</span>
          </div>
        </Card>

        <Card>
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted">Connected Integrations</span>
            <Plug className="h-4 w-4 text-slate-500" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-semibold text-foreground">{usage?.integrations_count ?? 0}</span>
            <span className="text-xs text-muted">/ {usage?.plan.max_integrations ?? 0} limit</span>
          </div>
        </Card>

        <Card>
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted">Executions ({usage?.period_month})</span>
            <GitBranch className="h-4 w-4 text-slate-500" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-semibold text-foreground">{usage?.executions_count ?? 0}</span>
            <span className="text-xs text-muted">/ {usage?.plan.max_monthly_executions.toLocaleString()}</span>
          </div>
        </Card>

        <Card>
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted">Outcome Monitors</span>
            <Target className="h-4 w-4 text-slate-500" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-semibold text-foreground">{usage?.outcome_monitors_count ?? 0}</span>
            <span className="text-xs text-muted">/ {usage?.plan.max_outcome_monitors ?? 0} limit</span>
          </div>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <div>
              <CardTitle>Projects in Workspace</CardTitle>
              <CardDescription>Environment-scoped automation containers</CardDescription>
            </div>
            <Link href="/projects" className="text-xs text-accent hover:underline">
              View all
            </Link>
          </CardHeader>

          {projects.length === 0 ? (
            <EmptyState
              title="No matching projects"
              description="Create a project or switch the environment filter in the top bar."
            />
          ) : (
            <div className="divide-y divide-border">
              {projects.map((p) => (
                <div key={p.id} className="flex items-center justify-between py-2.5 text-sm">
                  <div>
                    <p className="font-medium text-foreground">{p.name}</p>
                    <p className="text-xs text-muted">{p.description || "No description"}</p>
                  </div>
                  <Badge variant="default">{p.environment}</Badge>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card>
          <CardHeader>
            <div>
              <CardTitle>Active Incidents</CardTitle>
              <CardDescription>Grouped workflow failures & silent outcome anomalies</CardDescription>
            </div>
            <AlertOctagon className="h-4 w-4 text-slate-500" />
          </CardHeader>
          <EmptyState
            title="No incidents ingested yet"
            description="Connect an n8n integration or webhook in Phase 2 to start tracking real execution failures and grouped incidents."
          />
        </Card>
      </div>
    </div>
  );
}
