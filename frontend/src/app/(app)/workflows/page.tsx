import { ModuleRoadmapView } from "@/components/layout/module-roadmap-view";

export default function WorkflowsPage() {
  return (
    <ModuleRoadmapView
      title="Workflows"
      subtitle="Synced automation workflows, health status, and execution history"
      emptyTitle="Workflow sync activates in Phase 2"
      emptyDescription="Connect an n8n instance in Integrations to discover workflows and track execution metrics."
    />
  );
}
