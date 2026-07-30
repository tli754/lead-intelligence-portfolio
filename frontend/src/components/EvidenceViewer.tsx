import { AlertTriangle } from "lucide-react";

import { StatusPill, type StatusTone } from "@/components/status";
import { formatDateTime } from "@/lib/format";
import type { ConfidenceLevel, EvidenceItem } from "@/schemas/company";

const CONFIDENCE_TONE: Record<ConfidenceLevel, StatusTone> = {
  high: "good",
  medium: "warning",
  low: "critical",
};

interface EvidenceGroup {
  field: string;
  label: string;
  items: EvidenceItem[];
  hasConflict: boolean;
}

function groupEvidence(evidence: EvidenceItem[]): EvidenceGroup[] {
  const byField = new Map<string, EvidenceItem[]>();
  for (const item of evidence) {
    const list = byField.get(item.field) ?? [];
    list.push(item);
    byField.set(item.field, list);
  }
  return Array.from(byField.values()).map((items) => ({
    field: items[0].field,
    label: items[0].label,
    items,
    hasConflict: items.some((item) => item.conflicts_with.length > 0),
  }));
}

/**
 * Groups evidence by field, showing every observed value per field (not
 * just the "winning" one) so conflicting crawls/analyses are visible
 * rather than silently overwritten.
 */
export function EvidenceViewer({ evidence }: { evidence: EvidenceItem[] }) {
  if (evidence.length === 0) {
    return (
      <p className="text-muted-foreground text-sm" data-testid="evidence-empty-state">
        No evidence collected yet.
      </p>
    );
  }

  const groups = groupEvidence(evidence);

  return (
    <div className="flex flex-col gap-4" aria-label="Evidence viewer">
      {groups.map((group) => (
        <div key={group.field} className="border-border rounded-lg border p-3">
          <div className="mb-2 flex items-center gap-2">
            <h3 className="text-sm font-semibold">{group.label}</h3>
            {group.hasConflict && (
              <span className="text-status-critical inline-flex items-center gap-1 text-xs font-medium">
                <AlertTriangle className="size-3.5" aria-hidden="true" />
                Conflicting evidence
              </span>
            )}
          </div>
          <ul className="flex flex-col gap-2">
            {group.items.map((item) => (
              <li key={item.evidence_id} className="flex flex-col gap-0.5 text-sm">
                <div className="flex items-center gap-2">
                  <span className="font-medium">{item.value}</span>
                  <StatusPill tone={CONFIDENCE_TONE[item.confidence]} label={item.confidence} />
                </div>
                <span className="text-muted-foreground text-xs">
                  {item.source} · {formatDateTime(item.observed_at)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
