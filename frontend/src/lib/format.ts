/** Shared display-formatting helpers for company/job data. */

export function unknownOr(value: string | null): string {
  return value ?? "Unknown";
}

export function formatDate(iso: string | null): string {
  if (iso === null) return "—";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function formatDateTime(iso: string | null): string {
  if (iso === null) return "—";
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function formatScore(score: number | null): string {
  return score === null ? "—" : String(Math.round(score));
}
