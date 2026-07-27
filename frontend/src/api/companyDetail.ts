/**
 * Real API client + composition function backing `CompanyDetailPage`.
 *
 * Composes three already-live endpoints into one `CompanyDetail`:
 *   - `GET /api/companies/{companyId}` (modules/companies)
 *   - `GET /api/companies/{companyId}/facts` (modules/extraction)
 *   - `GET /api/facts/{factId}/evidence` (modules/extraction, backed by
 *     modules/evidence)
 *
 * See the "wire-company-detail-to-real-api" feature contract's "Known
 * Shape Gaps" section for the field-by-field mapping decisions below —
 * each gap is numbered here to match that section.
 */

import { getFieldLabel } from "./fieldLabels";
import type { CompanyDetail, ConfidenceLevel, EvidenceItem } from "@/schemas/company";
import { companyDetailSchema } from "@/schemas/company";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

/** Raised when `GET /api/companies/{companyId}` returns 404. */
export class CompanyDetailNotFoundError extends Error {
  constructor(companyId: string) {
    super(`No company found with id "${companyId}"`);
    this.name = "CompanyDetailNotFoundError";
  }
}

/** Raised when any of the three composed requests is rejected (non-2xx, non-404). */
export class CompanyDetailRequestError extends Error {}

interface FastApiValidationDetail {
  msg?: string;
}

interface FastApiErrorBody {
  detail?: string | FastApiValidationDetail[];
}

function extractErrorMessage(body: FastApiErrorBody, fallback: string): string {
  const { detail } = body;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0 && detail[0].msg) return detail[0].msg;
  return fallback;
}

// --- T1: real client functions -------------------------------------------

/** `CompanyResponse` (`backend/app/modules/companies/api/schemas.py`), camelCase over the wire. */
export interface CompanyResponseDto {
  companyId: string;
  domain: string;
  normalizedDomain: string;
  identity: {
    companyName: string | null;
    platform: string | null;
    country: string | null;
    city: string | null;
  };
  processing: {
    status: string;
    latestDiscoveryRunId: string | null;
    latestCrawlRunId: string | null;
    latestExtractionRunId: string | null;
    latestAnalysisRunId: string | null;
    latestScoringRunId: string | null;
  };
  workflow: {
    manualStatus: string;
    shortlisted: boolean;
    notesCount: number;
  };
  createdAt: string;
  updatedAt: string;
  documentVersion: number;
}

/** `GET /api/companies/{companyId}` */
export async function getCompany(companyId: string): Promise<CompanyResponseDto> {
  const response = await fetch(`${API_BASE_URL}/api/companies/${companyId}`);

  if (response.status === 404) {
    throw new CompanyDetailNotFoundError(companyId);
  }
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as FastApiErrorBody;
    throw new CompanyDetailRequestError(
      extractErrorMessage(body, "The company request was rejected."),
    );
  }

  return (await response.json()) as CompanyResponseDto;
}

/** `FactResponse` (`backend/app/modules/extraction/api/schemas.py`), camelCase over the wire. */
export interface FactResponseDto {
  factId: string;
  companyId: string;
  fieldPath: string;
  value: unknown;
  normalizedValue: unknown;
  evidenceIds: string[];
  status: string;
  [key: string]: unknown;
}

interface PaginationMetaDto {
  page: number;
  pageSize: number;
  total: number;
}

export interface PaginatedEnvelopeDto<T> {
  data: T[];
  pagination: PaginationMetaDto;
}

/**
 * The maximum `pageSize` `GET /api/companies/{id}/facts` and
 * `GET /api/facts/{id}/evidence` both accept (`Query(..., le=200)` on the
 * backend). Requesting the max up front keeps the common case (a company
 * with a normal number of facts/evidence items) to one round trip per
 * call, while `fetchAllPages` below still pages through the rest for the
 * rare company that exceeds it (AC-04).
 */
const MAX_PAGE_SIZE = 200;

/** `GET /api/companies/{companyId}/facts?page=&pageSize=` */
export async function listCompanyFacts(
  companyId: string,
  page = 1,
  pageSize = MAX_PAGE_SIZE,
): Promise<PaginatedEnvelopeDto<FactResponseDto>> {
  const response = await fetch(
    `${API_BASE_URL}/api/companies/${companyId}/facts?page=${page}&pageSize=${pageSize}`,
  );

  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as FastApiErrorBody;
    throw new CompanyDetailRequestError(
      extractErrorMessage(body, "The company facts request was rejected."),
    );
  }

  return (await response.json()) as PaginatedEnvelopeDto<FactResponseDto>;
}

