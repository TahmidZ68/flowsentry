"use client";

import React, { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FolderPlus } from "lucide-react";
import { z } from "zod";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/input";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { useAuth } from "@/features/auth/auth-context";
import { formatRelativeDate } from "@/lib/utils";
import { apiService } from "@/services/api";

const projectSchema = z.object({
  name: z.string().min(2, "Project name must be at least 2 characters").max(120),
  description: z.string().max(1000).optional(),
  environment: z.enum(["production", "staging", "development"]),
});

type ProjectFormValues = z.infer<typeof projectSchema>;

export default function ProjectsPage() {
  const { activeWorkspace, activeEnvironment } = useAuth();
  const queryClient = useQueryClient();
  const [formError, setFormError] = useState<string | null>(null);

  const projectsQuery = useQuery({
    queryKey: ["projects", activeWorkspace?.id, activeEnvironment],
    queryFn: () => apiService.listProjects(activeWorkspace!.id, activeEnvironment),
    enabled: Boolean(activeWorkspace?.id),
  });

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<ProjectFormValues>({
    resolver: zodResolver(projectSchema),
    defaultValues: { environment: "production" },
  });

  const createMutation = useMutation({
    mutationFn: (values: ProjectFormValues) =>
      apiService.createProject(activeWorkspace!.id, values),
    onSuccess: async () => {
      setFormError(null);
      reset({ name: "", description: "", environment: "production" });
      await queryClient.invalidateQueries({ queryKey: ["projects", activeWorkspace?.id] });
      await queryClient.invalidateQueries({ queryKey: ["usage", activeWorkspace?.id] });
    },
    onError: (err: Error) => {
      setFormError(err.message);
    },
  });

  if (!activeWorkspace) {
    return (
      <EmptyState
        title="No workspace selected"
        description="Create a workspace from the Overview or Settings page first."
      />
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight text-foreground">Projects</h1>
        <p className="text-xs text-muted">
          Organize workflows and integrations by application or deployment environment
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <div>
              <CardTitle>Workspace Projects</CardTitle>
              <CardDescription>
                Filtered by: {activeEnvironment === "all" ? "All environments" : activeEnvironment}
              </CardDescription>
            </div>
          </CardHeader>

          {projectsQuery.isLoading ? (
            <LoadingState label="Loading projects..." />
          ) : projectsQuery.isError ? (
            <ErrorState
              message={(projectsQuery.error as Error).message}
              onRetry={() => void projectsQuery.refetch()}
            />
          ) : (projectsQuery.data?.items.length ?? 0) === 0 ? (
            <EmptyState
              title="No projects found"
              description="Create a project on the right to segment workflows and environments."
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-border text-xs text-muted">
                    <th className="pb-2.5 font-medium">Name</th>
                    <th className="pb-2.5 font-medium">Environment</th>
                    <th className="pb-2.5 font-medium">Created</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {projectsQuery.data!.items.map((proj) => (
                    <tr key={proj.id}>
                      <td className="py-3 pr-4">
                        <p className="font-medium text-foreground">{proj.name}</p>
                        <p className="text-xs text-muted">{proj.description || "—"}</p>
                      </td>
                      <td className="py-3 pr-4">
                        <Badge
                          variant={
                            proj.environment === "production"
                              ? "accent"
                              : proj.environment === "staging"
                              ? "warning"
                              : "default"
                          }
                        >
                          {proj.environment}
                        </Badge>
                      </td>
                      <td className="py-3 text-xs text-muted">{formatRelativeDate(proj.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card>
          <CardHeader>
            <div>
              <CardTitle>New Project</CardTitle>
              <CardDescription>Requires admin or owner role</CardDescription>
            </div>
            <FolderPlus className="h-4 w-4 text-slate-500" />
          </CardHeader>

          <form
            onSubmit={handleSubmit((v) => createMutation.mutate(v))}
            className="space-y-3.5"
            noValidate
          >
            <div>
              <label htmlFor="proj-name" className="mb-1 block text-xs font-medium text-muted">
                Project name
              </label>
              <Input id="proj-name" placeholder="CRM Sync Pipelines" {...register("name")} />
              {errors.name ? <p className="mt-1 text-xs text-red-400">{errors.name.message}</p> : null}
            </div>

            <div>
              <label htmlFor="proj-env" className="mb-1 block text-xs font-medium text-muted">
                Environment
              </label>
              <Select id="proj-env" {...register("environment")}>
                <option value="production">Production</option>
                <option value="staging">Staging</option>
                <option value="development">Development</option>
              </Select>
            </div>

            <div>
              <label htmlFor="proj-desc" className="mb-1 block text-xs font-medium text-muted">
                Description (optional)
              </label>
              <Input id="proj-desc" placeholder="Lead capture & HubSpot sync" {...register("description")} />
            </div>

            {formError ? (
              <div className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
                {formError}
              </div>
            ) : null}

            <Button type="submit" className="w-full" disabled={createMutation.isPending}>
              {createMutation.isPending ? "Creating..." : "Create project"}
            </Button>
          </form>
        </Card>
      </div>
    </div>
  );
}
