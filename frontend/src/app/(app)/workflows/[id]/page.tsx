"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Badge } from "@/components/ui/badge";
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

export default function WorkflowDetailPage() {
  const params = useParams<{ id: string }>();
  const workflowId = params.id;
  const { activeWorkspace } = useAuth();
  const queryClient = useQueryClient();

  const [maxDurationInput, setMaxDurationInput] = useState("");

  const wfQuery = useQuery({
    queryKey: ["workflow", activeWorkspace?.id, workflowId],
    queryFn: () => apiService.getWorkflow(activeWorkspace!.id, workflowId),
    enabled: Boolean(activeWorkspace?.id && workflowId),
  });

  const execQuery = useQuery({
    queryKey: ["workflow-executions", activeWorkspace?.id, workflowId],
    queryFn: () => apiService.listExecutions(activeWorkspace!.id, workflowId),
    enabled: Boolean(activeWorkspace?.id && workflowId),
  });

  const incQuery = useQuery({
    queryKey: ["workflow-incidents", activeWorkspace?.id, workflowId],
    queryFn: () => apiService.listIncidents(activeWorkspace!.id, { workflow_id: workflowId }),
    enabled: Boolean(activeWorkspace?.id && workflowId),
  });

  const updateSlaMutation = useMutation({
    mutationFn: () =>
      apiService.updateWorkflow(activeWorkspace!.id, workflowId, {
        max_duration_ms: maxDurationInput ? Number(maxDurationInput) : null,
      }),
    onSuccess: async () => {
      setMaxDurationInput("");
      await queryClient.invalidateQueries({ queryKey: ["workflow", activeWorkspace?.id, workflowId] });
    },
  });

  if (!activeWorkspace) return null;
  if (wfQuery.isLoading) return <LoadingState label="Loading workflow details..." />;
  if (wfQuery.isError) {
    return (
      <ErrorState message={(wfQuery.error as Error).message} onRetry={() => void wfQuery.refetch()} />
    );
  }

  const wf = wfQuery.data!;
  const executions = execQuery.data?.items || [];
  const durationData = [...executions]
    .reverse()
    .slice(-15)
    .map((e) => ({
      id: e.external_execution_id.slice(-8),
      duration_ms: e.duration_ms ?? 0,
    }));

  return (
    <div className="space-y-6">
      <div>
        <Link
          href="/workflows"
          className="mb-2 inline-flex items-center gap-1 text-xs text-muted hover:text-foreground"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to workflows
        </Link>
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-lg font-semibold tracking-tight text-foreground">{wf.name}</h1>
            <p className="font-mono text-xs text-muted">External ID: {wf.external_workflow_id}</p>
          </div>
          <Badge variant={wf.active_incidents_count === 0 ? "healthy" : "critical"}>
            {wf.active_incidents_count === 0
              ? "Healthy"
              : `${wf.active_incidents_count} active incident(s)`}
          </Badge>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-4">
        <Card>
          <p className="text-xs text-muted">Total Executions</p>
          <p className="mt-1 text-xl font-semibold text-foreground">{wf.execution_count}</p>
        </Card>
        <Card>
          <p className="text-xs text-muted">Failure Rate</p>
          <p className="mt-1 text-xl font-semibold text-foreground">{wf.failure_rate}%</p>
        </Card>
        <Card>
          <p className="text-xs text-muted">Avg Duration</p>
          <p className="mt-1 text-xl font-semibold text-foreground">
            {wf.avg_duration_ms !== null ? `${wf.avg_duration_ms} ms` : "—"}
          </p>
        </Card>
        <Card>
          <p className="text-xs text-muted">Latency SLA</p>
          <p className="mt-1 text-xl font-semibold text-foreground">
            {wf.max_duration_ms ? `${wf.max_duration_ms} ms` : "Auto baseline"}
          </p>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <div>
              <CardTitle>Execution Duration Trend</CardTitle>
              <CardDescription>Recent runs (milliseconds)</CardDescription>
            </div>
          </CardHeader>
          {durationData.length === 0 ? (
            <EmptyState title="No executions yet" description="Runs will chart here." />
          ) : (
            <div className="h-56 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={durationData}>
                  <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                  <XAxis dataKey="id" tick={{ fill: "#94a3b8", fontSize: 10 }} />
                  <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#0d1320",
                      borderColor: "#1e293b",
                      color: "#f1f5f9",
                      fontSize: "12px",
                    }}
                  />
                  <Bar dataKey="duration_ms" name="Duration (ms)" fill="#6366f1" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Card>

        <Card>
          <CardHeader>
            <div>
              <CardTitle>Performance Threshold</CardTitle>
              <CardDescription>Flag executions exceeding SLA duration</CardDescription>
            </div>
          </CardHeader>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              updateSlaMutation.mutate();
            }}
            className="space-y-3"
          >
            <Input
              type="number"
              min={100}
              placeholder={wf.max_duration_ms ? String(wf.max_duration_ms) : "e.g. 5000 ms"}
              value={maxDurationInput}
              onChange={(e) => setMaxDurationInput(e.target.value)}
            />
            <Button type="submit" size="sm" className="w-full" disabled={updateSlaMutation.isPending}>
              Save SLA threshold
            </Button>
          </form>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <div>
              <CardTitle>Execution History</CardTitle>
              <CardDescription>Latest normalized runs</CardDescription>
            </div>
          </CardHeader>
          {executions.length === 0 ? (
            <EmptyState title="No executions" description="No runs ingested for this workflow." />
          ) : (
            <div className="divide-y divide-border text-xs">
              {executions.map((ex) => (
                <div key={ex.id} className="flex items-center justify-between gap-2 py-2.5">
                  <div className="min-w-0">
                    <p className="truncate font-mono text-foreground">{ex.external_execution_id}</p>
                    <p className="truncate text-muted">
                      {ex.error_summary || `${ex.duration_ms ?? 0} ms`}
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

        <Card>
          <CardHeader>
            <div>
              <CardTitle>Related Incidents</CardTitle>
              <CardDescription>Incidents opened for this workflow</CardDescription>
            </div>
          </CardHeader>
          {(incQuery.data?.items.length ?? 0) === 0 ? (
            <EmptyState title="No incidents" description="This workflow has no recorded incidents." />
          ) : (
            <div className="divide-y divide-border text-xs">
              {incQuery.data!.items.map((inc) => (
                <Link
                  key={inc.id}
                  href={`/incidents/${inc.id}`}
                  className="flex items-center justify-between gap-2 py-2.5 hover:bg-surface-elevated/40"
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium text-foreground">{inc.title}</p>
                    <p className="text-muted">{inc.occurrence_count}x</p>
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
      </div>
    </div>
  );
}
