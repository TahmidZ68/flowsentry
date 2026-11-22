"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle, MessageSquarePlus, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  ExecutionStatusBadge,
  IncidentStatusBadge,
  SeverityBadge,
} from "@/components/ui/severity-badge";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { useAuth } from "@/features/auth/auth-context";
import { formatRelativeDate } from "@/lib/utils";
import { apiService } from "@/services/api";

export default function IncidentDetailPage() {
  const params = useParams<{ id: string }>();
  const incidentId = params.id;
  const { activeWorkspace } = useAuth();
  const queryClient = useQueryClient();

  const [noteContent, setNoteContent] = useState("");
  const [resolutionNotes, setResolutionNotes] = useState("");

  const detailQuery = useQuery({
    queryKey: ["incident", activeWorkspace?.id, incidentId],
    queryFn: () => apiService.getIncident(activeWorkspace!.id, incidentId),
    enabled: Boolean(activeWorkspace?.id && incidentId),
  });

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ["incident", activeWorkspace?.id, incidentId] });
    await queryClient.invalidateQueries({ queryKey: ["incidents", activeWorkspace?.id] });
    await queryClient.invalidateQueries({ queryKey: ["overview", activeWorkspace?.id] });
  };

  const ackMutation = useMutation({
    mutationFn: () => apiService.acknowledgeIncident(activeWorkspace!.id, incidentId),
    onSuccess: invalidate,
  });

  const investigateMutation = useMutation({
    mutationFn: () => apiService.investigateIncident(activeWorkspace!.id, incidentId),
    onSuccess: invalidate,
  });

  const resolveMutation = useMutation({
    mutationFn: () => apiService.resolveIncident(activeWorkspace!.id, incidentId, resolutionNotes),
    onSuccess: async () => {
      setResolutionNotes("");
      await invalidate();
    },
  });

  const reopenMutation = useMutation({
    mutationFn: () => apiService.reopenIncident(activeWorkspace!.id, incidentId),
    onSuccess: invalidate,
  });

  const noteMutation = useMutation({
    mutationFn: () => apiService.addIncidentNote(activeWorkspace!.id, incidentId, noteContent),
    onSuccess: async () => {
      setNoteContent("");
      await invalidate();
    },
  });

  if (!activeWorkspace) return null;
  if (detailQuery.isLoading) return <LoadingState label="Loading incident details..." />;
  if (detailQuery.isError) {
    return (
      <ErrorState
        message={(detailQuery.error as Error).message}
        onRetry={() => void detailQuery.refetch()}
      />
    );
  }

  const inc = detailQuery.data!;
  const canMutate = activeWorkspace.role !== "viewer";

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link
            href="/incidents"
            className="mb-2 inline-flex items-center gap-1 text-xs text-muted hover:text-foreground"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Back to incidents
          </Link>
          <h1 className="text-lg font-semibold tracking-tight text-foreground">{inc.title}</h1>
          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-muted">
            <SeverityBadge severity={inc.severity} />
            <IncidentStatusBadge status={inc.status} />
            <span>Workflow: {inc.workflow_name}</span>
            <span>·</span>
            <span>Occurrences: {inc.occurrence_count}x</span>
            <span>·</span>
            <span>First seen: {formatRelativeDate(inc.first_seen_at)}</span>
          </div>
        </div>

        {canMutate ? (
          <div className="flex flex-wrap items-center gap-2">
            {inc.status === "open" || inc.status === "reopened" ? (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => ackMutation.mutate()}
                disabled={ackMutation.isPending}
              >
                Acknowledge
              </Button>
            ) : null}
            {inc.status !== "investigating" && inc.status !== "resolved" ? (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => investigateMutation.mutate()}
                disabled={investigateMutation.isPending}
              >
                Mark Investigating
              </Button>
            ) : null}
            {inc.status === "resolved" ? (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => reopenMutation.mutate()}
                disabled={reopenMutation.isPending}
              >
                <RotateCcw className="h-3.5 w-3.5" />
                Reopen
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {/* Error Evidence */}
          <Card>
            <CardHeader>
              <div>
                <CardTitle>Observed Error Evidence</CardTitle>
                <CardDescription>Sanitized failure context from latest occurrences</CardDescription>
              </div>
            </CardHeader>
            <p className="rounded-md border border-border bg-background p-3 font-mono text-xs text-red-300">
              {inc.description || "No error summary recorded."}
            </p>
            <div className="mt-3 text-xs text-muted">
              Fingerprint: <span className="font-mono text-foreground">{inc.fingerprint}</span>
            </div>
            {inc.resolution_reason ? (
              <div className="mt-3 rounded-md border border-emerald-500/30 bg-emerald-500/10 p-3 text-xs text-emerald-300">
                Resolution: {inc.resolution_reason}
                {inc.resolution_notes ? ` — ${inc.resolution_notes}` : ""}
              </div>
            ) : null}
          </Card>

          {/* Related Executions */}
          <Card>
            <CardHeader>
              <div>
                <CardTitle>Related Executions</CardTitle>
                <CardDescription>Grouped occurrences linked to this incident</CardDescription>
              </div>
            </CardHeader>
            <div className="divide-y divide-border">
              {inc.recent_executions.map((ex) => (
                <div key={ex.id} className="py-2.5 text-xs">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-foreground">{ex.external_execution_id}</span>
                    <div className="flex items-center gap-2">
                      <ExecutionStatusBadge status={ex.status} />
                      <span className="text-muted">{formatRelativeDate(ex.started_at)}</span>
                    </div>
                  </div>
                  <p className="mt-1 text-muted">
                    {ex.failed_node ? `Node: ${ex.failed_node} · ` : ""}
                    {ex.error_type || ""} {ex.error_summary ? `— ${ex.error_summary}` : ""}
                  </p>
                </div>
              ))}
            </div>
          </Card>
        </div>

        {/* Timeline, Notes & Resolution */}
        <div className="space-y-6">
          {canMutate && inc.status !== "resolved" ? (
            <Card>
              <CardHeader>
                <div>
                  <CardTitle>Resolve Incident</CardTitle>
                  <CardDescription>Document verification or mitigation applied</CardDescription>
                </div>
              </CardHeader>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  resolveMutation.mutate();
                }}
                className="space-y-3"
              >
                <Input
                  placeholder="Optional resolution notes..."
                  value={resolutionNotes}
                  onChange={(e) => setResolutionNotes(e.target.value)}
                />
                <Button type="submit" className="w-full" disabled={resolveMutation.isPending}>
                  <CheckCircle className="h-4 w-4" />
                  Mark Resolved
                </Button>
              </form>
            </Card>
          ) : null}

          <Card>
            <CardHeader>
              <div>
                <CardTitle>Timeline &amp; Notes</CardTitle>
                <CardDescription>Audit events and investigation comments</CardDescription>
              </div>
            </CardHeader>

            <div className="mb-4 max-h-72 space-y-2.5 overflow-y-auto pr-1 text-xs">
              {inc.notes.map((n) => (
                <div key={n.id} className="rounded-md border border-border bg-background p-2.5">
                  <div className="flex items-center justify-between text-[11px] text-muted">
                    <span className="uppercase tracking-wider">{n.note_type}</span>
                    <span>{formatRelativeDate(n.created_at)}</span>
                  </div>
                  <p className="mt-1 text-foreground">{n.content}</p>
                </div>
              ))}
            </div>

            {canMutate ? (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  if (noteContent.trim()) noteMutation.mutate();
                }}
                className="flex gap-2"
              >
                <Input
                  placeholder="Add investigation note..."
                  value={noteContent}
                  onChange={(e) => setNoteContent(e.target.value)}
                />
                <Button type="submit" size="sm" disabled={noteMutation.isPending}>
                  <MessageSquarePlus className="h-3.5 w-3.5" />
                </Button>
              </form>
            ) : null}
          </Card>
        </div>
      </div>
    </div>
  );
}
