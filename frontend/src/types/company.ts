/**
 * TypeScript mirror of the backend Pydantic models in
 * backend/app/domains/companies/models.py. Keep these in sync by hand —
 * there is no schema-generation step in v1.
 */

export type CompanySource = "paste_domain_list" | "paste_storeleads_html";

export interface Company {
  domain: string;
  source: CompanySource;
  url: string | null;
  estimated_sales_yearly_usd: number | null;
  source_created_at: string | null;
  emails: string[];
  phones: string[];
  imported_at: string;
}

export interface SkippedInvalidEntry {
  raw_value: string;
  reason: string;
}

export type DetectedFormat = "domain_list" | "storeleads_html";

export interface ImportResponse {
  detected_format: DetectedFormat;
  total_rows_detected: number;
  created: Company[];
  created_count: number;
  skipped_duplicate_in_paste: string[];
  skipped_existing_in_db: string[];
  skipped_invalid: SkippedInvalidEntry[];
}
