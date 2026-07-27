/**
 * Mock API layer for the companies-ranking and jobs features.
 *
 * Every exported function here has the signature and return shape a real
 * `fetch()`-based client would have once the FastAPI backend implements
 * these endpoints (see the request-shape comment above each function).
 * Responses are validated with the same Zod schemas a real client would
 * use to validate JSON crossing the network boundary — swapping the body
 * of each function for a real `fetch()` call is the only change needed
 * later; callers (TanStack Query hooks, pages) do not change.
 *
 * `Do NOT connect to MongoDB` per the task that created this module: all
 * data lives in `fixtures.ts` and is filtered/sorted in memory.
 */

import { mockCompanies, mockJobs } from "./fixtures";
import {
  type CompanyDetail,
  type CompanyListFilters,
  type CompanyListItem,
  type CompanyListResponse,
  companyDetailSchema,
  companyListResponseSchema,
} from "@/schemas/company";
import {
  type JobListFilters,
  type JobListResponse,
  jobListResponseSchema,
} from "@/schemas/job";

/** Raised when a company id has no matching record (mimics a 404 response body). */
export class CompanyNotFoundError extends Error {
  constructor(companyId: string) {
    super(`No company found with id "${companyId}"`);
    this.name = "CompanyNotFoundError";
  }
}

const SIMULATED_LATENCY_MS = 150;

function simulateNetwork<T>(value: T): Promise<T> {
  return new Promise((resolve) => {
    setTimeout(() => resolve(value), SIMULATED_LATENCY_MS);
  });
}

function toListItem(detail: CompanyDetail): CompanyListItem {
  const {
    company_id,
    domain,
    identity,
    processing,
    workflow,
    score,
    confidence,
    updated_at,
  } = detail;
  return { company_id, domain, identity, processing, workflow, score, confidence, updated_at };
}

function matchesFilters(company: CompanyDetail, filters: CompanyListFilters): boolean {
  if (filters.processing_status && company.processing.status !== filters.processing_status) {
    return false;
  }
  if (filters.workflow_status && company.workflow.manual_status !== filters.workflow_status) {
    return false;
  }
  if (
    filters.platform &&
    company.identity.platform?.toLowerCase() !== filters.platform.toLowerCase()
  ) {
    return false;
  }
  if (filters.q) {
    const needle = filters.q.trim().toLowerCase();
    if (needle) {
      const haystack = `${company.domain} ${company.identity.company_name ?? ""}`.toLowerCase();
      if (!haystack.includes(needle)) return false;
    }
  }
  return true;
}

function compareBy(filters: CompanyListFilters) {
  const sort = filters.sort ?? "score";
  const order = filters.order ?? "desc";
  const direction = order === "asc" ? 1 : -1;

  return (a: CompanyDetail, b: CompanyDetail): number => {
    if (sort === "score") {
      // Un-scored companies always sort last, regardless of direction.
      if (a.score === null && b.score === null) return 0;
      if (a.score === null) return 1;
      if (b.score === null) return -1;
      return (a.score - b.score) * direction;
    }
    if (sort === "updated_at") {
      return a.updated_at.localeCompare(b.updated_at) * direction;
    }
    return a.domain.localeCompare(b.domain) * direction;
  };
}

/** `GET /api/companies?processing_status=&workflow_status=&platform=&q=&sort=&order=` */
export async function fetchCompanies(
  filters: CompanyListFilters = {},
): Promise<CompanyListResponse> {
  const filtered = mockCompanies.filter((company) => matchesFilters(company, filters));
  filtered.sort(compareBy(filters));

  const response: CompanyListResponse = {
    items: filtered.map(toListItem),
    total: filtered.length,
  };

  const validated = companyListResponseSchema.parse(response);
  return simulateNetwork(validated);
}

/** `GET /api/companies/{company_id}` */
export async function fetchCompanyById(companyId: string): Promise<CompanyDetail> {
  const company = mockCompanies.find((candidate) => candidate.company_id === companyId);
  if (!company) {
    await simulateNetwork(null);
    throw new CompanyNotFoundError(companyId);
  }

  const validated = companyDetailSchema.parse(company);
  return simulateNetwork(validated);
}

/** `GET /api/jobs?stage=&status=` */
export async function fetchJobs(filters: JobListFilters = {}): Promise<JobListResponse> {
  const filtered = mockJobs.filter((job) => {
    if (filters.stage && job.stage !== filters.stage) return false;
    if (filters.status && job.status !== filters.status) return false;
    return true;
  });
  filtered.sort((a, b) => b.queued_at.localeCompare(a.queued_at));

  const response: JobListResponse = { items: filtered, total: filtered.length };
  const validated = jobListResponseSchema.parse(response);
  return simulateNetwork(validated);
}
