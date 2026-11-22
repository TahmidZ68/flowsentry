import { ModuleRoadmapView } from "@/components/layout/module-roadmap-view";

export default function IntegrationsPage() {
  return (
    <ModuleRoadmapView
      title="Integrations"
      subtitle="Connect n8n instances and webhook ingestion endpoints"
      emptyTitle="n8n integration activates in Phase 2"
      emptyDescription="Configure encrypted n8n API credentials and Error Trigger webhooks with SSRF validation."
    />
  );
}
