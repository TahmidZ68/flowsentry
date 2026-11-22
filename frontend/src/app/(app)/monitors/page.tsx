"use client";

import React, { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play, Power, Target, Trash2 } from "lucide-react";
import { z } from "zod";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/input";
import { SeverityBadge } from "@/components/ui/severity-badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { useAuth } from "@/features/auth/auth-context";
import { formatRelativeDate } from "@/lib/utils";
import { apiService } from "@/services/api";
import type { MonitorType } from "@/types/api";

const monitorSchema = z.object({
  workflow_id: z.string().min(1, "Select a workflow"),
  name: z.string().min(2, "Enter a monitor name").max(150),
  description: z.string().max(1000).optional(),
  monitor_type: z.enum([
    "expected_interval",
    "expected_count",
    "required_output_fields",
    "http_endpoint",
    "webhook_confirmation",
    "external_record_check",
  ]),
  severity: z.enum(["critical", "high", "medium", "low"]),
  schedule_seconds: z.coerce.number().min(60).max(86400).default(300),
  param_value: z.string().min(1, "Provide check configuration parameter"),
});

type MonitorFormValues = z.infer<typeof monitorSchema>;

export default function OutcomeMonitorsPage() {
  const { activeWorkspace } = useAuth();
  const queryClient = useQueryClient();
  const wsId = activeWorkspace?.id;
  const [feedback, setFeedback] = useState<string | null>(null);

  const workflowsQuery = useQuery({
    queryKey: ["workflows-for-monitors", wsId],
    queryFn: () => apiService.listWorkflows(wsId!),
    enabled: Boolean(wsId),
  });

  const monitorsQuery = useQuery({
    queryKey: ["outcome-monitors", wsId],
    queryFn: () => apiService.listOutcomeMonitors(wsId!),
    enabled: Boolean(wsId),
  });

  const {
    register,
    handleSubmit,
    watch,
    reset,
    formState: { errors },
  } = useForm<MonitorFormValues>({
    resolver: zodResolver(monitorSchema),
    defaultValues: {
      monitor_type: "required_output_fields",
      severity: "high",
      schedule_seconds: 300,
    },
  });

  const selectedType = watch("monitor_type");

  const buildPayload = (v: MonitorFormValues) => {
    let configuration: Record<string, unknown> = {};
    let expected_result: Record<string, unknown> = {};

    if (v.monitor_type === "expected_interval") {
      configuration = { max_interval_seconds: Number(v.param_value) || 3600 };
      expected_result = { max_interval_seconds: Number(v.param_value) || 3600 };
    } else if (v.monitor_type === "expected_count") {
      const minCount = Number(v.param_value) || 1;
      configuration = { window_seconds: 3600, min_count: minCount };
      expected_result = { min_count: minCount };
    } else if (v.monitor_type === "required_output_fields") {
      const fields = v.param_value
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      configuration = { required_fields: fields };
      expected_result = { required_fields: fields };
    } else if (v.monitor_type === "http_endpoint") {
      configuration = { url: v.param_value.trim(), method: "GET" };
      expected_result = { status_code: 200 };
    } else if (v.monitor_type === "webhook_confirmation") {
      configuration = { grace_period_seconds: Number(v.param_value) || 300 };
      expected_result = { confirmed: true };
    } else if (v.monitor_type === "external_record_check") {
      configuration = { url: v.param_value.trim() };
      expected_result = { status_code: 200, min_records: 1 };
    }

    return {
      workflow_id: v.workflow_id,
      name: v.name,
      description: v.description || undefined,
      monitor_type: v.monitor_type as MonitorType,
      configuration,
      expected_result,
      schedule_seconds: v.schedule_seconds,
      severity: v.severity,
    };
  };

  const createMutation = useMutation({
    mutationFn: (v: MonitorFormValues) => apiService.createOutcomeMonitor(wsId!, buildPayload(v)),
    onSuccess: async () => {
      setFeedback("Outcome monitor created.");
      reset({ monitor_type: "required_output_fields", severity: "high", schedule_seconds: 300 });
      await queryClient.invalidateQueries({ queryKey: ["outcome-monitors", wsId] });
      await queryClient.invalidateQueries({ queryKey: ["usage", wsId] });
    },
    onError: (err: Error) => setFeedback(err.message),
  });

  const checkMutation = useMutation({
    mutationFn: (id: string) => apiService.checkOutcomeMonitor(wsId!, id),
    onSuccess: async (res) => {
      setFeedback(
        res.run.passed
          ? `Monitor "${res.monitor.name}" passed.`
          : `Monitor "${res.monitor.name}" FAILED — silent failure incident updated.`
      );
      await queryClient.invalidateQueries({ queryKey: ["outcome-monitors", wsId] });
      await queryClient.invalidateQueries({ queryKey: ["incidents", wsId] });
    },
    onError: (err: Error) => setFeedback(err.message),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      apiService.toggleOutcomeMonitor(wsId!, id, enabled),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["outcome-monitors", wsId] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => apiService.deleteOutcomeMonitor(wsId!, id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["outcome-monitors", wsId] });
    },
  });

  if (!activeWorkspace) {
    return <EmptyState title="No workspace selected" description="Select a workspace first." />;
  }

  const paramPlaceholder =
    selectedType === "required_output_fields"
      ? "metadata.crm_contact_id, metadata.invoice_id"
      : selectedType === "expected_interval"
      ? "3600 (max seconds since last run)"
      : selectedType === "expected_count"
      ? "5 (min runs per hour)"
      : selectedType === "webhook_confirmation"
      ? "300 (grace period seconds)"
      : "https://api.example.com/verify";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight text-foreground">Outcome Monitors</h1>
        <p className="text-xs text-muted">
          Detect silent failures where workflows finish successfully but intended business outcomes do not occur
        </p>
      </div>

      {feedback ? (
        <div className="rounded-md border border-border bg-surface-elevated px-3.5 py-2.5 text-xs text-foreground">
          {feedback}
        </div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <div>
              <CardTitle>Configured Monitors</CardTitle>
              <CardDescription>Evaluated on schedule or manually via Check Now</CardDescription>
            </div>
          </CardHeader>

          {monitorsQuery.isLoading ? (
            <LoadingState label="Loading outcome monitors..." />
          ) : monitorsQuery.isError ? (
            <ErrorState
              message={(monitorsQuery.error as Error).message}
              onRetry={() => void monitorsQuery.refetch()}
            />
          ) : (monitorsQuery.data?.length ?? 0) === 0 ? (
            <EmptyState
              title="No outcome monitors configured"
              description="Define business outcome assertions on the right to catch silent workflow failures."
            />
          ) : (
            <div className="divide-y divide-border">
              {monitorsQuery.data!.map((m) => (
                <div key={m.id} className="space-y-2 py-3.5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium text-foreground">{m.name}</span>
                        <Badge variant="default">{m.monitor_type}</Badge>
                        <SeverityBadge severity={m.severity} />
                        <Badge
                          variant={
                            m.status === "healthy"
                              ? "healthy"
                              : m.status === "failing"
                              ? "critical"
                              : "default"
                          }
                        >
                          {m.status}
                        </Badge>
                      </div>
                      <p className="mt-1 text-xs text-muted">
                        Workflow: {m.workflow_name || m.workflow_id} · Last check:{" "}
                        {formatRelativeDate(m.last_checked_at)}
                      </p>
                      {m.failure_evidence?.reason ? (
                        <p className="mt-1 text-xs text-red-400">
                          Failure evidence: {String(m.failure_evidence.reason)}
                        </p>
                      ) : null}
                    </div>

                    <div className="flex items-center gap-1.5">
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => checkMutation.mutate(m.id)}
                        disabled={checkMutation.isPending}
                      >
                        <Play className="h-3.5 w-3.5" />
                        Check
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => toggleMutation.mutate({ id: m.id, enabled: !m.enabled })}
                        title={m.enabled ? "Disable" : "Enable"}
                      >
                        <Power className={`h-3.5 w-3.5 ${m.enabled ? "text-emerald-400" : "text-slate-500"}`} />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => deleteMutation.mutate(m.id)}
                        aria-label={`Delete ${m.name}`}
                      >
                        <Trash2 className="h-3.5 w-3.5 text-red-400" />
                      </Button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card>
          <CardHeader>
            <div>
              <CardTitle>Create Outcome Monitor</CardTitle>
              <CardDescription>Define what business success means</CardDescription>
            </div>
            <Target className="h-4 w-4 text-slate-500" />
          </CardHeader>

          <form
            onSubmit={handleSubmit((v) => createMutation.mutate(v))}
            className="space-y-3.5"
            noValidate
          >
            <div>
              <label htmlFor="mon-wf" className="mb-1 block text-xs font-medium text-muted">
                Target workflow
              </label>
              <Select id="mon-wf" {...register("workflow_id")}>
                <option value="">Select workflow...</option>
                {(workflowsQuery.data?.items || []).map((wf) => (
                  <option key={wf.id} value={wf.id}>
                    {wf.name}
                  </option>
                ))}
              </Select>
              {errors.workflow_id ? (
                <p className="mt-1 text-xs text-red-400">{errors.workflow_id.message}</p>
              ) : null}
            </div>

            <div>
              <label htmlFor="mon-name" className="mb-1 block text-xs font-medium text-muted">
                Monitor name
              </label>
              <Input id="mon-name" placeholder="HubSpot Contact Created" {...register("name")} />
              {errors.name ? (
                <p className="mt-1 text-xs text-red-400">{errors.name.message}</p>
              ) : null}
            </div>

            <div>
              <label htmlFor="mon-type" className="mb-1 block text-xs font-medium text-muted">
                Monitor type
              </label>
              <Select id="mon-type" {...register("monitor_type")}>
                <option value="required_output_fields">Required Output Fields</option>
                <option value="expected_interval">Expected Execution Interval</option>
                <option value="expected_count">Expected Execution Count</option>
                <option value="http_endpoint">HTTP Endpoint Verification</option>
                <option value="webhook_confirmation">Webhook Confirmation</option>
                <option value="external_record_check">External Record Existence</option>
              </Select>
            </div>

            <div>
              <label htmlFor="mon-param" className="mb-1 block text-xs font-medium text-muted">
                Check target / threshold
              </label>
              <Input id="mon-param" placeholder={paramPlaceholder} {...register("param_value")} />
              {errors.param_value ? (
                <p className="mt-1 text-xs text-red-400">{errors.param_value.message}</p>
              ) : null}
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <label htmlFor="mon-sev" className="mb-1 block text-xs font-medium text-muted">
                  Severity
                </label>
                <Select id="mon-sev" {...register("severity")}>
                  <option value="critical">Critical</option>
                  <option value="high">High</option>
                  <option value="medium">Medium</option>
                  <option value="low">Low</option>
                </Select>
              </div>
              <div>
                <label htmlFor="mon-sched" className="mb-1 block text-xs font-medium text-muted">
                  Schedule (sec)
                </label>
                <Input id="mon-sched" type="number" min={60} {...register("schedule_seconds")} />
              </div>
            </div>

            <Button type="submit" className="w-full" disabled={createMutation.isPending}>
              {createMutation.isPending ? "Creating..." : "Create monitor"}
            </Button>
          </form>
        </Card>
      </div>
    </div>
  );
}
