import { afterEach, describe, expect, it, vi } from "vitest";

import {
  fetchPipelineJobs,
  JobsRequestError,
  mapRunStatusToJobStatus,
  RUN_STATUS_TO_JOB_STATUS,
  type BackendRunStatus,
} from "./jobs";
import { jobStatusSchema } from "@/schemas/job";

/**
 * Every literal value of `DiscoveryStatus`, `CrawlStatus`, and
 * `ExtractionStatus` (`backend/app/modules/{discovery,crawling,extraction}/domain/enums.py`).
 * This list — not `RUN_STATUS_TO_JOB_STATUS`'s own keys — is the test's
 * source of truth, per the contract's Required Tests section: it must
 * independently enumerate every backend enum value, not just check that
 * whatever the implementation already maps happens to be internally
 * consistent.
 */
const ALL_BACKEND_STATUSES: BackendRunStatus[] = [
  // DiscoveryStatus
  "queued",
  "running",
  "completed",
  "completed_with_warnings",
  "failed",
  // CrawlStatus adds:
  "partial",
  "cancelled",
  // ExtractionStatus adds:
  "stale",
];

const EXPECTED_MAPPING: Record<BackendRunStatus, string> = {
  queued: "queued",
  running: "running",
  completed: "succeeded",
  completed_with_warnings: "succeeded",
  partial: "succeeded",
  failed: "failed",
  cancelled: "failed",
  stale: "succeeded",
};

describe("mapRunStatusToJobStatus", () => {
  it.each(ALL_BACKEND_STATUSES)(
    "maps backend status %s to exactly one of the 4 frontend JobStatus values",
    (status) => {
      const mapped = mapRunStatusToJobStatus(status);
      expect(() => jobStatusSchema.parse(mapped)).not.toThrow();
      expect(mapped).toBe(EXPECTED_MAPPING[status]);
    },
  );

  it("covers every ALL_BACKEND_STATUSES entry in RUN_STATUS_TO_JOB_STATUS (totality)", () => {
    for (const status of ALL_BACKEND_STATUSES) {
      expect(RUN_STATUS_TO_JOB_STATUS[status]).toBeDefined();
    }
  });

  it("throws rather than silently returning undefined for an unrecognized status", () => {
    expect(() => mapRunStatusToJobStatus("not_a_real_status")).toThrow();
  });
});

