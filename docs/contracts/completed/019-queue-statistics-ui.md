# Feature Contract: Task 019 — Queue Statistics UI

Task brief: `docs/execution-plans/tasks/019-Queue-Statistics-UI.md`

Binding architectural precedent: `docs/decisions/0004-adopt-rq-as-queue-system.md` (Accepted) and `docs/contracts/completed/017-rq-crawling-vertical-slice.md` (the crawling module's RQ implementation — this contract reads live state out of the same `"crawling"` RQ queue/Redis instance that contract wired up; it adds no new queue infrastructure of its own).

Depends only on `backend/app/queue.py` (`get_queue`, `get_redis_connection`) and `backend/app/worker.py` already existing (Task 017, merged to main) and on `frontend/src/pages/JobsPage.tsx` / `frontend/src/api/jobs.ts` / `frontend/src/api/queries.ts` already existing (Task 012, merged to main).

---

# Feature

## Business Goal

Since Task 017, crawl runs execute on a background RQ worker instead of inline in the HTTP request. This is invisible from the outside once a queue exists: there is currently no way to see, from the product, whether jobs are piling up unprocessed, whether any jobs have failed, or whether an `rq worker` process is even running at all. A caller who forgets to start `python -m app.worker` (or whose worker process crashed) would see crawl runs sit in `queued` forever with zero signal anywhere in the UI. This feature adds a small, auto-refreshing statistics panel to the existing Jobs page so this failure mode — and ordinary queue health — is visible without SSH-ing into a box and running `redis-cli`.

## User Story

As an operator of this system (today: a developer running the stack locally; eventually: whoever is responsible for keeping the pipeline healthy), I want to see, at a glance, on the Jobs page, how many jobs are queued/running/finished/failed/deferred/scheduled for the crawling queue, which specific jobs have failed, and whether a worker process is actually alive and consuming the queue, refreshed automatically every few seconds, so that a stuck or unconsumed queue is obvious without leaving the page or inspecting Redis directly.

## Business Value

Closes the observability gap Task 017 opened: RQ adoption made crawl execution asynchronous and therefore invisible-by-default. This is the first UI built directly on top of ADR 0004's queue decision (as opposed to the queue's own enqueue/execute mechanics), and it is designed to generalize without rework once discovery and extraction adopt RQ in their own future contracts, per ADR 0004's module-by-module rollout — the same panel and the same backend endpoint serve any future queue name, not just `"crawling"`.

---

# Architecture Impact

## Affected domains

A new, small, flat-convention domain: `backend/app/domains/queue_stats/`. No existing domain or module (`domains/companies`, `modules/companies`, `modules/discovery`, `modules/crawling`, `modules/evidence`, `modules/extraction`) is modified.

## Affected services

None existing. `backend/app/domains/queue_stats/service.py` is new — pure, Redis-free computation only (see "Design Decision 1–3" below).

## Affected repositories

None. This feature reads directly from RQ's own Redis-backed constructs (`Queue`, `StartedJobRegistry`, `FinishedJobRegistry`, `FailedJobRegistry`, `DeferredJobRegistry`, `ScheduledJobRegistry`, `Worker`) via the already-existing `app.queue.get_queue` factory — no MongoDB collection, no new repository class, no new persisted document of any kind.

## Affected APIs

One new endpoint: `GET /api/queue-stats`. No existing endpoint changes.

## Affected database collections

None.

## Affected frontend pages

`frontend/src/pages/JobsPage.tsx` — gains a new `QueueStatsPanel` rendered above the existing jobs table. `frontend/src/pages/JobsPage.test.tsx` requires updating (not just additive changes) because every existing test renders `<JobsPage />`, which will now also call `fetchQueueStats` — see "Required Tests."

---

# Design Decisions (explicit — do not re-derive)

## Decision 1 — Where the endpoint lives

