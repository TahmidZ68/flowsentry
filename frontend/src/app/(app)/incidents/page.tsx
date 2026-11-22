import { ModuleRoadmapView } from "@/components/layout/module-roadmap-view";

export default function IncidentsPage() {
  return (
    <ModuleRoadmapView
      title="Incidents"
      subtitle="Deduplicated workflow failures and silent outcome anomalies"
      emptyTitle="Incident management activates in Phase 2"
      emptyDescription="Once execution ingestion and deterministic failure detection are connected, grouped incidents will appear here."
    />
  );
}
