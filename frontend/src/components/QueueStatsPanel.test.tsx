import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as queueStatsApi from "@/api/queueStats";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { QueueStats } from "@/schemas/queueStats";
import { QueueStatsPanel } from "./QueueStatsPanel";

/**
 * Mocks `fetchQueueStats` (the real API client, see
 * `frontend/src/api/queueStats.ts`), matching `JobsPage.test.tsx`'s
 * established `vi.spyOn` pattern — not MSW, no new mocking library.
 */
function renderPanel() {
  return renderWithProviders(<QueueStatsPanel />);
}

describe("QueueStatsPanel", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders counts, worker pill, and failed-job badges from a successful fetch (AC-09)", async () => {
    const stats: QueueStats = {
      queue: "crawling",
      counts: {
        queued: 2,
        started: 1,
        finished: 42,
        failed: 3,
        deferred: 5,
        scheduled: 7,
      },
      failed_job_ids: ["job-a", "job-b", "job-c"],
      workers_alive: 1,
    };
    vi.spyOn(queueStatsApi, "fetchQueueStats").mockResolvedValue(stats);

    renderPanel();

    expect(await screen.findByText("Queued")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("Started")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("Finished")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("Deferred")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
    expect(screen.getByText("Scheduled")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();

    expect(screen.getByText("1 worker(s) alive")).toBeInTheDocument();

    expect(screen.getByText("job-a")).toBeInTheDocument();
    expect(screen.getByText("job-b")).toBeInTheDocument();
    expect(screen.getByText("job-c")).toBeInTheDocument();
    expect(screen.queryByText(/more$/)).not.toBeInTheDocument();
  });

  it("truncates the failed-job display to 8 badges with a '+N more' suffix (AC-10)", async () => {
    const failedJobIds = Array.from({ length: 12 }, (_, i) => `job-${i + 1}`);
    const stats: QueueStats = {
      queue: "crawling",
      counts: { queued: 0, started: 0, finished: 0, failed: 12, deferred: 0, scheduled: 0 },
      failed_job_ids: failedJobIds,
      workers_alive: 2,
    };
    vi.spyOn(queueStatsApi, "fetchQueueStats").mockResolvedValue(stats);

    renderPanel();

    await screen.findByText("+4 more");

    for (const jobId of failedJobIds.slice(0, 8)) {
      expect(screen.getByText(jobId)).toBeInTheDocument();
    }
    for (const jobId of failedJobIds.slice(8)) {
      expect(screen.queryByText(jobId)).not.toBeInTheDocument();
    }
  });

  it("renders the zero-count/zero-worker response as normal, not as an error (AC-11)", async () => {
    const stats: QueueStats = {
      queue: "crawling",
      counts: { queued: 0, started: 0, finished: 0, failed: 0, deferred: 0, scheduled: 0 },
      failed_job_ids: [],
      workers_alive: 0,
    };
    vi.spyOn(queueStatsApi, "fetchQueueStats").mockResolvedValue(stats);

    renderPanel();

    expect(await screen.findByText("No worker running")).toBeInTheDocument();
    expect(screen.getByText("No failed jobs")).toBeInTheDocument();
    expect(screen.queryByText("Couldn't load queue stats")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows a scoped error alert when fetchQueueStats rejects", async () => {
    vi.spyOn(queueStatsApi, "fetchQueueStats").mockRejectedValue(
      new queueStatsApi.QueueStatsRequestError("boom"),
    );

    renderPanel();

    expect(await screen.findByText("Couldn't load queue stats")).toBeInTheDocument();
  });
});
