import { EmptyState } from "@/components/ui/states";

export function ModuleRoadmapView({
  title,
  subtitle,
  emptyTitle,
  emptyDescription,
}: {
  title: string;
  subtitle: string;
  emptyTitle: string;
  emptyDescription: string;
}) {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold tracking-tight text-foreground">{title}</h1>
        <p className="text-xs text-muted">{subtitle}</p>
      </div>
      <EmptyState title={emptyTitle} description={emptyDescription} />
    </div>
  );
}
