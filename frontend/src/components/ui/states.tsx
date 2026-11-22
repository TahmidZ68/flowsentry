import * as React from "react";
import { AlertTriangle, Inbox, Loader2 } from "lucide-react";
import { Button } from "./button";

export function LoadingState({ label = "Loading..." }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-border bg-surface py-12 text-muted">
      <Loader2 className="mb-2 h-5 w-5 animate-spin text-accent" />
      <p className="text-sm">{label}</p>
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border bg-surface/60 px-6 py-12 text-center">
      <Inbox className="mb-3 h-7 w-7 text-slate-500" />
      <h4 className="text-sm font-medium text-foreground">{title}</h4>
      <p className="mt-1 max-w-md text-xs text-muted">{description}</p>
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-red-500/30 bg-red-500/5 px-6 py-10 text-center">
      <AlertTriangle className="mb-2 h-6 w-6 text-red-400" />
      <p className="text-sm font-medium text-red-300">Unable to load data</p>
      <p className="mt-1 max-w-md text-xs text-red-300/80">{message}</p>
      {onRetry ? (
        <Button variant="secondary" size="sm" className="mt-4" onClick={onRetry}>
          Retry
        </Button>
      ) : null}
    </div>
  );
}