**New flat domain `backend/app/domains/queue_stats/`** (router.py, schemas.py, service.py — plus `__init__.py`, matching `backend/app/domains/health/__init__.py`'s precedent), registered in `backend/app/main.py` alongside `health_router`. **Not** added to `modules/crawling/api/router.py`.

Rationale:
- Per ADR 0004, RQ itself is a repository-wide decision, not owned by any one module. A stats endpoint bolted onto `modules/crawling/api/router.py` would need to be duplicated (or awkwardly parameterized in a module that has no reason to know about other modules' queues) the moment discovery or extraction also adopt RQ. A single endpoint accepting a `queue` query parameter — defaulting to `"crawling"` today, accepting any future queue name tomorrow with zero code change — is the generalizing design the task brief asks for.
- `backend/app/domains/health/router.py` is the direct, already-established precedent in this exact codebase for "a small, flat, non-hexagonal-module router for a cross-cutting, infrastructure-level concern that doesn't belong to any single business-entity module." Queue statistics are exactly this kind of concern: infrastructure introspection, not business logic owned by `crawling`.
- This endpoint's only dependency is `app.queue` (already a cross-cutting, non-module-owned file, sibling to `config.py`/`db.py`/`main.py`) — it needs nothing from `modules/crawling/**` at all, not even for reading `CrawlRun` status; it reads Redis/RQ state directly, which is a deliberate, narrower scope (see Out of Scope).

**Naming note:** the new package is named `queue_stats`, not `queue`, specifically to avoid any visual/import confusion with the already-existing `backend/app/queue.py` (the Redis/RQ connection factory this domain depends on). `backend/app/domains/queue_stats/` and `backend/app/queue.py` are unrelated Python namespaces (no actual import collision either way), but the distinct name removes any doubt at a glance.

## Decision 2 — Response shape

Exact Pydantic models, in `backend/app/domains/queue_stats/schemas.py` (flat-convention snake_case field names — matching `backend/app/domains/companies/models.py`'s existing precedent, *not* the hexagonal modules' camelCase-DTO convention, since this is a flat domain):

```python
from pydantic import BaseModel, Field


class QueueCounts(BaseModel):
    """Current job counts for one RQ queue, one field per RQ registry
    (plus the queue's own pending-job count). All non-negative; all zero
    is a normal, expected state (e.g. before any job has ever run), not
    an error.
    """

    queued: int = Field(ge=0)      # Queue.count — jobs waiting, not yet dequeued by a worker
    started: int = Field(ge=0)     # StartedJobRegistry(queue=...).count
    finished: int = Field(ge=0)    # FinishedJobRegistry(queue=...).count
    failed: int = Field(ge=0)      # FailedJobRegistry(queue=...).count
    deferred: int = Field(ge=0)    # DeferredJobRegistry(queue=...).count
    scheduled: int = Field(ge=0)   # ScheduledJobRegistry(queue=...).count


class QueueStatsResponse(BaseModel):
    """Response body for `GET /api/queue-stats`. A point-in-time snapshot
    only — no history, no time series (out of scope, see the task brief)."""

    queue: str
    counts: QueueCounts
    failed_job_ids: list[str]
    workers_alive: int = Field(ge=0)
```

**`failed_job_ids` cap: 50, enforced server-side** (`FAILED_JOB_ID_LIMIT = 50` constant in `service.py`) by requesting at most 50 ids from `FailedJobRegistry.get_job_ids(0, FAILED_JOB_ID_LIMIT - 1)` — never more are ever fetched from Redis, let alone returned. Rationale: RQ's `FailedJobRegistry` entries persist until their own TTL (`DEFAULT_FAILURE_TTL` = 31,536,000 seconds ≈ 1 year, confirmed by direct inspection of the installed `rq` package's `rq/defaults.py`) — nothing prunes this registry down to a small number on its own, so an uncapped read could return an arbitrarily large list under sustained polling every 5–10s. 50 is generous enough to reveal a real "jobs are stuck" backlog at a glance (the entire point of surfacing IDs here — spotting *that* something is stuck, not maintaining a full audit trail; a dedicated job-history/retry view is explicitly out of scope) while keeping the response small and cheap regardless of how long a broken worker has been failing jobs. **The client detects truncation itself** by comparing `counts.failed` (the true total, from `FailedJobRegistry.count`, uncapped) to `len(failed_job_ids)` — no separate `truncated: bool` field is added; this keeps the response model to exactly one job-list field, and the comparison is trivial for the frontend to make.

Job ordering within `failed_job_ids` is whatever RQ's own `get_job_ids()` default ordering returns (ascending by the registry's internal expiration score) — no additional sort is applied. This is acceptable specifically because this feature is a current-snapshot view, not a chronological audit log (explicitly out of scope, see below).

**`workers_alive: int`, not a list of worker summaries.** Computed as: the count of `rq.Worker.all(queue=rq_queue)` entries whose `get_state()` is **not** `WorkerStatus.SUSPENDED`. Two things this leans on, both confirmed by direct inspection of the installed `rq` package (`rq/worker/base.py`):
1. `Worker.all(queue=...)` only returns workers whose Redis registration key currently exists. That key is heartbeat-refreshed by a live worker and carries its own TTL (`DEFAULT_WORKER_TTL` = 420 seconds) — a crashed or killed worker process's key expires on its own within that window. This means "present in `Worker.all()`'s result" already encodes the liveness signal the task brief asks for ("alive," not merely "once existed") — no additional heartbeat-age check needs to be built or duplicated here.
2. A worker can be alive (heartbeating, present in the registry) but in `WorkerStatus.SUSPENDED` state — set when the whole RQ system has been suspended via `rq suspend`. A suspended worker is not consuming jobs even though its process is alive, which is exactly the "nothing is consuming the queue" failure mode this feature exists to catch — so suspended workers are deliberately excluded from `workers_alive`.

