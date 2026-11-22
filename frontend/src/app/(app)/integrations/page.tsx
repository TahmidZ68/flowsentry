"use client";

import React, { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Plug, RefreshCw, ShieldAlert, TestTube2, Unplug } from "lucide-react";
import { z } from "zod";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/input";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { useAuth } from "@/features/auth/auth-context";
import { formatRelativeDate } from "@/lib/utils";
import { apiService } from "@/services/api";

const integrationSchema = z.object({
  project_id: z.string().min(1, "Select a project"),
  provider: z.enum(["n8n", "custom_webhook"]),
  connection_name: z.string().min(2, "Enter a connection name"),
  base_url: z.string().optional(),
  api_key: z.string().optional(),
  polling_interval_seconds: z.coerce.number<number>().min(30).max(3600),
});

type IntegrationFormValues = z.infer<typeof integrationSchema>;

export default function IntegrationsPage() {
  const { activeWorkspace } = useAuth();
  const queryClient = useQueryClient();
  const wsId = activeWorkspace?.id;

  const [createdSecret, setCreatedSecret] = useState<{ path: string; secret: string } | null>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);

  const projectsQuery = useQuery({
    queryKey: ["projects-all", wsId],
    queryFn: () => apiService.listProjects(wsId!),
    enabled: Boolean(wsId),
  });

  const integrationsQuery = useQuery({
    queryKey: ["integrations", wsId],
    queryFn: () => apiService.listIntegrations(wsId!),
    enabled: Boolean(wsId),
  });

  const {
    register,
    handleSubmit,
    watch,
    reset,
    formState: { errors },
  } = useForm<IntegrationFormValues>({
    resolver: zodResolver(integrationSchema),
    defaultValues: {
      provider: "n8n",
      polling_interval_seconds: 120,
    },
  });

  const provider = watch("provider");

  const createMutation = useMutation({
    mutationFn: (values: IntegrationFormValues) =>
      apiService.createIntegration(wsId!, {
        project_id: values.project_id,
        provider: values.provider,
        connection_name: values.connection_name,
        base_url: values.provider === "n8n" ? values.base_url : undefined,
        api_key: values.provider === "n8n" ? values.api_key : undefined,
        polling_enabled: values.provider === "n8n",
        polling_interval_seconds: values.polling_interval_seconds,
      }),
    onSuccess: async (res) => {
      setCreatedSecret({ path: res.webhook_url_path, secret: res.webhook_secret });
      setActionMsg("Integration saved. Copy your webhook secret below.");
      reset({ provider: "n8n", polling_interval_seconds: 120, connection_name: "", base_url: "", api_key: "" });
      await queryClient.invalidateQueries({ queryKey: ["integrations", wsId] });
      await queryClient.invalidateQueries({ queryKey: ["usage", wsId] });
    },
    onError: (err: Error) => setActionMsg(err.message),
  });

  const validateMutation = useMutation({
    mutationFn: (id: string) => apiService.validateIntegration(wsId!, id),
    onSuccess: async (res) => {
      setActionMsg(res.message);
      await queryClient.invalidateQueries({ queryKey: ["integrations", wsId] });
    },
    onError: (err: Error) => setActionMsg(err.message),
  });

  const syncMutation = useMutation({
    mutationFn: (id: string) => apiService.syncIntegration(wsId!, id),
    onSuccess: async (res) => {
      setActionMsg(
        `Synced ${res.workflows_synced} workflows, ingested ${res.executions_ingested} new executions (${res.incidents_created} new incidents).`
      );
      await queryClient.invalidateQueries({ queryKey: ["integrations", wsId] });
      await queryClient.invalidateQueries({ queryKey: ["workflows", wsId] });
      await queryClient.invalidateQueries({ queryKey: ["incidents", wsId] });
      await queryClient.invalidateQueries({ queryKey: ["overview", wsId] });
    },
    onError: (err: Error) => setActionMsg(err.message),
  });

  const testWebhookMutation = useMutation({
    mutationFn: (id: string) => apiService.sendTestWebhook(wsId!, id),
    onSuccess: async (res) => {
      setActionMsg(`Test HTTP 429 webhook processed (execution ${res.execution_id.slice(0, 8)}).`);
      await queryClient.invalidateQueries({ queryKey: ["incidents", wsId] });
      await queryClient.invalidateQueries({ queryKey: ["workflows", wsId] });
      await queryClient.invalidateQueries({ queryKey: ["overview", wsId] });
    },
    onError: (err: Error) => setActionMsg(err.message),
  });

  const disconnectMutation = useMutation({
    mutationFn: (id: string) => apiService.disconnectIntegration(wsId!, id),
    onSuccess: async () => {
      setActionMsg("Integration disconnected and stored credentials scrubbed.");
      await queryClient.invalidateQueries({ queryKey: ["integrations", wsId] });
    },
  });

  if (!activeWorkspace) {
    return <EmptyState title="No workspace selected" description="Select a workspace first." />;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight text-foreground">Integrations</h1>
        <p className="text-xs text-muted">
          Connect n8n instances (REST API v1 + Error Trigger webhooks) with encrypted credential storage
        </p>
      </div>

      {actionMsg ? (
        <div className="rounded-md border border-border bg-surface-elevated px-3.5 py-2.5 text-xs text-foreground">
          {actionMsg}
        </div>
      ) : null}

      {createdSecret ? (
        <Card className="border-emerald-500/30 bg-emerald-500/5">
          <p className="text-xs font-semibold text-emerald-300">
            Webhook Ingestion Secret (copy now — shown once)
          </p>
          <p className="mt-1 font-mono text-xs text-foreground">POST {createdSecret.path}</p>
          <p className="mt-1 font-mono text-xs text-emerald-200">
            Header: X-FlowSentry-Webhook-Secret: {createdSecret.secret}
          </p>
        </Card>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader>
              <div>
                <CardTitle>Connected Integrations</CardTitle>
                <CardDescription>Credentials are encrypted at rest and never returned</CardDescription>
              </div>
            </CardHeader>

            {integrationsQuery.isLoading ? (
              <LoadingState label="Loading integrations..." />
            ) : integrationsQuery.isError ? (
              <ErrorState
                message={(integrationsQuery.error as Error).message}
                onRetry={() => void integrationsQuery.refetch()}
              />
            ) : (integrationsQuery.data?.length ?? 0) === 0 ? (
              <EmptyState
                title="No integrations configured"
                description="Add an n8n instance or Error Trigger webhook on the right."
              />
            ) : (
              <div className="divide-y divide-border">
                {integrationsQuery.data!.map((item) => (
                  <div key={item.id} className="space-y-2.5 py-3.5">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-foreground">{item.connection_name}</span>
                          <Badge variant="default">{item.provider}</Badge>
                          <Badge
                            variant={
                              item.status === "connected"
                                ? "healthy"
                                : item.status === "error" || item.status === "disconnected"
                                ? "critical"
                                : "warning"
                            }
                          >
                            {item.status}
                          </Badge>
                        </div>
                        <p className="mt-0.5 text-xs text-muted">
                          {item.base_url || "Webhook-only ingestion"} · Last sync:{" "}
                          {formatRelativeDate(item.last_synced_at)}
                        </p>
                        {item.last_error ? (
                          <p className="mt-1 text-xs text-red-400">{item.last_error}</p>
                        ) : null}
                      </div>

                      {item.status !== "disconnected" ? (
                        <div className="flex flex-wrap items-center gap-1.5">
                          {item.provider === "n8n" ? (
                            <>
                              <Button
                                variant="secondary"
                                size="sm"
                                onClick={() => validateMutation.mutate(item.id)}
                                disabled={validateMutation.isPending}
                              >
                                <CheckCircle2 className="h-3.5 w-3.5" />
                                Validate
                              </Button>
                              <Button
                                variant="secondary"
                                size="sm"
                                onClick={() => syncMutation.mutate(item.id)}
                                disabled={syncMutation.isPending}
                              >
                                <RefreshCw className="h-3.5 w-3.5" />
                                Sync
                              </Button>
                            </>
                          ) : null}
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => testWebhookMutation.mutate(item.id)}
                            disabled={testWebhookMutation.isPending}
                          >
                            <TestTube2 className="h-3.5 w-3.5" />
                            Test Webhook
                          </Button>
                          <Button
                            variant="danger"
                            size="sm"
                            onClick={() => disconnectMutation.mutate(item.id)}
                          >
                            <Unplug className="h-3.5 w-3.5" />
                            Disconnect
                          </Button>
                        </div>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card>
            <CardHeader>
              <div>
                <CardTitle>n8n Error Trigger Setup Guide</CardTitle>
                <CardDescription>
                  Recommended setup without exposing private n8n instances to the public internet
                </CardDescription>
              </div>
              <ShieldAlert className="h-4 w-4 text-amber-400" />
            </CardHeader>
            <ol className="list-inside list-decimal space-y-1.5 text-xs text-muted">
              <li>Create an Error Workflow in n8n starting with the <code className="text-foreground">Error Trigger</code> node.</li>
              <li>Add an <code className="text-foreground">HTTP Request</code> node posting JSON to <code className="text-foreground">/api/v1/ingest/webhooks/n8n/&lt;integration_id&gt;</code>.</li>
              <li>Set header <code className="text-foreground">X-FlowSentry-Webhook-Secret</code> using the secret generated when creating the integration.</li>
              <li>Assign this Error Workflow in your production n8n workflows&apos; Settings. For self-hosted n8n behind a firewall, outbound Error Trigger webhooks work without opening inbound ports.</li>
            </ol>
          </Card>
        </div>

        {/* Connect Form */}
        <Card>
          <CardHeader>
            <div>
              <CardTitle>Add Integration</CardTitle>
              <CardDescription>Supports n8n REST API v1 &amp; webhooks</CardDescription>
            </div>
            <Plug className="h-4 w-4 text-slate-500" />
          </CardHeader>

          <form
            onSubmit={handleSubmit((v) => createMutation.mutate(v))}
            className="space-y-3.5"
            noValidate
          >
            <div>
              <label htmlFor="int-project" className="mb-1 block text-xs font-medium text-muted">
                Project
              </label>
              <Select id="int-project" {...register("project_id")}>
                <option value="">Select project...</option>
                {(projectsQuery.data?.items || []).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.environment})
                  </option>
                ))}
              </Select>
              {errors.project_id ? (
                <p className="mt-1 text-xs text-red-400">{errors.project_id.message}</p>
              ) : null}
            </div>

            <div>
              <label htmlFor="int-provider" className="mb-1 block text-xs font-medium text-muted">
                Provider
              </label>
              <Select id="int-provider" {...register("provider")}>
                <option value="n8n">n8n (API + Error Webhook)</option>
                <option value="custom_webhook">Webhook-Only (n8n Error Trigger / Custom)</option>
              </Select>
            </div>

            <div>
              <label htmlFor="int-name" className="mb-1 block text-xs font-medium text-muted">
                Connection name
              </label>
              <Input id="int-name" placeholder="Production n8n EU" {...register("connection_name")} />
              {errors.connection_name ? (
                <p className="mt-1 text-xs text-red-400">{errors.connection_name.message}</p>
              ) : null}
            </div>

            {provider === "n8n" ? (
              <>
                <div>
                  <label htmlFor="int-url" className="mb-1 block text-xs font-medium text-muted">
                    n8n Instance URL
                  </label>
                  <Input
                    id="int-url"
                    placeholder="https://n8n.yourdomain.com"
                    {...register("base_url")}
                  />
                </div>
                <div>
                  <label htmlFor="int-key" className="mb-1 block text-xs font-medium text-muted">
                    n8n API Key (X-N8N-API-KEY)
                  </label>
                  <Input
                    id="int-key"
                    type="password"
                    placeholder="n8n_api_..."
                    {...register("api_key")}
                  />
                </div>
              </>
            ) : null}

            <Button type="submit" className="w-full" disabled={createMutation.isPending}>
              {createMutation.isPending ? "Saving..." : "Connect integration"}
            </Button>
          </form>
        </Card>
      </div>
    </div>
  );
}
