import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as jobsApi from "@/api/jobs";
import * as queueStatsApi from "@/api/queueStats";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { Job, JobListFilters, JobListResponse } from "@/schemas/job";
import type { QueueStats } from "@/schemas/queueStats";
import { JobsPage } from "./JobsPage";

/**
 * These tests mock `fetchPipelineJobs` (the real API client, see
 * `frontend/src/api/jobs.ts`), not `src/api/mock/**`, matching Task 010/
 * 011's precedent for `CompaniesPage`/`CompanyDetailPage`.
 *
 * Every test also mocks `fetchQueueStats` (`frontend/src/api/queueStats.ts`)
 * via the `beforeEach` below — `JobsPage` now renders `QueueStatsPanel`,
 * which calls it on every render, independently of `fetchPipelineJobs`
 * (Task 019).
 */
const NORMAL_QUEUE_STATS: QueueStats = {
  queue: "crawling",
  counts: { queued: 0, started: 0, finished: 0, failed: 0, deferred: 0, scheduled: 0 },
  failed_job_ids: [],
  workers_alive: 0,
};

const discoveryJob: Job = {
  job_id: "discovery-run-1",
  company_id: "company-1",
  company_domain: "summit-outfitters.com",
  stage: "discovery",
  status: "succeeded",
  queued_at: "2026-01-10T00:00:00+00:00",
  started_at: "2026-01-10T00:01:00+00:00",
  finished_at: "2026-01-10T00:05:00+00:00",
  error_message: null,
};

const crawlJob: Job = {
  job_id: "crawl-run-1",
  company_id: "deleted-company",
  company_domain: "deleted-company",
  stage: "crawl",
  status: "failed",
  queued_at: "2026-01-12T00:00:00+00:00",
  started_at: null,
  finished_at: null,
  error_message: "network timeout",
};

const ALL_JOBS = [discoveryJob, crawlJob];

function fakeFetchPipelineJobs(filters: JobListFilters = {}): Promise<JobListResponse> {
  if (filters.stage === "analysis" || filters.stage === "scoring") {
    return Promise.resolve({ items: [], total: 0 });
  }
  const items = ALL_JOBS.filter((job) => {
    if (filters.stage && job.stage !== filters.stage) return false;
    if (filters.status && job.status !== filters.status) return false;
    return true;
  });
  return Promise.resolve({ items, total: items.length });
}

function renderPage() {
  return renderWithProviders(<JobsPage />);
}

describe("JobsPage", () => {
  beforeEach(() => {
    vi.spyOn(queueStatsApi, "fetchQueueStats").mockResolvedValue(NORMAL_QUEUE_STATS);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders pipeline jobs from the real fetchPipelineJobs client", async () => {
    vi.spyOn(jobsApi, "fetchPipelineJobs").mockImplementation(fakeFetchPipelineJobs);
    renderPage();

    expect(await screen.findByText("summit-outfitters.com")).toBeInTheDocument();
    expect(screen.getByText("deleted-company")).toBeInTheDocument();
    expect(screen.getByText("2 jobs")).toBeInTheDocument();
  });

  it("renders a company whose domain could not be resolved with the raw company_id fallback", async () => {
    vi.spyOn(jobsApi, "fetchPipelineJobs").mockImplementation(fakeFetchPipelineJobs);
    renderPage();

    expect(await screen.findByText("deleted-company")).toBeInTheDocument();
  });

  it("shows an empty result rather than an error for the analysis stage", async () => {
    vi.spyOn(jobsApi, "fetchPipelineJobs").mockImplementation(fakeFetchPipelineJobs);
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("summit-outfitters.com");

    await user.selectOptions(screen.getByLabelText(/stage/i), "analysis");

    expect(await screen.findByText("No jobs match these filters.")).toBeInTheDocument();
    expect(screen.queryByText(/couldn't load jobs/i)).not.toBeInTheDocument();
  });

  it("shows an error alert when fetchPipelineJobs rejects", async () => {
    vi.spyOn(jobsApi, "fetchPipelineJobs").mockRejectedValue(
      new jobsApi.JobsRequestError("boom"),
    );
    renderPage();

    expect(await screen.findByText("Couldn't load jobs")).toBeInTheDocument();
  });

  it("keeps the jobs table rendering normally when the queue-stats panel fails to load (AC-12)", async () => {
    vi.spyOn(queueStatsApi, "fetchQueueStats").mockRejectedValue(
      new queueStatsApi.QueueStatsRequestError("queue stats boom"),
    );
    vi.spyOn(jobsApi, "fetchPipelineJobs").mockImplementation(fakeFetchPipelineJobs);

    renderPage();

    expect(await screen.findByText("Couldn't load queue stats")).toBeInTheDocument();
    expect(await screen.findByText("summit-outfitters.com")).toBeInTheDocument();
    expect(screen.getByText("deleted-company")).toBeInTheDocument();
    expect(screen.queryByText("Couldn't load jobs")).not.toBeInTheDocument();
  });
});
