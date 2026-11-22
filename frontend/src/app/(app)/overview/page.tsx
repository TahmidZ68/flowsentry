"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertOctagon,
  CheckCircle2,
  GitBranch,
  Plug,
  Plus,
  XCircle,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  ExecutionStatusBadge,
  IncidentStatusBadge,
  SeverityBadge,
} from "@/components/ui/severity-badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { useAuth } from "@/features/auth/auth-context";
import { formatRelativeDate } from "@/lib/utils";
import { apiService } from "@/services/api";

export default function OverviewPage() {
  const { activeWorkspace, refreshAuth, setActiveWorkspaceId } = useAuth();
  const [newWsName, setNewWsName] = useState("");
  const [creatingWs, setCreatingWs] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const overviewQuery = useQuery({
    queryKey: ["overview", activeWorkspace?.id],
    queryFn: () => apiService.getOverview(activeWorkspace!.id),
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
            {createError ? <p className="text-xs text-red-400">{createError}</p> : null}
            <Button type="submit" disabled={creatingWs}>
              <Plus className="h-4 w-4" />
              {creatingWs ? "Creating..." : "Create workspace"}
            </Button>
          </form>
        </Card>
      </div>
    );
  }

  if (overviewQuery.isLoading) {
    return <LoadingState label="Loading workspace telemetry..." />;
  }

  if (overviewQuery.isError) {
    return (
      <ErrorState
        message={(overviewQuery.error as Error)?.message || "Failed to load overview metrics"}
        onRetry={() => void overviewQuery.refetch()}
      />
    );
  }

  const data = overviewQuery.data!;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold tracking-tight text-foreground">Overview</h1>
          <p className="text-xs text-muted">
            Live reliability telemetry for <span className="text-foreground">{activeWorkspace.name}</span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link href="/incidents">
            <Button variant="secondary" size="sm">
              <AlertOctagon className="h-3.5 w-3.5" />
              View Incidents
            </Button>
          </Link>
          <Link href="/integrations">
            <Button size="sm">
              <Plug className="h-3.5 w-3.5" />
              Integrations
            </Button>
          </Link>
        </div>
      </div>

      {/* Real Backend KPIs */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Card>
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted">Monitored Workflows</span>
            <GitBranch className="h-4 w-4 text-slate-500" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-semibold text-foreground">{data.total_workflows}</span>
            <span className="text-xs text-emerald-400">{data.healthy_workflows} healthy</span>
          </div>
        </Card>

        <Card>
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted">Successful Executions</span>
            <CheckCircle2 className="h-4 w-4 text-emerald-500" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-semibold text-foreground">
              {data.successful_executions}
            </span>
            <span className="text-xs text-muted">of {data.total_executions} total</span>
          </div>
        </Card>

        <Card>
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted">Failed Executions</span>
            <XCircle className="h-4 w-4 text-red-400" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-semibold text-foreground">{data.failed_executions}</span>
            <span className="text-xs text-muted">
              {data.total_executions > 0
                ? `${((data.failed_executions / data.total_executions) * 100).toFixed(1)}% failure rate`
                : "0% failure rate"}
            </span>
          </div>
        </Card>

        <Card>
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted">Active Incidents</span>
            <AlertOctagon className="h-4 w-4 text-amber-400" />
          </div>
          <div className="mt-2 flex items-baseline gap-2">
            <span className="text-2xl font-semibold text-foreground">{data.active_incidents}</span>
            <span className="text-xs text-red-400">{data.critical_incidents} critical</span>
          </div>
        </Card>
      </div>

      {/* First-run Onboarding Checklist (shown only when workspace has 0 workflows/executions) */}
      {data.total_workflows === 0 && data.total_executions === 0 ? (
        <Card className="border-indigo-500/30 bg-indigo-500/5">
          <CardHeader>
            <div>
              <CardTitle>Start monitoring in 3 steps</CardTitle>
              <CardDescription>
                Your workflows run. Make sure they actually produce expected business outcomes.
              </CardDescription>
            </div>
          </CardHeader>
          <div className="grid gap-3 md:grid-cols-3 text-xs">
            <Link
              href="/integrations"
              className="rounded-md border border-border bg-background/80 p-3 transition hover:border-accent/60"
            >
              <p className="font-semibold text-foreground">1. Connect n8n or Webhook</p>
              <p className="mt-1 text-muted">
                Sync executions via n8n REST API or point an Error Trigger webhook to FlowSentry.
              </p>
            </Link>
            <Link
              href="/monitors"
              className="rounded-md border border-border bg-background/80 p-3 transition hover:border-accent/60"
            >
              <p className="font-semibold text-foreground">2. Define Outcome Monitors</p>
              <p className="mt-1 text-muted">
                Catch silent failures using expected intervals, required fields, or HTTP checks.
              </p>
            </Link>
            <Link
              href="/notifications"
              className="rounded-md border border-border bg-background/80 p-3 transition hover:border-accent/60"
            >
              <p className="font-semibold text-foreground">3. Configure Alert Channels</p>
              <p className="mt-1 text-muted">
                Route incident alerts and resolution updates to Slack or team email via SMTP.
              </p>
            </Link>
          </div>
        </Card>
      ) : null}

      {/* 14-day Execution & Failure Trend */}
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Execution &amp; Failure Trends (14 Days)</CardTitle>
            <CardDescription>Aggregated from normalized execution records</CardDescription>
          </div>
          <Activity className="h-4 w-4 text-slate-500" />
        </CardHeader>
        {data.total_executions === 0 ? (
          <EmptyState
            title="No execution history recorded yet"
            description="Connect an n8n instance or trigger a safe test webhook in Integrations to see real execution trends."
          />
        ) : (
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data.trends} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
                <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                <XAxis dataKey="date" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} allowDecimals={false} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "#0d1320",
                    borderColor: "#1e293b",
                    color: "#f1f5f9",
                    fontSize: "12px",
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="success"
                  name="Success"
                  stroke="#10b981"
                  fill="#10b981"
                  fillOpacity={0.15}
                />
                <Area
                  type="monotone"
                  dataKey="failed"
                  name="Failed"
                  stroke="#ef4444"
                  fill="#ef4444"
                  fillOpacity={0.2}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Recent Incidents */}
        <Card>
          <CardHeader>
            <div>
              <CardTitle>Recent Incidents</CardTitle>
              <CardDescription>Grouped failures requiring attention</CardDescription>
            </div>
            <Link href="/incidents" className="text-xs text-accent hover:underline">
              All incidents
            </Link>
          </CardHeader>
          {data.recent_incidents.length === 0 ? (
            <EmptyState
              title="No incidents detected"
              description="Failed executions and silent outcome violations will group here."
            />
          ) : (
            <div className="divide-y divide-border">
              {data.recent_incidents.map((inc) => (
                <Link
                  key={inc.id}
                  href={`/incidents/${inc.id}`}
                  className="flex items-center justify-between gap-3 py-2.5 text-sm hover:bg-surface-elevated/40"
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium text-foreground">{inc.title}</p>
                    <p className="text-xs text-muted">
                      {inc.workflow_name} · {inc.occurrence_count}x · {formatRelativeDate(inc.last_seen_at)}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <SeverityBadge severity={inc.severity} />
                    <IncidentStatusBadge status={inc.status} />
                  </div>
                </Link>
              ))}
            </div>
          )}
        </Card>

        {/* Recent Executions */}
        <Card>
          <CardHeader>
            <div>
              <CardTitle>Recent Executions</CardTitle>
              <CardDescription>Latest normalized workflow runs</CardDescription>
            </div>
            <Link href="/workflows" className="text-xs text-accent hover:underline">
              Workflows
            </Link>
          </CardHeader>
          {data.recent_executions.length === 0 ? (
            <EmptyState
              title="No executions ingested"
              description="Sync an n8n instance or configure an Error Trigger webhook."
            />
          ) : (
            <div className="divide-y divide-border">
              {data.recent_executions.map((ex) => (
                <div key={ex.id} className="flex items-center justify-between gap-3 py-2.5 text-xs">
                  <div className="min-w-0">
                    <p className="truncate font-mono text-foreground">{ex.external_execution_id}</p>
                    <p className="truncate text-muted">
                      {ex.error_summary || (ex.duration_ms ? `${ex.duration_ms} ms` : "Completed")}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <ExecutionStatusBadge status={ex.status} />
                    <span className="text-muted">{formatRelativeDate(ex.started_at)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