/** `EvidenceResponse` (`backend/app/modules/evidence/api/schemas.py`), camelCase over the wire. */
export interface EvidenceResponseDto {
  evidenceId: string;
  factFieldPath: string;
  evidenceType: string;
  pageType: string;
  strength: string;
  sourceUrl: string;
  rawValue: string | null;
  normalizedValue: string | null;
  excerpt: { text: string };
  observedAt: string;
}

/** `GET /api/facts/{factId}/evidence?page=&pageSize=` */
export async function listFactEvidence(
  factId: string,
  page = 1,
  pageSize = MAX_PAGE_SIZE,
): Promise<PaginatedEnvelopeDto<EvidenceResponseDto>> {
  const response = await fetch(
    `${API_BASE_URL}/api/facts/${factId}/evidence?page=${page}&pageSize=${pageSize}`,
  );

  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as FastApiErrorBody;
    throw new CompanyDetailRequestError(
      extractErrorMessage(body, "The fact evidence request was rejected."),
    );
  }

  return (await response.json()) as PaginatedEnvelopeDto<EvidenceResponseDto>;
}

// --- T2: composition function ---------------------------------------------

/**
 * Fetches every page of a paginated envelope, starting from page 1,
 * rather than truncating to whatever the first page returns (AC-04:
 * company detail is a single-entity view, so a company with more facts —
 * or a fact with more evidence — than one `pageSize` must still show
 * everything, not just the first page).
 */
async function fetchAllPages<T>(
  loadPage: (page: number, pageSize: number) => Promise<PaginatedEnvelopeDto<T>>,
  pageSize = MAX_PAGE_SIZE,
): Promise<T[]> {
  const firstPage = await loadPage(1, pageSize);
  const items = [...firstPage.data];
  const totalPages = Math.ceil(firstPage.pagination.total / firstPage.pagination.pageSize) || 1;

  for (let page = 2; page <= totalPages; page += 1) {
    const nextPage = await loadPage(page, pageSize);
    items.push(...nextPage.data);
  }

  return items;
}

/**
 * Gap #7: `EvidenceStrength` (backend, 4 levels) -> `ConfidenceLevel`
 * (frontend, 3 levels). Named constant per the contract, not inline
 * conditionals, so every strength value is guaranteed to map to a defined
 * level (AC-05) — `EvidenceViewer`'s `CONFIDENCE_TONE` lookup throws on an
 * unmapped key.
 */
export const EVIDENCE_STRENGTH_TO_CONFIDENCE: Record<string, ConfidenceLevel> = {
  authoritative: "high",
  strong: "high",
  moderate: "medium",
  weak: "low",
};

function mapConfidence(strength: string): ConfidenceLevel {
  return EVIDENCE_STRENGTH_TO_CONFIDENCE[strength] ?? "low";
}

/**
 * Gap #9: `EvidenceResponse` has no single `source` string — the nearest
 * equivalents are `evidenceType` (e.g. `"page_text"`, `"meta_tag"`) and
 * `pageType`. `evidenceType` is chosen here because it describes *how* the
 * value was found (more useful next to a confidence badge than *what kind
 * of page* it came from, which `pageType` describes) — trivially
 * changeable later per the contract's risk note.
 */
function mapSource(evidence: EvidenceResponseDto): string {
  return evidence.evidenceType;
}

/** Best available human-readable value for one evidence item, in priority order. */
function mapEvidenceValue(evidence: EvidenceResponseDto): string {
  return evidence.normalizedValue ?? evidence.rawValue ?? evidence.excerpt.text;
}

export function mapEvidenceItem(evidence: EvidenceResponseDto): EvidenceItem {
  return {
    evidence_id: evidence.evidenceId,
    field: evidence.factFieldPath,
    label: getFieldLabel(evidence.factFieldPath),
    value: mapEvidenceValue(evidence),
    confidence: mapConfidence(evidence.strength),
    source: mapSource(evidence),
    source_url: evidence.sourceUrl,
    observed_at: evidence.observedAt,
    // Gap #8: real per-evidence-item conflict data isn't available from
    // this endpoint (it returns evidence for one already-accepted fact,
    // not cross-candidate conflicts). Always `[]` — see the contract's
    // "Known Shape Gaps" #8 and AC-06. `EvidenceViewer`'s "Conflicting
    // evidence" banner will not appear for real data until a follow-up
    // task wires in `FactConflictResponse`.
    conflicts_with: [],
  };
}

