import type { WorkflowStatus } from "@/schemas/company";

import { StatusPill } from "./StatusPill";
import type { StatusTone } from "./tone";

const WORKFLOW_STATUS_CONFIG: Record<WorkflowStatus, { label: string; tone: StatusTone }> = {
  unreviewed: { label: "Unreviewed", tone: "neutral" },
  reviewed: { label: "Reviewed", tone: "active" },
  shortlisted: { label: "Shortlisted", tone: "good" },
  not_suitable: { label: "Not suitable", tone: "critical" },
  contacted: { label: "Contacted", tone: "active" },
  customer: { label: "Customer", tone: "milestone" },
  archived: { label: "Archived", tone: "neutral" },
};

export function WorkflowStatusBadge({
  status,
  className,
}: {
  status: WorkflowStatus;
  className?: string;
}) {
  const config = WORKFLOW_STATUS_CONFIG[status];
  return <StatusPill tone={config.tone} label={config.label} className={className} />;
}
