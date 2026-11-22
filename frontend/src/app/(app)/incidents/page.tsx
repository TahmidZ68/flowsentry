"use client";

import React, { Suspense, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/input";
import { IncidentStatusBadge, SeverityBadge } from "@/components/ui/severity-badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { useAuth } from "@/features/auth/auth-context";
import { formatRelativeDate } from "@/lib/utils";
import { apiService } from "@/services/api";

function IncidentsPageContent() {
  const { activeWorkspace } = useAuth();
  const searchParams = useSearchParams();
  const querySearch = searchParams.get("search") ?? "";
  const [searchOverride, setSearchOverride] = useState<{ query: string; value: string } | null>(null);
  const search = searchOverride && searchOverride.query === querySearch ? searchOverride.value : querySearch;
  const [severity, setSeverity] = useState("");
  const [status, setStatus] = useState("");
  const [workflowId, setWorkflowId] = useState("");

  const workflowsQuery = useQuery({
    queryKey: ["workflows-filter", activeWorkspace?.id],
    queryFn: () => apiService.listWorkflows(activeWorkspace!.id),
    enabled: Boolean(activeWorkspace?.id),
  });

  const incidentsQuery = useQuery({
    queryKey: ["incidents", activeWorkspace?.id, search, severity, status, workflowId],
    queryFn: () =>
      apiService.listIncidents(activeWorkspace!.id, {
        search: search || undefined,
        severity: severity || undefined,
        status: status || undefined,
        workflow_id: workflowId || undefined,
      }),
    enabled: Boolean(activeWorkspace?.id),
  });

  if (!activeWorkspace) {
    return <EmptyState title="No workspace selected" description="Select a workspace first." />;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight text-foreground">Incidents</h1>
        <p className="text-xs text-muted">
          Grouped workflow failures, recurring issues, and silent outcome violations
        </p>
      </div>

      {/* Filters */}
      <Card className="p-4">
        <div className="grid gap-3 md:grid-cols-4">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-slate-500" />
            <Input
              aria-label="Search incidents"
              placeholder="Search title or error..."
              value={search}
              onChange={(e) => setSearchOverride({ query: querySearch, value: e.target.value })}
              className="pl-8"
            />
          </div>

          <Select
            aria-label="Filter by severity"
            value={severity}
            onChange={(e) => setSeverity(e.target.value)}
          >
            <option value="">All severities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </Select>

          <Select
            aria-label="Filter by status"
            value={status}
            onChange={(e) => setStatus(e.target.value)}
          >
            <option value="">All statuses</option>
            <option value="open">Open</option>
            <option value="acknowledged">Acknowledged</option>
            <option value="investigating">Investigating</option>
            <option value="resolved">Resolved</option>
            <option value="reopened">Reopened</option>
          </Select>

          <Select
            aria-label="Filter by workflow"
            value={workflowId}
            onChange={(e) => setWorkflowId(e.target.value)}
          >
            <option value="">All workflows</option>
            {(workflowsQuery.data?.items || []).map((wf) => (
              <option key={wf.id} value={wf.id}>
                {wf.name}
              </option>
            ))}
          </Select>
        </div>
      </Card>

      <Card>
        {incidentsQuery.isLoading ? (
          <LoadingState label="Loading incidents..." />
        ) : incidentsQuery.isError ? (
          <ErrorState
            message={(incidentsQuery.error as Error).message}
            onRetry={() => void incidentsQuery.refetch()}
          />
        ) : (incidentsQuery.data?.items.length ?? 0) === 0 ? (
          <EmptyState
            title="No incidents match current filters"
            description="Adjust filters or ingest workflow executions to track incidents."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-border text-xs text-muted">
                  <th className="pb-2.5 font-medium">Incident</th>
                  <th className="pb-2.5 font-medium">Workflow</th>
                  <th className="pb-2.5 font-medium">Severity</th>
                  <th className="pb-2.5 font-medium">Status</th>
                  <th className="pb-2.5 font-medium">Count</th>
                  <th className="pb-2.5 font-medium">First Seen</th>
                  <th className="pb-2.5 font-medium">Last Seen</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {incidentsQuery.data!.items.map((inc) => (
                  <tr key={inc.id} className="hover:bg-surface-elevated/40">
                    <td className="py-3 pr-4">
                      <Link
                        href={`/incidents/${inc.id}`}
                        className="font-medium text-foreground hover:text-accent hover:underline"
                      >
                        {inc.title}
                      </Link>
                      {inc.description ? (
                        <p className="max-w-md truncate text-xs text-muted">{inc.description}</p>
                      ) : null}
                    </td>
                    <td className="py-3 pr-4 text-xs text-muted">{inc.workflow_name || "—"}</td>
                    <td className="py-3 pr-4">
                      <SeverityBadge severity={inc.severity} />
                    </td>
                    <td className="py-3 pr-4">
                      <IncidentStatusBadge status={inc.status} />
                    </td>
                    <td className="py-3 pr-4 font-mono text-xs text-foreground">
                      {inc.occurrence_count}x
                    </td>
                    <td className="py-3 pr-4 text-xs text-muted">
                      {formatRelativeDate(inc.first_seen_at)}
                    </td>
                    <td className="py-3 text-xs text-muted">{formatRelativeDate(inc.last_seen_at)}</td>
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

export default function IncidentsPage() {
  return (
    <Suspense fallback={<LoadingState label="Loading incidents..." />}>
      <IncidentsPageContent />
    </Suspense>
  );
}
