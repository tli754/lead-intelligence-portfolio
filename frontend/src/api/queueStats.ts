/**
 * Real API client for `GET /api/queue-stats`
 * (`backend/app/domains/queue_stats/router.py`), following
 * `frontend/src/api/companies.ts`'s established client-file shape (its
 * own local `extractErrorMessage`/`FastApiErrorBody` helper, duplicated
 * rather than shared, per this repository's existing per-client-file
 * precedent).
 */

import { queueStatsSchema, type QueueStats } from "@/schemas/queueStats";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

/** Raised when the API rejects a queue-stats request (non-2xx). */
export class QueueStatsRequestError extends Error {}

interface FastApiValidationDetail {
  msg?: string;
}

interface FastApiErrorBody {
  detail?: string | FastApiValidationDetail[];
}

function extractErrorMessage(body: FastApiErrorBody, fallback: string): string {
  const { detail } = body;
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail) && detail.length > 0 && detail[0].msg) {
    return detail[0].msg;
  }
  return fallback;
}

/**
 * `GET /api/queue-stats?queue=` — defaults to `"crawling"`, the only
 * queue this repository has adopted RQ for today (ADR 0004's
 * module-by-module rollout).
 *
 * A Zod parse failure is allowed to propagate as-is (not wrapped in
 * `QueueStatsRequestError`) — matching `companies.ts`'s own
 * `companyListResponseSchema.parse(...)` call, which is likewise
 * unwrapped. Either error type makes a TanStack Query hook's `isError`
 * true, which is all `QueueStatsPanel` needs.
 */
export async function fetchQueueStats(queueName = "crawling"): Promise<QueueStats> {
  const response = await fetch(
    `${API_BASE_URL}/api/queue-stats?queue=${encodeURIComponent(queueName)}`,
  );
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as FastApiErrorBody;
    throw new QueueStatsRequestError(
      extractErrorMessage(body, `GET /api/queue-stats?queue=${queueName} failed with ${response.status}`),
    );
  }
  return queueStatsSchema.parse(await response.json());
}
