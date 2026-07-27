/**
 * TanStack Query hooks wrapping the API clients (`./companies.ts` for the
 * real backend, `./mock/client.ts` for pages not wired to a real endpoint
 * yet).
 *
 * Pages depend only on these hooks, never on the client modules directly,
 * so swapping a mock client for a real `fetch()` call is a one-file
 * change here.
 */

import { useQuery } from "@tanstack/react-query";

import { listCompanies } from "./companies";
import { fetchCompanyDetail } from "./companyDetail";
import { fetchJobs } from "./mock/client";
import type { CompanyListFilters } from "@/schemas/company";
import type { JobListFilters } from "@/schemas/job";

export function useCompanies(filters: CompanyListFilters) {
  return useQuery({
    queryKey: ["companies", filters],
    queryFn: () => listCompanies(filters),
  });
}

export function useCompany(companyId: string | undefined) {
  return useQuery({
    queryKey: ["company", companyId],
    queryFn: () => fetchCompanyDetail(companyId as string),
    enabled: companyId !== undefined,
    retry: false,
  });
}

export function useJobs(filters: JobListFilters) {
  return useQuery({
    queryKey: ["jobs", filters],
    queryFn: () => fetchJobs(filters),
  });
}
