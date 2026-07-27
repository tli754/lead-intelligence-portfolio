import type { ImportResponse } from "../types/company";
import type {
  CompanyListFilters,
  CompanyListItem,
  CompanyListResponse,
} from "../schemas/company";
import { companyListResponseSchema } from "../schemas/company";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

/** Raised when the API rejects an import request (e.g. 422 validation error). */
export class ImportRequestError extends Error {}

/** Raised when the API rejects a companies-list request (e.g. a bad query param). */
export class CompanyListRequestError extends Error {}

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

/** Posts raw pasted text to the import endpoint and returns the parsed result. */
export async function importCompanies(rawText: string): Promise<ImportResponse> {
  const response = await fetch(`${API_BASE_URL}/api/companies/import`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ raw_text: rawText }),
  });

  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as FastApiErrorBody;
    throw new ImportRequestError(extractErrorMessage(body, "The import request was rejected."));
  }

  return (await response.json()) as ImportResponse;
}

/**
 * The flat, camelCase list-item shape `GET /api/companies` actually
 * returns (`CompanyListItemResponse` in
 * `backend/app/modules/companies/api/schemas.py`). Kept separate from
 * `CompanyListItem` (the nested shape the rest of the frontend expects) —
 * `mapCompanyListItem` below is the only place that translates between
 * them.
 */
interface CompanyListItemDto {
  companyId: string;
  companyName: string | null;
  domain: string;
  platform: string | null;
  country: string | null;
  city: string | null;
  opportunityScore: number | null;
  confidence: string | null;
  mainReason: string | null;
  processingStatus: string;
  workflowStatus: string;
  updatedAt: string;
}

interface CompanyListEnvelopeDto {
  data: CompanyListItemDto[];
  pagination: { page: number; pageSize: number; total: number };
}

/**
 * Maps one flat `CompanyListItemDto` (as returned over the wire) to the
 * nested `CompanyListItem` shape the rest of the frontend expects.
 *
 * The list endpoint doesn't return per-run ids, `shortlisted`, or
 * `notes_count` — those default to `null`/a derived boolean/`0` rather
 * than being added to the backend response (see the companies-list
 * feature contract's "Known Shape Gaps"). `shortlisted` is therefore a
 * best-effort value derived from `workflowStatus`, not a real stored
 * field.
 */
export function mapCompanyListItem(dto: CompanyListItemDto): CompanyListItem {
  return {
    company_id: dto.companyId,
    domain: dto.domain,
    identity: {
      company_name: dto.companyName,
      platform: dto.platform,
      country: dto.country,
      city: dto.city,
    },
    processing: {
      status: dto.processingStatus as CompanyListItem["processing"]["status"],
      latest_discovery_run: null,
      latest_crawl_run: null,
      latest_extraction_run: null,
      latest_analysis_run: null,
      latest_scoring_run: null,
      failure_reason: null,
    },
    workflow: {
      manual_status: dto.workflowStatus as CompanyListItem["workflow"]["manual_status"],
      shortlisted: dto.workflowStatus === "shortlisted",
      notes_count: 0,
    },
    score: dto.opportunityScore,
    confidence: dto.confidence as CompanyListItem["confidence"],
    updated_at: dto.updatedAt,
  };
}

function buildCompanyListQuery(filters: CompanyListFilters): string {
  const params = new URLSearchParams();
  if (filters.processing_status) params.set("processingStatus", filters.processing_status);
  if (filters.workflow_status) params.set("workflowStatus", filters.workflow_status);
  if (filters.platform) params.set("platform", filters.platform);
  // `q`/`sort`/`order` have no backend equivalent on `GET /api/companies`
  // (no free-text search, no server-side sort) and are intentionally
  // dropped here rather than sent as unsupported query params.
  const query = params.toString();
  return query ? `?${query}` : "";
}

/**
 * `GET /api/companies?processingStatus=&workflowStatus=&platform=`
 *
 * `filters.q`/`filters.sort`/`filters.order` are accepted (so callers
 * don't need to strip them) but not sent — the real endpoint doesn't
 * support free-text search or server-side sorting.
 */
export async function listCompanies(
  filters: CompanyListFilters = {},
): Promise<CompanyListResponse> {
  const response = await fetch(`${API_BASE_URL}/api/companies${buildCompanyListQuery(filters)}`);

  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as FastApiErrorBody;
    throw new CompanyListRequestError(
      extractErrorMessage(body, "The companies request was rejected."),
    );
  }

  const envelope = (await response.json()) as CompanyListEnvelopeDto;
  const mapped: CompanyListResponse = {
    items: envelope.data.map(mapCompanyListItem),
    total: envelope.pagination.total,
  };
  return companyListResponseSchema.parse(mapped);
}
