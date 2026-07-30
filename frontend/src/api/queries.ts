/**
 * TanStack Query hooks wrapping the API clients (`./companies.ts`,
 * `./companyDetail.ts`, `./jobs.ts`, `./imports.ts`, `./queueStats.ts` —
 * all real backend clients as of Task 014/019; `./mock/client.ts` is no
 * longer used by any hook here, but stays in place per the contract's
 * allowed-paths list).
 *
 * Pages depend only on these hooks, never on the client modules directly,
 * so swapping a client implementation is a one-file change here.
 */

import { useMutation, useQuery } from "@tanstack/react-query";

import { listCompanies } from "./companies";
import { fetchCompanyDetail } from "./companyDetail";
import { commitStoreLeadsImport, previewStoreLeadsImport } from "./imports";
import { fetchPipelineJobs } from "./jobs";
import { fetchQueueStats } from "./queueStats";
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
    queryFn: () => fetchPipelineJobs(filters),
  });
}

/**
 * `refetchInterval: 7000` — the exact midpoint of the confirmed 5-10s
 * polling range (see the queue-statistics-ui feature contract's
 * Decision 4). Cheap Redis reads make request cost a non-issue at this
 * range; 7s keeps a stuck queue or dead worker visible within one
 * page-glance without polling at the aggressive end for no benefit.
 */
export function useQueueStats(queueName = "crawling") {
  return useQuery({
    queryKey: ["queueStats", queueName],
    queryFn: () => fetchQueueStats(queueName),
    refetchInterval: 7000,
  });
}

/**
 * Two separate mutations, not one hook hiding both steps: preview and
 * commit are independent user actions (Preview / Confirm import buttons)
 * with independently-rendered loading/error states. There is no
 * server-side preview-session state to share between them (commit
 * resubmits the full `html` string) — see ADR 0002.
 */
export function useStoreLeadsPreview() {
  return useMutation({ mutationFn: previewStoreLeadsImport });
}

export function useStoreLeadsCommit() {
  return useMutation({ mutationFn: commitStoreLeadsImport });
}