A plain `int` (not a list of `{hostname, pid, state}` worker summaries) is deliberately chosen: the task brief's own requirement is "is at least one worker alive and processing this queue," a liveness check, not a fleet-management/per-worker detail view — a richer worker roster is scope creep this contract does not build (see Out of Scope).

## Decision 3 — DI / composition

`backend/app/domains/queue_stats/router.py` defines its own small dependency, built on the already-existing `app.queue.get_queue` — **not** a copy of `modules/crawling/api/router.py`'s `get_crawl_queue`:

```python
from typing import Annotated
from fastapi import APIRouter, Depends, Query
from rq import Queue
from rq.registry import (
    DeferredJobRegistry, FailedJobRegistry, FinishedJobRegistry,
    ScheduledJobRegistry, StartedJobRegistry,
)
from rq.worker import Worker

from app.queue import get_queue
from app.domains.queue_stats.schemas import QueueCounts, QueueStatsResponse
from app.domains.queue_stats.service import build_queue_stats, summarize_worker_liveness

router = APIRouter(prefix="/api", tags=["queue-stats"])


def get_queue_by_name(queue: Annotated[str, Query()] = "crawling") -> Queue:
    """Resolve an RQ Queue by name from the `?queue=` query param, defaulting
    to "crawling" — the only queue this repository has adopted RQ for today
    (ADR 0004's module-by-module rollout). Generalizes to any future queue
    name (discovery, extraction, ...) with no change here."""
    return get_queue(queue)


@router.get("/queue-stats", response_model=QueueStatsResponse)
async def get_queue_stats(
    queue: Annotated[str, Query()] = "crawling",
    rq_queue: Queue = Depends(get_queue_by_name),
) -> QueueStatsResponse:
    counts = QueueCounts(
        queued=rq_queue.count,
        started=StartedJobRegistry(queue=rq_queue).count,
        finished=FinishedJobRegistry(queue=rq_queue).count,
        failed=FailedJobRegistry(queue=rq_queue).count,
        deferred=DeferredJobRegistry(queue=rq_queue).count,
        scheduled=ScheduledJobRegistry(queue=rq_queue).count,
    )
    failed_job_ids = FailedJobRegistry(queue=rq_queue).get_job_ids(0, FAILED_JOB_ID_LIMIT - 1)
    worker_states = [worker.get_state() for worker in Worker.all(queue=rq_queue)]
    return build_queue_stats(
        queue_name=queue,
        counts=counts,
        failed_job_ids=failed_job_ids,
        worker_states=worker_states,
    )
```

(`FAILED_JOB_ID_LIMIT` is imported from `service.py`, not redefined in `router.py`.)

