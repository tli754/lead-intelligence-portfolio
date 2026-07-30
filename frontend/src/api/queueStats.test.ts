import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchQueueStats, QueueStatsRequestError } from "./queueStats";

function validBody() {
  return {
    queue: "crawling",
    counts: {
      queued: 2,
      started: 1,
      finished: 10,
      failed: 0,
      deferred: 0,
      scheduled: 0,
    },
    failed_job_ids: [],
    workers_alive: 1,
  };
}

describe("fetchQueueStats", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function stubFetch(response: Response) {
    const fetchMock = vi.fn().mockResolvedValue(response);
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  it("resolves the parsed QueueStats object on a successful response", async () => {
    stubFetch(new Response(JSON.stringify(validBody()), { status: 200 }));

    const result = await fetchQueueStats();

    expect(result).toEqual(validBody());
  });

  it("requests the default 'crawling' queue when no queue name is passed", async () => {
    const fetchMock = stubFetch(new Response(JSON.stringify(validBody()), { status: 200 }));

    await fetchQueueStats();

    const requestedUrl = fetchMock.mock.calls[0][0] as string;
    expect(requestedUrl).toContain("/api/queue-stats?queue=crawling");
  });

  it("rejects with QueueStatsRequestError on a non-2xx response", async () => {
    const errorBody = JSON.stringify({ detail: "boom" });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() => Promise.resolve(new Response(errorBody, { status: 500 }))),
    );

    await expect(fetchQueueStats()).rejects.toThrow(QueueStatsRequestError);
    await expect(fetchQueueStats()).rejects.toThrow("boom");
  });
});
