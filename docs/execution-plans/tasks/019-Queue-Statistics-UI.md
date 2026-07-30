queue is working now, we need build a UI for queue statistics

Clarified in conversation, since this is entirely new product surface
(no existing plan in `docs/product/vision.md`, which is empty, or any
other product doc):

- Placement: a stats panel added to the existing `JobsPage`
  (`frontend/src/pages/JobsPage.tsx`), above the current per-run jobs
  table — not a new standalone page/route.
- Data scope: per-queue counts (queued, started, finished, failed,
  deferred, scheduled), plus a list of failed job IDs so a stuck job is
  visible without leaving the page, plus worker liveness (is at least
  one `rq worker` process actually alive and processing this queue —
  catches the "nothing is consuming the queue" failure mode silently).
- Refresh behavior: auto-refresh via polling (TanStack Query
  `refetchInterval`, every 5-10s), not manual-refresh-only.

Context confirmed by investigation before this brief was written: RQ
2.10.0 (installed, Task 017) already exposes everything needed for
this without new infrastructure — `Queue.count`, the
`StartedJobRegistry`/`FinishedJobRegistry`/`FailedJobRegistry`/
`DeferredJobRegistry`/`ScheduledJobRegistry` classes (each with
`.count` and `.get_job_ids()`), and `rq.Worker.all(connection=...)` for
liveness/state. None of this is wired up anywhere today — no
queue-level (as opposed to per-run) endpoint exists in
`backend/app/modules/crawling/api/router.py` or any other router.
Only one queue exists today: `"crawling"` (per ADR 0004's
module-by-module rollout — discovery/extraction aren't queued yet).

`frontend/src/pages/JobsPage.tsx` currently shows only a per-run table
(one row per `CrawlRun`/`DiscoveryRun`/`ExtractionRun`, synthesized
client-side by `frontend/src/api/jobs.ts`'s `fetchPipelineJobs`) — no
aggregate/queue-level view exists anywhere in the frontend today.
