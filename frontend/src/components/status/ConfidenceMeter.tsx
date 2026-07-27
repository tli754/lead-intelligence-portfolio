import type { ConfidenceLevel } from "@/schemas/company";
import { cn } from "@/lib/utils";

import { TONE_DOT_CLASS, type StatusTone } from "./tone";

const CONFIDENCE_CONFIG: Record<ConfidenceLevel, { label: string; tone: StatusTone; filled: number }> = {
  high: { label: "High confidence", tone: "good", filled: 3 },
  medium: { label: "Medium confidence", tone: "warning", filled: 2 },
  low: { label: "Low confidence", tone: "critical", filled: 1 },
};

const BARS = [0, 1, 2];

/**
 * A 3-bar meter + label. `null` renders a "not yet scored" empty state
 * rather than being omitted, so unscored companies are never ambiguous
 * with a genuinely low-confidence score.
 */
export function ConfidenceMeter({
  level,
  className,
}: {
  level: ConfidenceLevel | null;
  className?: string;
}) {
  if (level === null) {
    return (
      <span className={cn("text-muted-foreground inline-flex items-center gap-1.5 text-xs", className)}>
        <span className="flex items-end gap-0.5" aria-hidden="true">
          {BARS.map((bar) => (
            <span key={bar} className="bg-muted h-2.5 w-1 rounded-sm" />
          ))}
        </span>
        Not yet scored
      </span>
    );
  }

  const config = CONFIDENCE_CONFIG[level];
  return (
    <span
      className={cn("inline-flex items-center gap-1.5 text-xs font-medium", className)}
      role="img"
      aria-label={config.label}
    >
      <span className="flex items-end gap-0.5" aria-hidden="true">
        {BARS.map((bar) => (
          <span
            key={bar}
            className={cn(
              "h-2.5 w-1 rounded-sm",
              bar < config.filled ? TONE_DOT_CLASS[config.tone] : "bg-muted",
            )}
          />
        ))}
      </span>
      <span className="text-foreground">{config.label}</span>
    </span>
  );
}
