import type { ProcessingStatus } from "@/schemas/company";

import { StatusPill } from "./StatusPill";
import type { StatusTone } from "./tone";

const PROCESSING_STATUS_CONFIG: Record<
  ProcessingStatus,
  { label: string; tone: StatusTone; pulse?: boolean }
> = {
  imported: { label: "Imported", tone: "neutral" },
  discovering: { label: "Discovering", tone: "active", pulse: true },
  discovered: { label: "Discovered", tone: "neutral" },
  crawling: { label: "Crawling", tone: "active", pulse: true },
  crawled: { label: "Crawled", tone: "neutral" },
  extracting: { label: "Extracting", tone: "active", pulse: true },
  extracted: { label: "Extracted", tone: "neutral" },
  analysing: { label: "Analysing", tone: "active", pulse: true },
  analysed: { label: "Analysed", tone: "neutral" },
  scoring: { label: "Scoring", tone: "active", pulse: true },
  ready: { label: "Ready", tone: "good" },
  partial: { label: "Partial", tone: "warning" },
  failed: { label: "Failed", tone: "critical" },
  stale: { label: "Stale", tone: "warning" },
};

export function ProcessingStatusBadge({
  status,
  className,
}: {
  status: ProcessingStatus;
  className?: string;
}) {
  const config = PROCESSING_STATUS_CONFIG[status];
  return <StatusPill tone={config.tone} label={config.label} pulse={config.pulse} className={className} />;
}