/** Extracts a `string_list`-typed fact's `value` (already a bare `string[]`) by field path. */
function extractStringListFact(facts: FactResponseDto[], fieldPath: string): string[] {
  const fact = facts.find((candidate) => candidate.fieldPath === fieldPath);
  if (!fact || !Array.isArray(fact.value)) return [];
  return fact.value.filter((item): item is string => typeof item === "string");
}

/**
 * Gap #1: maps `CompanyResponse` to `CompanyDetail`'s
 * `identity`/`processing`/`workflow`/`score`/`confidence`, the same shape
 * of adapter Task 010's `mapCompanyListItem` (`./companies.ts`) applies
 * for the list endpoint. Two differences from that adapter, both because
 * `CompanyResponse` (unlike `CompanyListItemResponse`) actually returns
 * these fields:
 *   - `workflow.shortlisted`/`notes_count` come straight from the
 *     response instead of being derived from `manual_status`.
 *   - `processing.latest_*_run` stay `null` even though `CompanyResponse`
 *     has `latest*RunId` fields — those are opaque run *ids*, not
 *     timestamps, and `CompanyDetailPage` formats this field as a date
 *     (`formatDateTime`), so surfacing an id there would render
 *     "Invalid Date" instead of being an improvement.
 */
function mapCompanySummary(
  dto: CompanyResponseDto,
): Omit<CompanyDetail, "emails" | "phones" | "score_factors" | "evidence"> {
  return {
    company_id: dto.companyId,
    domain: dto.domain,
    // Gap #2: `url` <- `CompanyResponse.domain`. The backend stores a bare
    // host (no scheme), so this prepends `https://` to make it a usable
    // link — a derivation, not a fabrication, since `domain` already
    // uniquely determines the URL a browser would visit.
    url: `https://${dto.domain}`,
    identity: {
      company_name: dto.identity.companyName,
      platform: dto.identity.platform,
      country: dto.identity.country,
      city: dto.identity.city,
    },
    processing: {
      status: dto.processing.status as CompanyDetail["processing"]["status"],
      latest_discovery_run: null,
      latest_crawl_run: null,
      latest_extraction_run: null,
      latest_analysis_run: null,
      latest_scoring_run: null,
      failure_reason: null,
    },
    workflow: {
      manual_status: dto.workflow.manualStatus as CompanyDetail["workflow"]["manual_status"],
      shortlisted: dto.workflow.shortlisted,
      notes_count: dto.workflow.notesCount,
    },
    // Gap #4: no scoring module exists yet — always null/empty, rendered
    // as an explicit "not yet scored" state by `CompanyDetailPage`/
    // `ConfidenceMeter` (AC-03), consistent with Task 010's list-page
    // treatment of the same gap.
    score: null,
    confidence: null,
    created_at: dto.createdAt,
    updated_at: dto.updatedAt,
  };
}

/**
 * `GET /api/companies/{id}`, `GET /api/companies/{id}/facts`, and
 * `GET /api/facts/{factId}/evidence`, composed into one `CompanyDetail`.
 *
 * Gap #5: fetches evidence per fact (N+1) — accepted for this task's
 * scope; a company's fact count is bounded by `field_catalogue.py`'s
 * fixed set of field paths, so this is not unbounded.
 */
export async function fetchCompanyDetail(companyId: string): Promise<CompanyDetail> {
  const companyDto = await getCompany(companyId);
  const facts = await fetchAllPages((page, pageSize) =>
    listCompanyFacts(companyId, page, pageSize),
  );

  const evidenceLists = await Promise.all(
    facts.map((fact) =>
      fetchAllPages((page, pageSize) => listFactEvidence(fact.factId, page, pageSize)),
    ),
  );
  const evidence = evidenceLists.flat().map(mapEvidenceItem);

  const detail: CompanyDetail = {
    ...mapCompanySummary(companyDto),
    // Gap #3: pulled from the accepted facts list by `field_path`, not
    // fabricated. `organisation.emails`/`organisation.phone_numbers` are
    // `string_list`-typed fields reconciled by `SET_UNION` merge
    // (`modules/extraction/domain/reconciliation.py`), whose `value` is
    // already a bare `string[]` (verified against
    // `organisation_extractor.py` — each email/phone candidate's
    // `normalized_value` is a single string, and array reconciliation
    // collects those into `FactRecord.value` directly, not a
    // list-of-objects). Defaults to `[]` if the company has no such fact.
    emails: extractStringListFact(facts, "organisation.emails"),
    phones: extractStringListFact(facts, "organisation.phone_numbers"),
    score_factors: [],
    evidence,
  };

  return companyDetailSchema.parse(detail);
}
