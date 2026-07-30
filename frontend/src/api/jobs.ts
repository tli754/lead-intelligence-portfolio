/**
 * Real API client backing `JobsPage`, composing three already-live
 * pipeline-run listing endpoints (`GET /api/discovery-runs`,
 * `GET /api/crawl-runs`, `GET /api/extraction-runs`) into the existing
 * mock-shaped `Job` view (`src/schemas/job.ts`).
 *
 * `analysis`/`scoring` stages have no backend module yet — requesting
 * either always returns an empty result with no network call (AC-03).
 *
 * See the "wire-jobs-page-to-pipeline-runs" feature contract's
 * "Field & Status Mapping" table (binding) for the exact field/status
 * translation implemented below.
 */

import { listCompanies } from "./companies";
import type { Job, JobListFilters, JobListResponse, JobStage, JobStatus } from "@/schemas/job";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

/** Raised when any of the three composed run-list requests is rejected (non-2xx). */
export class JobsRequestError extends Error {}

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

// --- Status mapping (contract's binding Field & Status Mapping table) -----------

/**
 * Every literal value across `DiscoveryStatus`, `CrawlStatus`, and
 * `ExtractionStatus` (`backend/app/modules/{discovery,crawling,extraction}/domain/enums.py`).
 * Discovery only ever produces a subset of these (`queued`, `running`,
 * `completed`, `completed_with_warnings`, `failed`) — the union still
 * covers every module so one mapping table serves all three.
 */
export type BackendRunStatus =
  | "queued"
  | "running"
  | "completed"
  | "completed_with_warnings"
  | "partial"
  | "failed"
  | "cancelled"
  | "stale";

/**
 * The binding status mapping from the feature contract — do not
 * improvise per-module. A `Record` over the full `BackendRunStatus`
 * union so TypeScript itself enforces totality: adding a new backend
 * status literal without updating this table is a compile error.
 */
export const RUN_STATUS_TO_JOB_STATUS: Record<BackendRunStatus, JobStatus> = {
  queued: "queued",
  running: "running",
  completed: "succeeded",
  completed_with_warnings: "succeeded",
  partial: "succeeded",
  failed: "failed",
  cancelled: "failed",
  stale: "succeeded",
};

/**
 * Maps a raw backend run status string to a `JobStatus`. Throws on any
 * value outside `BackendRunStatus` rather than returning `undefined` —
 * `JobStatusBadge`'s `JOB_STATUS_CONFIG[status]` lookup has no fallback
 * branch and would throw obscurely on `undefined`; failing loudly here,
 * at the API boundary, is easier to diagnose.
 */
export function mapRunStatusToJobStatus(status: string): JobStatus {
  const mapped = RUN_STATUS_TO_JOB_STATUS[status as BackendRunStatus];
  if (mapped === undefined) {
    throw new Error(`Unmapped pipeline run status: "${status}"`);
  }
  return mapped;
}

// --- company_id -> domain resolution --------------------------------------------

/**
 * The maximum `pageSize` `GET /api/companies` accepts
 * (`Query(..., le=200)` on the backend) — requested up front so the
 * `company_id` -> `domain` map covers realistic datasets in one call.
 */
const MAX_COMPANY_PAGE_SIZE = 200;

/**
 * `company_id` -> `domain`, for runs whose `Job` view needs
 * `company_domain` but the run record itself only carries `company_id`
 * (see the contract's Field & Status Mapping table).
 */
async function buildCompanyDomainMap(): Promise<Map<string, string>> {
  const { items } = await listCompanies({}, MAX_COMPANY_PAGE_SIZE);
  return new Map(items.map((item) => [item.company_id, item.domain]));
}

/**
 * Resolves a run's `company_domain`, falling back to the raw
 * `company_id` (AC-05) when the company was deleted after the run was
 * created and no longer appears in `domainMap`.
 */
function resolveCompanyDomain(companyId: string, domainMap: Map<string, string>): string {
  return domainMap.get(companyId) ?? companyId;
}

// --- Run DTOs (camelCase over the wire) + list-envelope shape -------------------

interface PaginationDto {
  page: number;
  pageSize: number;
  total: number;
}

interface RunListEnvelopeDto<T> {
  data: T[];
  pagination: PaginationDto;
}

/** `DiscoveryRunResponse` (`backend/app/modules/discovery/api/schemas.py`), fields used here only. */
interface DiscoveryRunDto {
  discoveryRunId: string;
  companyId: string;
  status: string;
  startedAt: string | null;
  completedAt: string | null;
  error: string | null;
  createdAt: string;
}

/** `CrawlRunResponse` (`backend/app/modules/crawling/api/schemas.py`), fields used here only. */
interface CrawlRunDto {
  crawlRunId: string;
  companyId: string;
  status: string;
  startedAt: string | null;
  completedAt: string | null;
  error: string | null;
  createdAt: string;
}

/** `ExtractionRunResponse` (`backend/app/modules/extraction/api/schemas.py`), fields used here only. */
interface ExtractionRunDto {
  extractionRunId: string;
  companyId: string;
  status: string;
  startedAt: string | null;
  completedAt: string | null;
  error: string | null;
  createdAt: string;
}

async function fetchRunList<T>(
  path: string,
  params: URLSearchParams,
): Promise<RunListEnvelopeDto<T>> {
  const query = params.toString();
  const response = await fetch(`${API_BASE_URL}${path}${query ? `?${query}` : ""}`);

  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as FastApiErrorBody;
    throw new JobsRequestError(extractErrorMessage(body, `The ${path} request was rejected.`));
  }

  return (await response.json()) as RunListEnvelopeDto<T>;
}

