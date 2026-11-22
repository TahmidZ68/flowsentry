"use client";

import React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { useAuth } from "@/features/auth/auth-context";
import { formatRelativeDate } from "@/lib/utils";
import { apiService } from "@/services/api";

export default function InvestigationsPage() {
  const { activeWorkspace } = useAuth();

  const investigationsQuery = useQuery({
    queryKey: ["investigations", activeWorkspace?.id],
    queryFn: () => apiService.listInvestigations(activeWorkspace!.id),
    enabled: Boolean(activeWorkspace?.id),
  });

  if (!activeWorkspace) {
    return <EmptyState title="No workspace selected" description="Select a workspace first." />;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight text-foreground">Investigations</h1>
        <p className="text-xs text-muted">
          AI and deterministic root-cause analyses backed by sanitized execution evidence
        </p>
      </div>

      {investigationsQuery.isLoading ? (
        <LoadingState label="Loading investigations..." />
      ) : investigationsQuery.isError ? (
        <ErrorState
          message={(investigationsQuery.error as Error).message}
          onRetry={() => void investigationsQuery.refetch()}
        />
      ) : (investigationsQuery.data?.items.length ?? 0) === 0 ? (
        <EmptyState
          title="No investigations run yet"
          description="Open any incident and click 'Run Investigation' to generate a root-cause hypothesis and action plan."
        />
      ) : (
        <div className="space-y-4">
          {investigationsQuery.data!.items.map((inv) => (
            <Card key={inv.id}>
              <CardHeader>
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Sparkles className="h-4 w-4 text-accent" />
                    <CardTitle>{inv.summary || "Investigation"}</CardTitle>
                  </div>
                  <CardDescription>
                    <Link
                      href={`/incidents/${inv.incident_id}`}
                      className="text-accent hover:underline"
                    >
                      View Incident ({inv.incident_id.slice(0, 8)})
                    </Link>{" "}
                    · {formatRelativeDate(inv.created_at)}
                  </CardDescription>
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge variant="accent">
                    {inv.provider} / {inv.model}
                  </Badge>
                  <Badge variant={inv.analysis_status === "completed" ? "healthy" : "warning"}>
                    {inv.analysis_status}
                  </Badge>
                  {inv.confidence !== null ? (
                    <Badge variant="info">{Math.round(inv.confidence * 100)}% confidence</Badge>
                  ) : null}
                </div>
              </CardHeader>

              {inv.root_cause_hypothesis ? (
                <p className="mb-3 text-xs text-foreground">{inv.root_cause_hypothesis}</p>
              ) : null}

              <div className="grid gap-4 md:grid-cols-2 text-xs">
                <div>
                  <p className="font-semibold text-muted">Observed Evidence</p>
                  <ul className="mt-1 list-inside list-disc space-y-1 text-foreground">
                    {inv.evidence.map((e, i) => (
                      <li key={i}>{e}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <p className="font-semibold text-muted">Recommended Actions</p>
                  <ul className="mt-1 list-inside list-disc space-y-1 text-emerald-300">
                    {inv.recommended_actions.map((a, i) => (
                      <li key={i}>{a}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
