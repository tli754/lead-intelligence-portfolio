/**
 * Zod contract for `GET /api/queue-stats`
 * (`backend/app/domains/queue_stats/schemas.py`'s `QueueStatsResponse`).
 *
 * Snake_case fields — this backend response comes from a flat-convention
 * domain (see `backend/app/domains/queue_stats/schemas.py`'s own
 * docstring), matching `src/schemas/job.ts`'s existing snake_case
 * precedent, not the hexagonal modules' camelCase-DTO convention.
 */

import { z } from "zod";

export const queueCountsSchema = z.object({
  queued: z.number().int().nonnegative(),
  started: z.number().int().nonnegative(),
  finished: z.number().int().nonnegative(),
  failed: z.number().int().nonnegative(),
  deferred: z.number().int().nonnegative(),
  scheduled: z.number().int().nonnegative(),
});
export type QueueCounts = z.infer<typeof queueCountsSchema>;

export const queueStatsSchema = z.object({
  queue: z.string(),
  counts: queueCountsSchema,
  failed_job_ids: z.array(z.string()),
  workers_alive: z.number().int().nonnegative(),
});
export type QueueStats = z.infer<typeof queueStatsSchema>;
