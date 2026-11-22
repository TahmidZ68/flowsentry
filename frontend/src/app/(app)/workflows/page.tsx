"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { useAuth } from "@/features/auth/auth-context";
import { formatRelativeDate } from "@/lib/utils";
import { apiService } from "@/services/api";

export default function WorkflowsPage() {
  const { activeWorkspace, activeEnvironment } = useAuth();
  const [search, setSearch] = useState("");

  const workflowsQuery = useQuery({
    queryKey: ["workflows", activeWorkspace?.id, activeEnvironment, search],
    queryFn: () => apiService.listWorkflows(activeWorkspace!.id, activeEnvironment, search || undefined),
    enabled: Boolean(activeWorkspace?.id),
  });

  if (!activeWorkspace) {
    return <EmptyState title="No workspace selected" description="Select a workspace first." />;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold tracking-tight text-foreground">Workflows</h1>
          <p className="text-xs text-muted">
            Execution health, failure rates, and latency across connected automations
          </p>
        </div>

        <div className="relative w-64">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-slate-500" />
          <Input
            aria-label="Search workflows"
            placeholder="Filter workflows..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-8"
          />
        </div>
      </div>

      <Card>
        {workflowsQuery.isLoading ? (
          <LoadingState label="Loading workflows..." />
        ) : workflowsQuery.isError ? (
          <ErrorState
            message={(workflowsQuery.error as Error).message}
            onRetry={() => void workflowsQuery.refetch()}
          />
        ) : (workflowsQuery.data?.items.length ?? 0) === 0 ? (
          <EmptyState
            title="No workflows discovered yet"
            description="Connect an n8n integration or ingest an execution event to register workflows automatically."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-border text-xs text-muted">
                  <th className="pb-2.5 font-medium">Workflow</th>
                  <th className="pb-2.5 font-medium">Health</th>
                  <th className="pb-2.5 font-medium">Executions</th>
                  <th className="pb-2.5 font-medium">Success Rate</th>
                  <th className="pb-2.5 font-medium">Failures</th>
                  <th className="pb-2.5 font-medium">Avg Duration</th>
                  <th className="pb-2.5 font-medium">Last Execution</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {workflowsQuery.data!.items.map((wf) => {
                  const successRate = (100 - wf.failure_rate).toFixed(1);
                  const healthy = wf.active_incidents_count === 0;
                  return (
                    <tr key={wf.id} className="hover:bg-surface-elevated/40">
                      <td className="py-3 pr-4">
                        <Link
                          href={`/workflows/${wf.id}`}
                          className="font-medium text-foreground hover:text-accent hover:underline"
                        >
                          {wf.name}
                        </Link>
                        <p className="font-mono text-xs text-muted">ID: {wf.external_workflow_id}</p>
                      </td>
                      <td className="py-3 pr-4">
                        <Badge variant={healthy ? "healthy" : "critical"}>
                          {healthy ? "Healthy" : `${wf.active_incidents_count} active incident(s)`}
                        </Badge>
                      </td>
                      <td className="py-3 pr-4 font-mono text-xs text-foreground">
                        {wf.execution_count}
                      </td>
                      <td className="py-3 pr-4 font-mono text-xs text-foreground">{successRate}%</td>
                      <td className="py-3 pr-4 font-mono text-xs text-red-400">{wf.failed_count}</td>
                      <td className="py-3 pr-4 font-mono text-xs text-muted">
                        {wf.avg_duration_ms !== null ? `${wf.avg_duration_ms} ms` : "—"}
                      </td>
                      <td className="py-3 text-xs text-muted">
                        {formatRelativeDate(wf.last_execution_at)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