Note the same query-string value (`?queue=...`) is read independently by both the route handler's own `queue: str` parameter and by `get_queue_by_name`'s `queue: str` parameter — this is standard, supported FastAPI behavior (multiple parameters, including a dependency's own parameters, may bind to the same query key) and is **not** a duplication bug; it is what lets the route handler echo the requested queue name back in the response body without needing `rq_queue` to carry it.

**No validation that `queue` is one of a fixed, known set of adopted queue names.** An unknown/never-used queue name (e.g. `?queue=discovery` today, before discovery adopts RQ) simply produces an all-zero, no-workers, empty-failed-ids response — a valid, harmless snapshot, not a 404 or a validation error. RQ's own `Queue`/registry constructors don't require a queue to have ever been used to be constructed or counted. This deliberately avoids introducing a second, endpoint-local "list of known queues" that would need to be kept in sync with `app/worker.py`'s `QUEUE_NAMES` every time a module adopts RQ — one less place to update per future rollout.

`backend/app/domains/queue_stats/service.py` — the pure, Redis-free half:

```python
FAILED_JOB_ID_LIMIT = 50


def summarize_worker_liveness(worker_states: list[str]) -> int:
    """Count workers whose RQ state is not 'suspended' — see the feature
    contract's Decision 2 for why suspended workers don't count as alive."""
    return sum(1 for state in worker_states if state != "suspended")


def build_queue_stats(
    *,
    queue_name: str,
    counts: QueueCounts,
    failed_job_ids: list[str],
    worker_states: list[str],
) -> QueueStatsResponse:
    return QueueStatsResponse(
        queue=queue_name,
        counts=counts,
        failed_job_ids=failed_job_ids[:FAILED_JOB_ID_LIMIT],
        workers_alive=summarize_worker_liveness(worker_states),
    )
```

`failed_job_ids[:FAILED_JOB_ID_LIMIT]` here is a defensive re-slice (the router already only ever requests `FAILED_JOB_ID_LIMIT` ids from Redis) — belt-and-suspenders so `build_queue_stats` alone is provably cap-respecting regardless of what its caller passes in, which is what makes it unit-testable as a standalone guarantee (see AC-04).

`backend/app/main.py` gains:
```python
from app.domains.queue_stats.router import router as queue_stats_router
...
app.include_router(queue_stats_router)
```

## Decision 4 — Frontend

**New files:**

1. `frontend/src/schemas/queueStats.ts` — Zod schema (snake_case fields, matching the backend's flat-domain response and `frontend/src/schemas/job.ts`'s own snake_case precedent):
   ```ts
   export const queueCountsSchema = z.object({
     queued: z.number().int().nonnegative(),
     started: z.number().int().nonnegative(),
     finished: z.number().int().nonnegative(),
     failed: z.number().int().nonnegative(),
     deferred: z.number().int().nonnegative(),
     scheduled: z.number().int().nonnegative(),
   });
   export type QueueCounts = z.infer<typeof queueCountsSchema>;

   export const queueStatsSchema = z.object({
     queue: z.string(),
     counts: queueCountsSchema,
     failed_job_ids: z.array(z.string()),
     workers_alive: z.number().int().nonnegative(),
   });
   export type QueueStats = z.infer<typeof queueStatsSchema>;
   ```

2. `frontend/src/api/queueStats.ts` — fetch client, matching `frontend/src/api/companies.ts`'s established shape (its own local `extractErrorMessage`/`FastApiErrorBody` helper, duplicated rather than shared — following this repository's existing per-client-file precedent, not introducing a new shared util):
   ```ts
   import { queueStatsSchema, type QueueStats } from "@/schemas/queueStats";

   const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

   export class QueueStatsRequestError extends Error {}

   export async function fetchQueueStats(queueName = "crawling"): Promise<QueueStats> {
     const response = await fetch(
       `${API_BASE_URL}/api/queue-stats?queue=${encodeURIComponent(queueName)}`,
     );
     if (!response.ok) {
       const body = await response.json().catch(() => ({}));
       throw new QueueStatsRequestError(
         (typeof body?.detail === "string" && body.detail) ||
           `GET /api/queue-stats?queue=${queueName} failed with ${response.status}`,
       );
     }
     return queueStatsSchema.parse(await response.json());
   }
   ```
   A Zod parse failure is allowed to propagate as-is (not wrapped in `QueueStatsRequestError`) — matching `companies.ts`'s own `companyListResponseSchema.parse(...)` call, which is likewise unwrapped. Either error type makes a TanStack Query hook's `isError` true, which is all `QueueStatsPanel` needs.

3. `useQueueStats` in `frontend/src/api/queries.ts`:
   ```ts
   export function useQueueStats(queueName = "crawling") {
     return useQuery({
       queryKey: ["queueStats", queueName],
       queryFn: () => fetchQueueStats(queueName),
       refetchInterval: 7000,
     });
   }
   ```
   **`refetchInterval: 7000` (7 seconds)** — the exact midpoint of the confirmed 5–10s range. Justification: RQ's `Queue.count`/registry `.count` calls are cheap Redis operations (a handful of `LLEN`/`ZCARD`-class commands), so request cost isn't the binding constraint on picking a value in the range; 7s is simply a reasonable, unremarkable middle point — close enough to real-time that a newly-stuck queue or a newly-dead worker surfaces within one page-glance, without polling at the aggressive end of the range for no added benefit.

