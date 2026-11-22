import { ModuleRoadmapView } from "@/components/layout/module-roadmap-view";

export default function MonitorsPage() {
  return (
    <ModuleRoadmapView
      title="Outcome Monitors"
      subtitle="Verify business outcomes and detect silent workflow failures"
      emptyTitle="Outcome monitoring activates in Phase 3"
      emptyDescription="Define expected intervals, execution counts, required output fields, and HTTP/record verification checks."
    />
  );
}