/** `GET /api/discovery-runs?page=&pageSize=` */
export async function listDiscoveryRuns(
  pageSize = MAX_COMPANY_PAGE_SIZE,
): Promise<RunListEnvelopeDto<DiscoveryRunDto>> {
  const params = new URLSearchParams({ page: "1", pageSize: String(pageSize) });
  return fetchRunList<DiscoveryRunDto>("/api/discovery-runs", params);
}

/** `GET /api/crawl-runs?page=&pageSize=` */
export async function listCrawlRuns(
  pageSize = MAX_COMPANY_PAGE_SIZE,
): Promise<RunListEnvelopeDto<CrawlRunDto>> {
  const params = new URLSearchParams({ page: "1", pageSize: String(pageSize) });
  return fetchRunList<CrawlRunDto>("/api/crawl-runs", params);
}

/** `GET /api/extraction-runs?page=&pageSize=` */
export async function listExtractionRuns(
  pageSize = MAX_COMPANY_PAGE_SIZE,
): Promise<RunListEnvelopeDto<ExtractionRunDto>> {
  const params = new URLSearchParams({ page: "1", pageSize: String(pageSize) });
  return fetchRunList<ExtractionRunDto>("/api/extraction-runs", params);
}

// --- Run -> Job mapping (contract's binding Field & Status Mapping table) ------

function discoveryRunToJob(run: DiscoveryRunDto, domainMap: Map<string, string>): Job {
  return {
    job_id: run.discoveryRunId,
    company_id: run.companyId,
    company_domain: resolveCompanyDomain(run.companyId, domainMap),
    stage: "discovery",
    status: mapRunStatusToJobStatus(run.status),
    queued_at: run.createdAt,
    started_at: run.startedAt,
    finished_at: run.completedAt,
    error_message: run.error,
  };
}

function crawlRunToJob(run: CrawlRunDto, domainMap: Map<string, string>): Job {
  return {
    job_id: run.crawlRunId,
    company_id: run.companyId,
    company_domain: resolveCompanyDomain(run.companyId, domainMap),
    stage: "crawl",
    status: mapRunStatusToJobStatus(run.status),
    queued_at: run.createdAt,
    started_at: run.startedAt,
    finished_at: run.completedAt,
    error_message: run.error,
  };
}

function extractionRunToJob(run: ExtractionRunDto, domainMap: Map<string, string>): Job {
  return {
    job_id: run.extractionRunId,
    company_id: run.companyId,
    company_domain: resolveCompanyDomain(run.companyId, domainMap),
    stage: "extraction",
    status: mapRunStatusToJobStatus(run.status),
    queued_at: run.createdAt,
    started_at: run.startedAt,
    finished_at: run.completedAt,
    error_message: run.error,
  };
}

/** Stages with a real backend module — `analysis`/`scoring` are handled separately (AC-03). */
const BUILT_STAGES: readonly JobStage[] = ["discovery", "crawl", "extraction"];

async function fetchJobsForStage(
  stage: "discovery" | "crawl" | "extraction",
  domainMap: Map<string, string>,
): Promise<Job[]> {
  if (stage === "discovery") {
    const envelope = await listDiscoveryRuns();
    return envelope.data.map((run) => discoveryRunToJob(run, domainMap));
  }
  if (stage === "crawl") {
    const envelope = await listCrawlRuns();
    return envelope.data.map((run) => crawlRunToJob(run, domainMap));
  }
  const envelope = await listExtractionRuns();
  return envelope.data.map((run) => extractionRunToJob(run, domainMap));
}

/**
 * `GET /api/discovery-runs`, `GET /api/crawl-runs`, and
 * `GET /api/extraction-runs`, composed into the mock-shaped
 * `JobListResponse` `JobsPage` already renders.
 *
 * `filters.stage === "analysis" | "scoring"` returns an empty result
 * immediately, with no network call (AC-03 — no backend module exists
 * for either stage yet). Otherwise queries whichever of the three real
 * stages `filters.stage` implies (or all three if unset), maps each run
 * via the Field & Status Mapping table, merges, applies `filters.status`
 * client-side (the backend's own `status` query param takes a
 * per-module enum, not a `JobStatus`, so filtering happens after
 * mapping rather than being pushed down as a query param), and sorts by
 * `queued_at` descending — matching `src/api/mock/client.ts`'s
 * `fetchJobs` sort.
 */
export async function fetchPipelineJobs(filters: JobListFilters = {}): Promise<JobListResponse> {
  if (filters.stage === "analysis" || filters.stage === "scoring") {
    return { items: [], total: 0 };
  }

  const stagesToQuery = filters.stage
    ? BUILT_STAGES.filter((stage) => stage === filters.stage)
    : BUILT_STAGES;

  const domainMap = await buildCompanyDomainMap();
  const jobLists = await Promise.all(
    stagesToQuery.map((stage) =>
      fetchJobsForStage(stage as "discovery" | "crawl" | "extraction", domainMap),
    ),
  );

  let merged = jobLists.flat();
  if (filters.status) {
    merged = merged.filter((job) => job.status === filters.status);
  }
  merged.sort((a, b) => b.queued_at.localeCompare(a.queued_at));

  return { items: merged, total: merged.length };
}
