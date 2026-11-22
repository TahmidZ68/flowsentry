import { ModuleRoadmapView } from "@/components/layout/module-roadmap-view";

export default function InvestigationsPage() {
  return (
    <ModuleRoadmapView
      title="Investigations"
      subtitle="Root-cause hypotheses, supporting evidence, and recovery guidance"
      emptyTitle="Root-cause investigations activate in Phase 3"
      emptyDescription="Sanitized execution evidence will be analyzed via configured AI providers or the deterministic fallback engine."
    />
  );
}
