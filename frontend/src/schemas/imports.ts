/**
 * Zod contracts for the StoreLeads import preview/commit wire shapes
 * (`backend/app/modules/imports/api/schemas.py`). Enum values are pinned
 * here so a future backend enum addition fails loudly as a Zod parse
 * error instead of silently rendering an undefined badge — see the
 * "storeleads-import-ui" feature contract's "Known Shape Gaps" #3.
 */

import { z } from "zod";

export const importValidationStatusSchema = z.enum(["valid", "invalid"]);
export type ImportValidationStatus = z.infer<typeof importValidationStatusSchema>;

export const importDuplicateStatusSchema = z.enum([
  "new",
  "existing",
  "duplicate_in_file",
  "unknown",
]);
export type ImportDuplicateStatus = z.infer<typeof importDuplicateStatusSchema>;

export const importRowOutcomeSchema = z.enum([
  "created",
  "skipped_existing",
  "skipped_invalid",
  "failed",
]);
export type ImportRowOutcome = z.infer<typeof importRowOutcomeSchema>;

export const importRowErrorSchema = z.object({
  field: z.string().nullable(),
  message: z.string(),
});
export type ImportRowError = z.infer<typeof importRowErrorSchema>;

export const importRowSchema = z.object({
  rowNumber: z.number().int(),
  website: z.string().nullable(),
  normalizedDomain: z.string().nullable(),
  platform: z.string().nullable(),
  country: z.string().nullable(),
  city: z.string().nullable(),
  validationStatus: importValidationStatusSchema,
  errors: z.array(importRowErrorSchema),
  duplicateStatus: importDuplicateStatusSchema,
  outcome: importRowOutcomeSchema.nullable(),
});
export type ImportRow = z.infer<typeof importRowSchema>;

export const importBatchSummarySchema = z.object({
  rowsFound: z.number().int().nonnegative(),
  validRows: z.number().int().nonnegative(),
  invalidRows: z.number().int().nonnegative(),
  existingCompanies: z.number().int().nonnegative(),
  duplicateRowsInFile: z.number().int().nonnegative(),
  importableRows: z.number().int().nonnegative(),
});
export type ImportBatchSummary = z.infer<typeof importBatchSummarySchema>;

export const importPreviewResponseSchema = z.object({
  data: z.object({
    summary: importBatchSummarySchema,
    rows: z.array(importRowSchema),
  }),
});
export type ImportPreviewResponse = z.infer<typeof importPreviewResponseSchema>;

export const importResultResponseSchema = z.object({
  data: z.object({
    created: z.number().int().nonnegative(),
    skippedExisting: z.number().int().nonnegative(),
    skippedInvalid: z.number().int().nonnegative(),
    failed: z.number().int().nonnegative(),
    rows: z.array(importRowSchema),
  }),
});
export type ImportResultResponse = z.infer<typeof importResultResponseSchema>;