4. `frontend/src/components/QueueStatsPanel.tsx` — new component, rendered by `JobsPage.tsx` above the existing `<Table>`. Built on `Card`/`CardHeader`/`CardTitle`/`CardContent` (`components/ui/card.tsx`), `Badge` (`components/ui/badge.tsx`) for failed-job-id chips, `StatusPill` (`components/status/StatusPill.tsx`) for the worker-liveness indicator, and `Alert`/`AlertTitle`/`AlertDescription` for the error state — all existing primitives, no new UI primitive is added.

   **Displays, in order:**
   - A small header: `Queue: {data.queue}`.
   - Six labeled counts (`Queued`, `Started`, `Finished`, `Failed`, `Deferred`, `Scheduled`) from `data.counts`, laid out as a simple flex/grid row of label+value pairs (no new chart/graph component).
   - A worker-liveness `StatusPill`: `tone="good"`, `pulse={true}`, label `"{n} worker(s) alive"` when `data.workers_alive >= 1`; `tone="warning"` (not `"critical"`), label `"No worker running"` when `data.workers_alive === 0`. **Explicit choice:** `"warning"`, not `"critical"`, even when `workers_alive === 0` — a worker simply not being started (e.g. local development) is not inherently a system failure the way a `critical` tone implies elsewhere in this codebase; it is however worth a visually distinct, attention-drawing tone from the neutral/good states, which `"warning"` provides. This is a fixed, deterministic mapping (not conditioned on `counts.queued`/`counts.started` — keeping the rule simple and testable, per this contract's own minimise-scope principle).
   - Up to **8** failed job IDs, each as a small `Badge`, in whatever order `data.failed_job_ids` arrives in (no client-side re-sort). If `data.counts.failed > 8`, append a plain text suffix `"+{data.counts.failed - 8} more"` — no expand/collapse control, no link to a detail view (display-only per the confirmed scope; retry/cancel/drill-down from this panel is explicitly out of scope). If `data.failed_job_ids.length === 0`, render `"No failed jobs"` instead of an empty badge row.

   **Loading state** (`isPending`): a small inline `Loader2` spinner + `"Loading queue stats…"` text — matching `JobsPage.tsx`'s own existing loading-row convention — rendered in place of the counts/pill/badges, not replacing the whole page.

   **Error state** (`isError`): a small `Alert variant="destructive"` with title `"Couldn't load queue stats"` — scoped to the panel only. This must **not** block or replace the jobs table below it (a separate `useQuery` call, a separate error boundary in effect) — if `fetchQueueStats` fails, `fetchPipelineJobs`/the jobs table render exactly as they do today.

   **Empty/zero state** (all counts 0, `workers_alive` 0 — e.g. a fresh environment where nothing has ever run and no worker has ever started): renders as the **normal** counts-and-pill layout described above (all counts render as `0`, the pill renders `"No worker running"` in its `"warning"` tone) — **not** the error `Alert`. This is a real, valid response from the backend (`isError` is `false`), so the component's existing `isPending`/`isError`/success branches already handle this correctly with no special-cased "empty" branch needed.

**`JobsPage.tsx` change:** import and render `<QueueStatsPanel />` directly above the existing `<Table aria-label="Pipeline jobs table">` (and above the filter `role="search"` bar, or below it — placed above the table as the task brief specifies; exact position relative to the filter bar is the implementer's choice, not specified further here since it doesn't affect any behavior this contract tests). No change to `useJobs`/`fetchPipelineJobs`/the filter controls/the table itself.

---

# Acceptance Criteria

**AC-01 — Default queue name, all-zero state renders as a normal response, not an error**
Given a fake `Queue`/registry/worker set producing zero counts, an empty failed-job list, and no workers, with no `?queue=` query param supplied
When `GET /api/queue-stats` is called
Then the response is `200` with `queue == "crawling"`, every field in `counts` equal to `0`, `failed_job_ids == []`, and `workers_alive == 0`
Verification: `pytest backend/tests/domains/queue_stats/test_router.py::test_queue_stats_defaults_to_crawling_and_handles_empty_state`

**AC-02 — An explicit, never-adopted `?queue=` name is accepted without error**
Given `?queue=discovery` (a queue name no module has adopted RQ for yet)
When `GET /api/queue-stats?queue=discovery` is called
Then the response is still `200`, with `queue == "discovery"` and the same all-zero-shaped response as AC-01 — no `404`, no validation error
Verification: `pytest backend/tests/domains/queue_stats/test_router.py::test_queue_stats_accepts_arbitrary_queue_name`

**AC-03 — Counts map 1:1 onto the six RQ sources**
Given a `QueueCounts` built from distinct, non-equal fake values for `queue.count`/each registry's `.count`
When `build_queue_stats` is called with those values
Then each field of the returned `QueueStatsResponse.counts` equals its corresponding distinct input value (proving no field is accidentally swapped or duplicated)
Verification: `pytest backend/tests/domains/queue_stats/test_service.py::test_build_queue_stats_maps_counts_without_swapping_fields`

**AC-04 — `failed_job_ids` is never longer than the cap, even if handed more**
Given `build_queue_stats` called with a `failed_job_ids` list longer than `FAILED_JOB_ID_LIMIT` (simulating a caller that ignored the router's own bounded `get_job_ids` call)
When the function returns
Then `len(response.failed_job_ids) == FAILED_JOB_ID_LIMIT`, and its content is the first `FAILED_JOB_ID_LIMIT` items of the input, unchanged in order
Verification: `pytest backend/tests/domains/queue_stats/test_service.py::test_failed_job_ids_never_exceeds_limit`

**AC-05 — Worker liveness excludes suspended workers**
Given `worker_states = ["idle", "busy", "suspended"]`
When `summarize_worker_liveness(worker_states)` is called
Then it returns `2`
Verification: `pytest backend/tests/domains/queue_stats/test_service.py::test_summarize_worker_liveness_excludes_suspended`

**AC-06 — Worker liveness with zero workers returns zero, not an error**
Given `worker_states = []`
When `summarize_worker_liveness(worker_states)` is called
Then it returns `0`
Verification: `pytest backend/tests/domains/queue_stats/test_service.py::test_summarize_worker_liveness_empty`

**AC-07 — The router requests at most `FAILED_JOB_ID_LIMIT` failed ids from RQ**
Given a fake `FailedJobRegistry`-like object recording the arguments it was called with
When `GET /api/queue-stats` is handled
Then `get_job_ids` was called with an `end` argument of exactly `FAILED_JOB_ID_LIMIT - 1` (proving the router itself bounds the Redis read, not just `build_queue_stats` after the fact)
Verification: `pytest backend/tests/domains/queue_stats/test_router.py::test_router_requests_bounded_failed_job_id_range`

**AC-08 — Frontend client parses a valid response and rejects with a typed error on non-2xx**
Given a mocked `fetch` resolving `200` with a body matching `queueStatsSchema`
When `fetchQueueStats()` is called
Then it resolves to the parsed `QueueStats` object
And, given a mocked `fetch` resolving with a non-2xx status
When `fetchQueueStats()` is called
Then it rejects with a `QueueStatsRequestError`
Verification: `pnpm --dir frontend run test src/api/queueStats.test.ts`

**AC-09 — `QueueStatsPanel` renders counts, worker pill, and failed-job badges from a successful fetch**
Given `fetchQueueStats` mocked to resolve with non-zero counts, `workers_alive: 1`, and 3 failed job ids
When `<QueueStatsPanel />` is rendered
Then all six count labels/values are visible, a `"1 worker(s) alive"` pill is visible, and all 3 failed job id badges are visible (no "+N more" text, since 3 ≤ 8)
Verification: `pnpm --dir frontend run test src/components/QueueStatsPanel.test.tsx`

**AC-10 — Truncated failed-job display**
Given `fetchQueueStats` mocked to resolve with `counts.failed: 12` and a `failed_job_ids` array of length 12
When `<QueueStatsPanel />` is rendered
Then exactly 8 badges are visible and the text `"+4 more"` is visible
Verification: `pnpm --dir frontend run test src/components/QueueStatsPanel.test.tsx`

**AC-11 — Zero-worker/zero-count response renders as normal, not as an error**
Given `fetchQueueStats` mocked to resolve with every count `0`, `workers_alive: 0`, `failed_job_ids: []`
When `<QueueStatsPanel />` is rendered
Then a `"No worker running"` pill and `"No failed jobs"` text are visible, and no destructive `Alert`/`"Couldn't load queue stats"` text is present
Verification: `pnpm --dir frontend run test src/components/QueueStatsPanel.test.tsx`

**AC-12 — Panel error does not block the jobs table**
Given `fetchQueueStats` mocked to reject, and `fetchPipelineJobs` mocked to resolve normally with at least one job
When `<JobsPage />` is rendered
Then `"Couldn't load queue stats"` is visible **and** the jobs table still renders the mocked job row(s) — neither query's failure affects the other
Verification: `pnpm --dir frontend run test src/pages/JobsPage.test.tsx`

**AC-13 — Existing `JobsPage` tests keep passing with `fetchQueueStats` mocked alongside `fetchPipelineJobs`**
Given the existing `JobsPage.test.tsx` suite, updated so every test that renders `<JobsPage />` also mocks `fetchQueueStats` (e.g. via a shared `beforeEach`/module-level mock resolving a normal all-zero-or-populated payload)
When the suite runs
Then every existing assertion (job rows, stage/status filters, empty state, error state) still passes
Verification: `pnpm --dir frontend run test src/pages/JobsPage.test.tsx`

---

# Required Tests

**Unit tests (pure, no Redis, no MongoDB)** — `backend/tests/domains/queue_stats/test_service.py`: `build_queue_stats` field-mapping and cap-enforcement (AC-03, AC-04), `summarize_worker_liveness` (AC-05, AC-06). These test plain Python functions with plain `int`/`str`/`list[str]` arguments — no RQ object is constructed, no Redis connection exists anywhere in this file.

**Router tests (FastAPI `TestClient`/`httpx.AsyncClient` against a locally-scoped `FastAPI()` app containing only `queue_stats_router` — no real Redis, following Task 017's own `FakeQueue`/`modules/imports`'s locally-scoped-app precedent, not the shared `app.main.app`)** — new file `backend/tests/domains/queue_stats/test_router.py`, with a local `conftest.py` providing:
- A `FakeQueue` (records nothing itself, just a placeholder object) overriding `get_queue_by_name` via `app.dependency_overrides`.
- `monkeypatch.setattr` on the five registry classes and `Worker` **as imported into `app.domains.queue_stats.router`** (not the `rq` package globally), each replaced with a small fake class/factory returning fixed `.count`/`.get_job_ids(start, end)` values and, for `Worker.all`, a fixed list of fake objects exposing only `.get_state()`.
Covers AC-01, AC-02, AC-07.

**Frontend unit tests (Vitest, mocked `fetch`)** — `frontend/src/api/queueStats.test.ts`, matching `frontend/src/api/companies.test.ts`'s existing style (mock global `fetch`, assert parse success / `QueueStatsRequestError` on non-2xx). Covers AC-08.

**Frontend component tests (Vitest + Testing Library, mocked API client via `vi.spyOn`, matching `JobsPage.test.tsx`'s established pattern — not MSW, no new mocking library introduced)** — `frontend/src/components/QueueStatsPanel.test.tsx` (AC-09, AC-10, AC-11) and an update to the existing `frontend/src/pages/JobsPage.test.tsx` (AC-12, AC-13).

**Real Redis + real `rq worker` end-to-end test: explicitly NOT required, waived — same rationale as Task 017's contract, reapplied here.** This feature reads live Redis state through RQ's own `Queue`/registry/`Worker` classes; proving those classes themselves correctly report counts/registry membership/heartbeat-derived liveness against a real Redis instance is RQ's own well-established, out-of-this-repository's-scope behavior (identical reasoning to Task 017's waiver for `enqueue_call`). What this contract's own logic needs proven — the six counts are wired to the correct six sources without being swapped (AC-03), the failed-id cap is enforced at both the service layer and the router's own bounded Redis read (AC-04, AC-07), and suspended workers are excluded from liveness (AC-05) — is fully covered by the unit/router tests above without a real Redis dependency. **Manual verification (recommended, not required):** with the shared `/srv/infra` Redis reachable, run `.venv/bin/python -m app.worker` in one terminal, enqueue a real crawl run, and poll `GET /api/queue-stats` (default `?queue=crawling`) across its `queued` → `started` → `finished` transitions, confirming the counts move as expected and `workers_alive` reads `1` while the worker process is up.

**Browser tests**: not applicable — no `tests/` (top-level, full-stack) coverage is in scope for this feature, consistent with every prior frontend-only or backend-only feature in this repository.

---

# Risks

**Technical risks**
- `Worker.all(queue=rq_queue)` derives its Redis connection from `rq_queue.connection` (confirmed by direct inspection of the installed `rq` package) — if `get_queue_by_name`'s underlying `app.queue.get_queue` ever changes to construct a `Queue` without a live connection, this silently breaks; not a risk this contract introduces, but worth the implementer double-checking against the exact installed `rq` version at build time (mirroring Task 017's own "verify against the actual installed `rq` version" caution).
- If Redis is unreachable when `GET /api/queue-stats` is called, RQ's own `Queue`/registry calls will raise a `redis.exceptions.ConnectionError`-family exception, which FastAPI will surface as an unhandled `500`. No explicit try/except-and-degrade-gracefully behavior is built for this — an unreachable Redis is a real infrastructure failure the caller should see, not one this panel should silently mask as "0 across the board" (which would look identical to a healthy, idle queue and actively hide the problem this feature exists to surface). This is an accepted, deliberate gap, not solved here.
- Polling every 7s against a real Redis instance from every open Jobs-page browser tab is cheap per the endpoint's own read cost, but this contract does not address multiple simultaneously open tabs/browsers compounding read load — not a realistic concern at this repository's current (single-operator, local-dev) scale, and out of scope to solve pre-emptively.

**Business risks**
- None beyond what ADR 0004 and Task 017 already accepted (unauthenticated, single-tenant, local-dev-infra Redis) — this feature only reads, never writes, so it introduces no new business-data risk.

**Performance risks**
- None new — six cheap Redis reads plus one bounded `ZRANGE`-class call and one `Worker.all` scan (bounded by however many `rq worker` processes actually exist, expected to be a handful at most), once per 7s per open tab.

**Security risks**
- None new — same shared, unauthenticated local Redis instance already used by Task 017, consistent with this repository's existing accepted no-auth-yet posture. `queue` is a free-text query parameter used only as an RQ Redis key-name component (`rq:queue:{name}`, `rq:registry:{name}`, etc.) — not used in any filesystem path, shell command, or database query string, so there is no injection surface beyond what RQ's own key-naming already accepts.

**Data integrity risks**
- None — this feature persists nothing. No MongoDB write path, no new collection, no new document.

---

# Dependencies

**External APIs:** None new.

**MongoDB:** None — this feature touches no collection.

**Redis:** Reuses the existing shared `/srv/infra` Redis instance and the existing `app.queue.get_queue`/`get_redis_connection` factory (Task 017) — no new connection logic, no new environment variable.

**Playwright:** Not used, unaffected.

**OpenAI:** Not used, unaffected.

**Environment variables:** None new — `REDIS_URL` already exists (Task 017).

**Required follow-up outside this task (report, do not build):**
1. Update CLAUDE.md's directory-layout listing under `backend/app/domains/` to include `queue_stats/`, and under `frontend/src/` to include `api/queueStats.ts`, `schemas/queueStats.ts`, and `components/QueueStatsPanel.tsx` — a routine content-accuracy edit, not a rule/instruction change.
2. When discovery or extraction adopt RQ (their own future contracts, per ADR 0004), no change to this feature's backend or frontend code is anticipated — `?queue=discovery`/`?queue=extraction` already work today per AC-02's design; the only follow-up would be the frontend optionally offering a queue-selector control if multiple queues become worth surfacing simultaneously, which is explicitly not built here (see Out of Scope).

---

# Out of Scope

- Discovery/extraction queue stats as a *populated* view — the endpoint already generalizes to any queue name (AC-02), but only `"crawling"` has any real jobs to show today; no frontend queue-selector UI is built (`QueueStatsPanel` hardcodes `"crawling"` as its default/only queue for now).
- Any historical or time-series view of queue depth/failure counts over time — this is a current-snapshot-only feature; no new MongoDB collection, no charting library, no persistence of past snapshots.
- Any ability to retry, cancel, requeue, or otherwise act on a failed job from this panel — strictly display-only, per the confirmed scope. (Retry/cancel already exist as separate, unrelated endpoints on `modules/crawling/api/router.py` — this feature does not link to or wire into them.)
- A full per-worker roster (hostnames, PIDs, current job, uptime) — only an aggregate `workers_alive` count is returned; see Decision 2's rationale.
- Any new shared "list of known queues" registry/allow-list — deliberately avoided (see Decision 3) in favor of accepting any `queue` value permissively.
- Authentication/authorization on the new endpoint — consistent with this repository's existing no-auth-yet posture.
- A real Redis/`rq worker`-backed end-to-end automated test — explicitly waived, see Required Tests.
- Any change to `backend/app/queue.py` or `backend/app/worker.py` — both are reused exactly as Task 017 left them; no new field, no new function.

---

# Suggested Implementation Order

1. `backend/app/domains/queue_stats/__init__.py`, `schemas.py` — `QueueCounts`/`QueueStatsResponse`.
2. `backend/app/domains/queue_stats/service.py` — `FAILED_JOB_ID_LIMIT`, `build_queue_stats`, `summarize_worker_liveness`. Independently unit-testable immediately (AC-03 through AC-06) — no router/Redis dependency yet.
3. `backend/tests/domains/queue_stats/__init__.py` + `test_service.py` — write and pass AC-03–AC-06 before touching the router.
4. `backend/app/domains/queue_stats/router.py` — `get_queue_by_name`, `get_queue_stats`.
5. `backend/app/main.py` — register `queue_stats_router`.
6. `backend/tests/domains/queue_stats/conftest.py` + `test_router.py` — fakes/monkeypatches for the five registries + `Worker`, AC-01, AC-02, AC-07.
7. `frontend/src/schemas/queueStats.ts`.
8. `frontend/src/api/queueStats.ts` + `frontend/src/api/queueStats.test.ts` — AC-08.
9. `frontend/src/api/queries.ts` — add `useQueueStats`.
10. `frontend/src/components/QueueStatsPanel.tsx` + `QueueStatsPanel.test.tsx` — AC-09, AC-10, AC-11.
11. `frontend/src/pages/JobsPage.tsx` — render `<QueueStatsPanel />` above the table.
12. `frontend/src/pages/JobsPage.test.tsx` — update every existing test to also mock `fetchQueueStats`; add AC-12's cross-panel-independence test.
13. Full local verification: `pytest backend/tests/domains/queue_stats`, `pnpm --dir frontend run test`, `ruff check`, `pyright` on all new/changed backend paths, frontend `tsc`/lint per its existing scripts.
14. Manual smoke test (recommended, not required — see Required Tests) against a real Redis + `rq worker` + a real crawl run, confirming counts and `workers_alive` move as expected while polling.
15. Final report: files created/changed, the exact `refetchInterval` value chosen and why, the `FAILED_JOB_ID_LIMIT` value chosen and why, confirmation that AC-01 through AC-13 pass, and the "Required follow-up" list above.

---

# Success Criteria

This feature is complete only when:

✓ AC-01 through AC-13 all pass

✓ Every test file listed under "Required Tests" exists and passes, including `frontend/src/pages/JobsPage.test.tsx`'s pre-existing assertions continuing to pass once updated to mock `fetchQueueStats` alongside `fetchPipelineJobs`

✓ `git diff --stat` touches only: `backend/app/domains/queue_stats/**` (new), `backend/app/main.py`, `backend/tests/domains/queue_stats/**` (new), `frontend/src/schemas/queueStats.ts` (new), `frontend/src/api/queueStats.ts` (new) + its test, `frontend/src/api/queries.ts`, `frontend/src/components/QueueStatsPanel.tsx` (new) + its test, `frontend/src/pages/JobsPage.tsx`, `frontend/src/pages/JobsPage.test.tsx` — no other module/domain/page is touched

✓ `ruff check` and `pyright` are clean on every new/changed backend path; the frontend's existing lint/type-check scripts are clean on every new/changed frontend path

✓ The "Required follow-up" list is reported, not silently built or silently omitted

✓ Evaluator reports PASS
