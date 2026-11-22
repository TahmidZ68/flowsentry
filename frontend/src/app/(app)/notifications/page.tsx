import { ModuleRoadmapView } from "@/components/layout/module-roadmap-view";

export default function NotificationsPage() {
  return (
    <ModuleRoadmapView
      title="Notifications"
      subtitle="Email and Slack alert preferences, suppression, and delivery history"
      emptyTitle="Notification delivery activates in Phase 4"
      emptyDescription="Configure per-severity Slack webhooks and email alerts with duplicate suppression."
    />
  );
}
