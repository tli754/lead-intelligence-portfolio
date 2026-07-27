/**
 * Zod contract for the pipeline-jobs API — a future FastAPI worker-queue
 * view (discovery/crawl/extraction/analysis/scoring stages). See
 * `src/schemas/company.ts` for the sibling companies contract.
 */

import { z } from "zod";

export const jobStageSchema = z.enum(["discovery", "crawl", "extraction", "analysis", "scoring"]);
export type JobStage = z.infer<typeof jobStageSchema>;

export const jobStatusSchema = z.enum(["queued", "running", "succeeded", "failed"]);
export type JobStatus = z.infer<typeof jobStatusSchema>;

export const jobSchema = z.object({
  job_id: z.string(),
  company_id: z.string(),
  company_domain: z.string(),
  stage: jobStageSchema,
  status: jobStatusSchema,
  queued_at: z.string(),
  started_at: z.string().nullable(),
  finished_at: z.string().nullable(),
  error_message: z.string().nullable(),
});
export type Job = z.infer<typeof jobSchema>;

export const jobListResponseSchema = z.object({
  items: z.array(jobSchema),
  total: z.number().int().nonnegative(),
});
export type JobListResponse = z.infer<typeof jobListResponseSchema>;

export interface JobListFilters {
  stage?: JobStage;
  status?: JobStatus;
}
