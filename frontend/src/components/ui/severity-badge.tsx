import { Badge } from "@/components/ui/badge";
import type { IncidentSeverity, IncidentStatus } from "@/types/api";

export function SeverityBadge({ severity }: { severity: IncidentSeverity | string }) {
  const variant =
    severity === "critical"
      ? "critical"
      : severity === "high"
      ? "warning"
      : severity === "medium"
      ? "info"
      : "default";
  return <Badge variant={variant}>{severity}</Badge>;
}

export function IncidentStatusBadge({ status }: { status: IncidentStatus | string }) {
  const variant =
    status === "resolved"
      ? "healthy"
      : status === "open" || status === "reopened"
      ? "critical"
      : status === "investigating"
      ? "accent"
      : "warning";
  return <Badge variant={variant}>{status}</Badge>;
}

export function ExecutionStatusBadge({ status }: { status: string }) {
  const variant =
    status === "success"
      ? "healthy"
      : status === "failed"
      ? "critical"
      : status === "running" || status === "waiting"
      ? "info"
      : "default";
  return <Badge variant={variant}>{status}</Badge>;
}
