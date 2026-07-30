import type { JobStatus } from "@/schemas/job";

import { StatusPill } from "./StatusPill";
import type { StatusTone } from "./tone";

const JOB_STATUS_CONFIG: Record<JobStatus, { label: string; tone: StatusTone; pulse?: boolean }> = {
  queued: { label: "Queued", tone: "neutral" },
  running: { label: "Running", tone: "active", pulse: true },
  succeeded: { label: "Succeeded", tone: "good" },
  failed: { label: "Failed", tone: "critical" },
};

export function JobStatusBadge({ status, className }: { status: JobStatus; className?: string }) {
  const config = JOB_STATUS_CONFIG[status];
  return <StatusPill tone={config.tone} label={config.label} pulse={config.pulse} className={className} />;
}
