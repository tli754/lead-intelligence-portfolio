import { cn } from "@/lib/utils";

import { TONE_DOT_CLASS, type StatusTone } from "./tone";

interface StatusPillProps {
  tone: StatusTone;
  label: string;
  /** Animates the dot for "actively running" states (e.g. crawling). */
  pulse?: boolean;
  className?: string;
}

/**
 * The reusable status/confidence primitive: a colored dot plus a text
 * label, never color alone. `ProcessingStatusBadge`, `WorkflowStatusBadge`
 * and `ConfidenceMeter` all compose this.
 */
export function StatusPill({ tone, label, pulse = false, className }: StatusPillProps) {
  return (
    <span
      className={cn(
        "border-border bg-background text-foreground inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        className,
      )}
    >
      <span
        className={cn("size-1.5 shrink-0 rounded-full", TONE_DOT_CLASS[tone], pulse && "animate-pulse")}
        aria-hidden="true"
      />
      {label}
    </span>
  );
}
