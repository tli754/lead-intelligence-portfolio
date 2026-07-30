/**
 * Zod contracts for the companies-ranking/detail API.
 *
 * These describe the shape a future FastAPI implementation should return
 * (mirroring `backend/app/modules/companies/domain/models.py`'s
 * `identity`/`processing`/`workflow` nesting and enum values, extended
 * with `score`/`confidence`/`evidence` fields the scoring feature will
 * eventually populate). The mock API layer in `src/api/mock/` validates
 * its fixture data against these same schemas, so swapping the mock
 * client for a real `fetch()` later requires no contract changes.
 */

import { z } from "zod";

export const processingStatusSchema = z.enum([
  "imported",
  "discovering",
  "discovered",
  "crawling",
  "crawled",
  "extracting",
  "extracted",
  "analysing",
  "analysed",
  "scoring",
  "ready",
  "partial",
  "failed",
  "stale",
]);
export type ProcessingStatus = z.infer<typeof processingStatusSchema>;

export const workflowStatusSchema = z.enum([
  "unreviewed",
  "reviewed",
  "shortlisted",
  "not_suitable",
  "contacted",
  "customer",
  "archived",
]);
export type WorkflowStatus = z.infer<typeof workflowStatusSchema>;

export const confidenceLevelSchema = z.enum(["high", "medium", "low"]);
export type ConfidenceLevel = z.infer<typeof confidenceLevelSchema>;

export const companyIdentitySchema = z.object({
  company_name: z.string().nullable(),
  platform: z.string().nullable(),
  country: z.string().nullable(),
  city: z.string().nullable(),
});
export type CompanyIdentity = z.infer<typeof companyIdentitySchema>;

export const companyProcessingSchema = z.object({
  status: processingStatusSchema,
  latest_discovery_run: z.string().nullable(),
  latest_crawl_run: z.string().nullable(),
  latest_extraction_run: z.string().nullable(),
  latest_analysis_run: z.string().nullable(),
  latest_scoring_run: z.string().nullable(),
  failure_reason: z.string().nullable(),
});
export type CompanyProcessing = z.infer<typeof companyProcessingSchema>;

export const companyWorkflowSchema = z.object({
  manual_status: workflowStatusSchema,
  shortlisted: z.boolean(),
  notes_count: z.number().int().nonnegative(),
});
export type CompanyWorkflow = z.infer<typeof companyWorkflowSchema>;

export const scoreFactorSchema = z.object({
  label: z.string(),
  weight: z.number(),
  value: z.number(),
});
export type ScoreFactor = z.infer<typeof scoreFactorSchema>;

export const evidenceItemSchema = z.object({
  evidence_id: z.string(),
  field: z.string(),
  label: z.string(),
  value: z.string(),
  confidence: confidenceLevelSchema,
  source: z.string(),
  source_url: z.string().nullable(),
  observed_at: z.string(),
  /** IDs of other evidence items for the same `field` with a contradicting value. */
  conflicts_with: z.array(z.string()),
});
export type EvidenceItem = z.infer<typeof evidenceItemSchema>;

export const companyListItemSchema = z.object({
  company_id: z.string(),
  domain: z.string(),
  identity: companyIdentitySchema,
  processing: companyProcessingSchema,
  workflow: companyWorkflowSchema,
  score: z.number().min(0).max(100).nullable(),
  confidence: confidenceLevelSchema.nullable(),
  updated_at: z.string(),
});
export type CompanyListItem = z.infer<typeof companyListItemSchema>;

export const companyDetailSchema = companyListItemSchema.extend({
  url: z.string().nullable(),
  emails: z.array(z.string()),
  phones: z.array(z.string()),
  created_at: z.string(),
  score_factors: z.array(scoreFactorSchema),
  evidence: z.array(evidenceItemSchema),
});
export type CompanyDetail = z.infer<typeof companyDetailSchema>;

export const companyListResponseSchema = z.object({
  items: z.array(companyListItemSchema),
  total: z.number().int().nonnegative(),
});
export type CompanyListResponse = z.infer<typeof companyListResponseSchema>;

export interface CompanyListFilters {
  processing_status?: ProcessingStatus;
  workflow_status?: WorkflowStatus;
  platform?: string;
  q?: string;
  sort?: "score" | "updated_at" | "domain";
  order?: "asc" | "desc";
}