describe("fetchPipelineJobs", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  const COMPANIES_ENVELOPE = {
    data: [
      {
        companyId: "company-1",
        companyName: "Summit Outfitters",
        domain: "summit-outfitters.com",
        platform: "Shopify",
        country: "US",
        city: "Denver",
        opportunityScore: null,
        confidence: null,
        mainReason: null,
        processingStatus: "ready",
        workflowStatus: "shortlisted",
        updatedAt: "2026-01-15T10:00:00+00:00",
      },
    ],
    pagination: { page: 1, pageSize: 200, total: 1 },
  };

  function emptyRunEnvelope() {
    return { data: [], pagination: { page: 1, pageSize: 200, total: 0 } };
  }

  function jsonResponse(body: unknown) {
    return new Response(JSON.stringify(body), { status: 200 });
  }

  function stubFetch(handler: (url: string) => Response) {
    const fetchMock = vi.fn().mockImplementation((url: string) => Promise.resolve(handler(url)));
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  it("returns an empty result with no network call for the analysis stage", async () => {
    const fetchMock = stubFetch(() => jsonResponse(emptyRunEnvelope()));

    const result = await fetchPipelineJobs({ stage: "analysis" });

    expect(result).toEqual({ items: [], total: 0 });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("returns an empty result with no network call for the scoring stage", async () => {
    const fetchMock = stubFetch(() => jsonResponse(emptyRunEnvelope()));

    const result = await fetchPipelineJobs({ stage: "scoring" });

    expect(result).toEqual({ items: [], total: 0 });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("resolves company_domain from the companies list when the company is found", async () => {
    stubFetch((url) => {
      if (url.includes("/api/companies")) return jsonResponse(COMPANIES_ENVELOPE);
      if (url.includes("/api/discovery-runs")) {
        return jsonResponse({
          data: [
            {
              discoveryRunId: "run-1",
              companyId: "company-1",
              status: "completed",
              startedAt: "2026-01-15T09:00:00+00:00",
              completedAt: "2026-01-15T09:05:00+00:00",
              error: null,
              createdAt: "2026-01-15T08:00:00+00:00",
            },
          ],
          pagination: { page: 1, pageSize: 200, total: 1 },
        });
      }
      return jsonResponse(emptyRunEnvelope());
    });

    const result = await fetchPipelineJobs({ stage: "discovery" });

    expect(result.total).toBe(1);
    expect(result.items[0]).toMatchObject({
      job_id: "run-1",
      company_id: "company-1",
      company_domain: "summit-outfitters.com",
      stage: "discovery",
      status: "succeeded",
    });
  });

  it("falls back to the raw company_id when the company is not found (AC-05)", async () => {
    stubFetch((url) => {
      if (url.includes("/api/companies")) return jsonResponse(COMPANIES_ENVELOPE);
      if (url.includes("/api/crawl-runs")) {
        return jsonResponse({
          data: [
            {
              crawlRunId: "run-2",
              companyId: "deleted-company",
              status: "failed",
              startedAt: null,
              completedAt: null,
              error: "boom",
              createdAt: "2026-01-16T08:00:00+00:00",
            },
          ],
          pagination: { page: 1, pageSize: 200, total: 1 },
        });
      }
      return jsonResponse(emptyRunEnvelope());
    });

    const result = await fetchPipelineJobs({ stage: "crawl" });

    expect(result.items[0].company_domain).toBe("deleted-company");
    expect(result.items[0].status).toBe("failed");
    expect(result.items[0].error_message).toBe("boom");
  });

  it("merges all three stages and sorts by queued_at descending when no stage filter is set", async () => {
    stubFetch((url) => {
      if (url.includes("/api/companies")) return jsonResponse(COMPANIES_ENVELOPE);
      if (url.includes("/api/discovery-runs")) {
        return jsonResponse({
          data: [
            {
              discoveryRunId: "discovery-1",
              companyId: "company-1",
              status: "completed",
              startedAt: null,
              completedAt: null,
              error: null,
              createdAt: "2026-01-10T00:00:00+00:00",
            },
          ],
          pagination: { page: 1, pageSize: 200, total: 1 },
        });
      }
      if (url.includes("/api/crawl-runs")) {
        return jsonResponse({
          data: [
            {
              crawlRunId: "crawl-1",
              companyId: "company-1",
              status: "running",
              startedAt: null,
              completedAt: null,
              error: null,
              createdAt: "2026-01-20T00:00:00+00:00",
            },
          ],
          pagination: { page: 1, pageSize: 200, total: 1 },
        });
      }
      if (url.includes("/api/extraction-runs")) {
        return jsonResponse({
          data: [
            {
              extractionRunId: "extraction-1",
              companyId: "company-1",
              status: "queued",
              startedAt: null,
              completedAt: null,
              error: null,
              createdAt: "2026-01-15T00:00:00+00:00",
            },
          ],
          pagination: { page: 1, pageSize: 200, total: 1 },
        });
      }
      return jsonResponse(emptyRunEnvelope());
    });

    const result = await fetchPipelineJobs({});

    expect(result.total).toBe(3);
    expect(result.items.map((job) => job.job_id)).toEqual(["crawl-1", "extraction-1", "discovery-1"]);
  });

  it("filters the merged result by status client-side", async () => {
    stubFetch((url) => {
      if (url.includes("/api/companies")) return jsonResponse(COMPANIES_ENVELOPE);
      if (url.includes("/api/discovery-runs")) {
        return jsonResponse({
          data: [
            {
              discoveryRunId: "discovery-1",
              companyId: "company-1",
              status: "completed",
              startedAt: null,
              completedAt: null,
              error: null,
              createdAt: "2026-01-10T00:00:00+00:00",
            },
          ],
          pagination: { page: 1, pageSize: 200, total: 1 },
        });
      }
      if (url.includes("/api/crawl-runs")) {
        return jsonResponse({
          data: [
            {
              crawlRunId: "crawl-1",
              companyId: "company-1",
              status: "failed",
              startedAt: null,
              completedAt: null,
              error: "network timeout",
              createdAt: "2026-01-20T00:00:00+00:00",
            },
          ],
          pagination: { page: 1, pageSize: 200, total: 1 },
        });
      }
      return jsonResponse(emptyRunEnvelope());
    });

    const result = await fetchPipelineJobs({ status: "failed" });

    expect(result.total).toBe(1);
    expect(result.items[0].job_id).toBe("crawl-1");
  });

  it("throws JobsRequestError when a run-list request is rejected", async () => {
    stubFetch((url) => {
      if (url.includes("/api/companies")) return jsonResponse(COMPANIES_ENVELOPE);
      return new Response(JSON.stringify({ detail: "boom" }), { status: 500 });
    });

    await expect(fetchPipelineJobs({ stage: "discovery" })).rejects.toThrow(JobsRequestError);
  });
});
