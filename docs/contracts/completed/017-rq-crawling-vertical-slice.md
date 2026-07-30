# Feature Contract: Task 017 — Adopt RQ for the crawling module (vertical slice)

Task brief: `docs/execution-plans/tasks/017-Adopt-RQ-Queue-Crawling-Vertical-Slice.md`

Binding architectural precedent: `docs/decisions/0004-adopt-rq-as-queue-system.md`
(Accepted). That ADR authorizes RQ + Redis generally, chooses crawling
as the first module to adopt it, and explicitly reserves this
contract for the crawling-specific design. This contract does not
re-argue RQ-vs-Celery or Redis sourcing — see the ADR for that.

Depends only on `backend/app/modules/crawling/**` already existing
(Task 006, `docs/contracts/completed/crawling-module.md`) and being
registered in `backend/app/main.py` (already true — confirmed by
direct inspection, not a required follow-up here).

# Feature

## Business Goal

`POST /api/companies/{company_id}/crawl-runs` today runs an entire
crawl (potentially dozens of sequential, rate-limited, real network
fetches — the crawling module's own contract documents a 30-target
run taking "at least ~30 seconds," with no fixed upper bound) inline
inside the HTTP request/response cycle. A caller's connection must
stay open for the full duration, the API process is occupied for
that entire time, and a client that times out or disconnects has no
way to learn the run's outcome. This feature moves crawl execution
onto a background worker via RQ, so the create-crawl-run endpoint
returns immediately with a `queued` run the caller can poll, while a
separate worker process does the actual fetching.

## User Story

As a caller of the crawling API (today: a human hitting the API
directly or via future frontend wiring; eventually: an orchestrating
pipeline), I want `POST .../crawl-runs` to return immediately with a
trackable `queued` run, and the actual crawling to happen on a
background worker, so that starting a crawl is a fast, reliable
operation regardless of how long the underlying crawl takes.

## Business Value

First real application of ADR 0004's queue decision — validates the
RQ pattern end-to-end (enqueue at the API layer, execute in a
separate worker process, against the exact same application-service
code the synchronous path already used) on the one pipeline stage
with the clearest, already-documented need for it. Establishes the
concrete pattern (queue connection factory, worker entrypoint, job
wrapper functions) that discovery and extraction can each follow in
their own future contracts, per ADR 0004's module-by-module rollout.

---

# Architecture Impact

## Affected domains

`backend/app/modules/crawling/` only. No other module's `domain/`,
`application/`, `infrastructure/`, or `api/` directory changes.

## Affected services

`WebsiteCrawlService`
(`backend/app/modules/crawling/application/website_crawl_service.py`)
is restructured, not rewritten: today's `start_crawl_run` is split
into two methods so the "validate + create the run record" half can
run synchronously in the API request while the "actually process
targets" half can run later, on a worker, given nothing but the
`crawl_run_id`. See "Application service changes" below for the exact
split. `retry_failed` gains a small companion method for the same
reason. No change to `WebsiteDiscoveryService`, `StructuredExtractionService`,
`CompanyService`, or any other module's service.

## Affected repositories

No new method. `CrawlRepository`'s existing interface (`create_run`,
`update_run`, `get_run`, `find_active_run`, `mark_run_cancelled`, plus
the target/page methods) already has everything the new split needs —
confirmed by direct inspection of
`backend/app/modules/crawling/domain/repository.py`. The RQ job id
used for a given run is derived deterministically from `crawl_run_id`
(see "Job identity" below) rather than persisted as a new field.

**Amendment (post-evaluation):** one new field on `CrawlRun` proved
necessary and was added: `options_snapshot: dict`. The original design
above assumed `configuration_snapshot` (a `CrawlConfig` dump, already
persisted at enqueue time) captured everything `execute_crawl_run`
would need to recover from `crawl_run_id` alone. That premise was
wrong: `_build_effective_config` only folds `max_pages`/`browser_policy`
into `configuration_snapshot` — it never captured `force_refresh`,
`include_page_types`, `exclude_page_types`, or `manual_urls`, which
live only on the caller-supplied `CrawlRunOptions` passed to
`enqueue_crawl_run`. Without persisting them, `execute_crawl_run` had
no way to reconstruct the caller's actual options and silently fell
back to defaults — a real regression an evaluation pass caught and
reproduced. The fix: `enqueue_crawl_run` now also persists
`options_snapshot=options.model_dump(mode="json")`; `execute_crawl_run`
reconstructs `options = CrawlRunOptions.model_validate(run.options_snapshot)`
instead of hardcoding `CrawlRunOptions()`. `docs/architecture/mongodb-design.md`'s
`crawl_runs` schema listing was updated accordingly — see "Out of
Scope" below, also amended.

## Affected APIs

`POST /api/companies/{company_id}/crawl-runs`,
`POST /api/crawl-runs/{crawl_run_id}/cancel`, and
`POST /api/crawl-runs/{crawl_run_id}/retry-failed` change behavior
(enqueue instead of/in addition to inline execution — see
"Router changes"). Every GET endpoint
(`.../crawl-runs/latest`, `/api/crawl-runs/{id}`, `.../targets`,
`.../pages`, `/api/pages/{id}`, `GET /api/crawl-runs`) is unchanged —
they already read whatever `CrawlRun.status` currently is
(`queued`/`running`/terminal), and that enum already includes
`queued` today, so no response-schema change is needed anywhere.

## Affected database collections

None. Same three collections (`crawl_runs`, `crawl_targets`, `pages`),
same documents, same indexes. `CrawlRun.status` will now spend real
wall-clock time as `queued` (previously it transitioned from `queued`
to `running` inside a single inline call, so `queued` was visible only
for a database round trip), which is exactly what the enum already
models — no migration needed.

## Affected frontend pages

None directly. `frontend/src/pages/JobsPage.tsx`'s existing
`queued -> queued` status mapping (Task 012's mapping table,
`docs/contracts/completed/wire-jobs-page-to-pipeline-runs.md`) already
handles a `CrawlRun` sitting in `queued` for longer than before —
no frontend code or test changes are required or in scope for this
contract. See "Out of Scope" for the one documentation staleness this
creates.

---

# Cross-module dependency decisions

None needed. This task adds no new gateway, no new port, and touches
no other module's `domain/`/`application/`/`infrastructure/`. The one
new piece of infrastructure this task needs — a Redis connection/queue
accessor — is deliberately placed *outside* `modules/crawling/`
entirely (see "New shared infrastructure" below), exactly mirroring
how `app/db.py` is a single, cross-cutting Motor-client factory that
every module's own `infrastructure/mongo_*_repository.py` depends on,
never the reverse.

---

# New shared infrastructure (outside `modules/crawling/`, in scope for this task)

## `backend/app/config.py`

Add one field to `Settings`:

```python
REDIS_URL: str = "redis://localhost:6379/0"
```

Matches `MONGODB_URI`'s existing pattern exactly (a plain string field
with a working local default, read once via `get_settings()`). Add a
corresponding documented line to `.env.example`, matching
`MONGODB_URI`'s existing comment style.

## `backend/app/queue.py` (new file)

A small, cross-cutting module, sibling to `config.py`/`db.py`/
`main.py` — not under any `modules/` directory, because ADR 0004
frames RQ as a repository-wide decision, and this factory must be
reusable by discovery/extraction's own future contracts without
importing across module boundaries. Mirrors `db.py`'s exact shape
(one cached connection factory, one thin per-queue accessor):

```python
from functools import lru_cache
from redis import Redis
from rq import Queue
from app.config import get_settings

@lru_cache
def get_redis_connection() -> Redis:
    """Return the process-wide Redis connection, creating it on first use."""
    settings = get_settings()
    return Redis.from_url(settings.REDIS_URL)

def get_queue(name: str) -> Queue:
    """Return an RQ Queue bound to the shared Redis connection."""
    return Queue(name, connection=get_redis_connection())
```

`get_redis_connection` is process-wide-cached the same way
`get_client()` is in `db.py`; `get_queue` itself is cheap and
uncached (constructing an RQ `Queue` object is inexpensive — the real
resource is the connection). This file has **zero** knowledge of
crawling, discovery, or extraction — it is pure queue infrastructure,
exactly as `db.py` has zero knowledge of any collection name.

## `backend/app/worker.py` (new file)

A thin, directly-runnable worker entrypoint, sibling to `main.py`
(the uvicorn entrypoint already documented in `README.md`). Lists
every queue name any module currently uses — today, just `"crawling"`
— so a single worker process can serve all adopted modules; future
per-module contracts add their own queue name to this same list
rather than each spinning up a separate worker script:

```python
"""RQ worker entrypoint. Run with:
    .venv/bin/python -m app.worker
Processes jobs for every queue this repository has adopted RQ for.
Crawling is first (Task 017); add a queue name here when discovery or
extraction adopt RQ per ADR 0004 — one queue name per module, added to
this same list, not a second worker script.
"""
from rq import Worker
from app.queue import get_redis_connection

QUEUE_NAMES = ["crawling"]

if __name__ == "__main__":
    Worker(QUEUE_NAMES, connection=get_redis_connection()).work()
```

## `pyproject.toml`

Add to `[project] dependencies`:
```
"redis>=5.0",
"rq>=1.16",
```
Both listed explicitly (not `rq` alone) since `app/queue.py` calls
`redis.Redis.from_url` directly, not merely transitively through
`rq`. No `dev` dependency changes needed — RQ's own test doubles are
not required (see "Required Tests").

## `docker-compose.yml` / root `.gitignore`

Not changed. Per ADR 0004, Redis connectivity reuses the shared
`/srv/infra` stack — no new compose service.

---

# Crawling-module changes

## Current behavior (confirmed by direct inspection)

`WebsiteCrawlService.start_crawl_run(company_id, discovery_run_id, options)`
today, in one call: computes the idempotency key; checks
`find_active_run` (raises `DuplicateActiveCrawlRunError` on conflict);
validates the discovery run exists via `discovery_gateway.get_discovery_run`
(raises `DiscoveryRunNotFoundForCrawlError`); advances company
`processing.status` to `CRAWLING` (best-effort); creates and persists
a `CrawlRun` (`status` defaults to `CrawlStatus.QUEUED`); immediately
flips it to `RUNNING`; selects and persists targets; runs every target
sequentially; computes final summary/status; advances company status
to `CRAWLED`/`FAILED`; calls the (documented no-op)
`update_latest_crawl_run`; returns the completed run.
`api/router.py`'s `create_crawl_run` route awaits this entire chain
inline before responding.

`cancel_run(crawl_run_id)` unconditionally sets `CrawlRun.status` to
`cancelled` in MongoDB (`mark_run_cancelled` has no transition-validity
check) — the *running* execution loop cooperatively checks this
between targets and stops scheduling new ones, but does not undo
already-completed work.

`retry_failed(crawl_run_id)` loads the existing (terminal-status) run,
re-processes only its currently-failed/rejected(/optionally
blocked-by-robots) targets in place, and recomputes the run's final
status — all synchronously inline, called directly by
`retry_failed_targets`'s route handler today.

## Application service changes (`website_crawl_service.py`)

Split `start_crawl_run` into two methods along the exact seam already
present in its own code (the moment the `CrawlRun` document is first
created and persisted):

1. **`async def enqueue_crawl_run(self, company_id: str, discovery_run_id: str, options: CrawlRunOptions | None = None) -> CrawlRun`**
   — everything `start_crawl_run` does *before* target processing
   starts, ending right after the run is first persisted:
   idempotency-key computation, `find_active_run` duplicate check
   (raises `DuplicateActiveCrawlRunError`), discovery-run-existence
   validation (raises `DiscoveryRunNotFoundForCrawlError`), building
   and persisting the `CrawlRun` record. **Decision:** company
   `processing.status` is **not** advanced to `CRAWLING` here — that
   now happens in `execute_crawl_run`, once execution actually starts
   (see rationale below). Returns the persisted run, still in its
   default `CrawlStatus.QUEUED` state, with no targets selected and no
   fetch ever attempted. This method performs no real-website network
   I/O — its only I/O is the discovery-run existence check (a Mongo/
   gateway read) and the run's own persistence — so it is safe and fast
   to run synchronously inside the HTTP request, exactly the reasoning
   ADR 0003 already established for why *this* kind of fast, bounded
   check belongs in the synchronous path while the slow part does not.

2. **`async def execute_crawl_run(self, crawl_run_id: str) -> CrawlRun`**
   — everything `start_crawl_run` did *after* run creation, unchanged
   in substance, just re-anchored on a `crawl_run_id` looked up fresh
   from the repository instead of an in-memory `run` object carried
   over from creation: `run = await self._repository.get_run(crawl_run_id)`,
   raising `CrawlRunNotFoundError` if missing. **New guard, first
   thing in the method:** if `run.status == CrawlStatus.CANCELLED`,
   return `run` immediately, unchanged — no company-status advance, no
   target selection, no fetch. This handles the race where `cancel_run`
   is called after `enqueue_crawl_run` but before the worker actually
   picks the job up (see "Cancel semantics" below). Otherwise:
   advance company `processing.status` to `CRAWLING` (best-effort,
   same swallow-`InvalidStatusTransitionError` pattern as today), set
   `run.status = RUNNING`/`started_at`, persist, select and persist
   targets, run every target (`_run_targets`, unchanged), compute
   final summary/status, persist, advance company status to
   `CRAWLED`/`FAILED` (best-effort, unchanged), call
   `update_latest_crawl_run` (still the documented no-op from Task 006 —
   unchanged, not part of this task's scope to resolve), return the
   completed run.

   **Why advance to `CRAWLING` here, not in `enqueue_crawl_run`:**
   `processing.status == CRAWLING` should mean "actively being
   crawled," not "sitting in a Redis queue behind other jobs" — the
   whole point of introducing an observable `queued` state was to
   distinguish those two. Moving the status-advance here keeps that
   distinction meaningful instead of collapsing it back to "queued
   looks the same as running" from the company's point of view.

3. **`async def start_crawl_run(self, company_id: str, discovery_run_id: str, options: CrawlRunOptions | None = None) -> CrawlRun`**
   — **kept**, not deleted, as a thin composed convenience:
   ```python
   run = await self.enqueue_crawl_run(company_id, discovery_run_id, options)
   return await self.execute_crawl_run(run.crawl_run_id)
   ```
   This is a deliberate compatibility decision: the crawling module's
   own existing integration-test suite
   (`backend/tests/integration/crawling/test_website_crawl_service.py`,
   ~30 scenarios per `docs/contracts/completed/crawling-module.md`'s
   AC-01 through AC-36) calls `start_crawl_run` directly and asserts
   on its fully-completed return value. Preserving this method,
   unchanged in its external contract, means that entire existing
   suite keeps passing **unmodified** — only new tests are added for
   the new split (see "Required Tests"). It also leaves a synchronous,
   non-queue code path available for local development without a
   running Redis/worker. Do not remove it; do not have the router call
   it going forward.

4. **`async def enqueue_retry(self, crawl_run_id: str) -> CrawlRun`** —
   new, small method: `run = await self._repository.get_run(crawl_run_id)`,
   raising `CrawlRunNotFoundError` if missing; set `run.status = CrawlStatus.QUEUED`;
   persist via the existing `update_run` (its `document_version`
   optimistic-concurrency bump applies unchanged); return the
   persisted (now `queued`) run immediately. The actual retry logic —
   `retry_failed(crawl_run_id)` — is **unchanged**; it is now invoked
   by the worker instead of inline by the router.

## Router changes (`api/router.py`)

Add one new DI accessor:

```python
def get_crawl_queue() -> Queue:
    return get_queue("crawling")
```
(`Queue` and `get_queue` imported from `app.queue` — the router layer
already imports concrete infrastructure directly in its other `get_*`
functions today, e.g. `get_crawl_repository` returns `MongoCrawlRepository`
directly and `get_page_fetcher` returns `HttpxPageFetcher` directly, so
this is consistent with, not a deviation from, this file's existing
convention. No new port/gateway is introduced for the queue.)

**`POST /api/companies/{company_id}/crawl-runs`** (`create_crawl_run`):
replace the current `await service.start_crawl_run(...)` call with:
```python
run = await service.enqueue_crawl_run(
    company_id, request.discovery_run_id, request.options_or_default()
)
queue.enqueue_call(
    func=run_crawl_execution,   # see "Job wrapper functions" below
    args=(run.crawl_run_id,),
    job_id=run.crawl_run_id,
    timeout=CRAWL_JOB_TIMEOUT,  # see "Job timeout" below — must not be RQ's 180s default
)
return CrawlRunEnvelope(data=run_to_response(run))
```
Exception handling for `CompanyNotFoundForCrawlError`/
`DiscoveryRunNotFoundForCrawlError`/`DuplicateActiveCrawlRunError` is
unchanged (`enqueue_crawl_run` raises the same set
`start_crawl_run` used to raise for that half of the work). Response
status/shape unchanged (`201`, `CrawlRunEnvelope`) — the returned
run's `status` will now read `"queued"` instead of whatever the
inline run eventually finished as; this is the intended, documented
behavior change.

**Job timeout — explicit decision, not left to the generator to
guess:** RQ's default job timeout is 180 seconds. The crawling
module's own contract documents runs taking well over that for
non-trivial target counts, with no fixed upper bound on
`max_pages_per_company`. `CRAWL_JOB_TIMEOUT` must be set generously —
a module-level constant in `infrastructure/rq_jobs.py` (see below),
e.g. `CRAWL_JOB_TIMEOUT = "1h"` (RQ's string duration syntax) — not
left at RQ's default. Document this constant's rationale in a
one-line comment at its definition.

**Job identity — explicit decision:** the RQ job for a fresh crawl
uses `job_id=run.crawl_run_id` directly — `crawl_run_id` is a
freshly-generated UUID per new `CrawlRun`, so no collision is
possible for a create. This also means "the queued job for this run,
if it hasn't started yet" can always be looked up later by
`Job.fetch(crawl_run_id, connection=...)` without persisting any new
field.

**`POST /api/crawl-runs/{crawl_run_id}/retry-failed`** (`retry_failed_targets`):
replace the current `await service.retry_failed(crawl_run_id)` call
with:
```python
run = await service.enqueue_retry(crawl_run_id)
queue.enqueue_call(
    func=run_crawl_retry,
    args=(crawl_run_id,),
    job_id=f"{crawl_run_id}-retry",
    timeout=CRAWL_JOB_TIMEOUT,
)
return CrawlRunEnvelope(data=run_to_response(run))
```
Exception handling for `CrawlRunNotFoundError` is unchanged.
**Decision, explicit:** the retry job uses a distinct id
(`f"{crawl_run_id}-retry"`), not the same `crawl_run_id` as the
original create job, because `retry_failed_targets` can only ever be
called once the run has already reached a terminal status — meaning
the original create job has already finished and its job id may still
be present in RQ's finished-job registry; reusing the exact same id
risks an RQ conflict this contract does not need to resolve when a
distinct, equally-lookupable id avoids the question entirely. If a
second retry is requested while the first retry job is still
queued/running, that is a genuine duplicate-request race this task
does not attempt to prevent at the queue layer — see Risks.

**`POST /api/crawl-runs/{crawl_run_id}/cancel`** (`cancel_crawl_run`):
domain call to `service.cancel_run(crawl_run_id)` is **unchanged**
(still unconditionally marks the Mongo document `cancelled`). Add,
immediately after, a best-effort attempt to cancel whichever RQ job
(if any) is still queued for this run — try both possible ids,
swallowing "no such job" for whichever doesn't currently exist:
```python
from rq.job import Job
from rq.exceptions import NoSuchJobError
for candidate_job_id in (crawl_run_id, f"{crawl_run_id}-retry"):
    try:
        Job.fetch(candidate_job_id, connection=get_redis_connection()).cancel()
    except NoSuchJobError:
        pass
```
This is deliberately **best-effort and non-blocking to the response** —
any RQ/Redis error here is logged, never raised to the caller, and
never changes the HTTP status code returned. **Documented, explicit
limitation:** RQ can only cleanly cancel a job while it is still
queued and has not yet been picked up by a worker. Once a worker has
started executing `run_crawl_execution`/`run_crawl_retry`, calling
`.cancel()` on it does **not** stop the in-progress Python code — what
actually stops it is `execute_crawl_run`'s own cooperative
cancellation check between targets (unchanged from today's
`_run_targets` behavior) plus the new "return early if already
`CANCELLED`" guard at the top of `execute_crawl_run`. Both mechanisms
are complementary, not redundant: `.cancel()` prevents a not-yet-started
job from ever running at all (cheap, correct, immediate); the
in-loop check stops an already-running job as soon as it next
checks (same latency characteristics as today, unchanged).

## Job wrapper functions — `backend/app/modules/crawling/infrastructure/rq_jobs.py` (new file)

RQ workers call a plain Python callable, synchronously, outside any
FastAPI request and outside any existing asyncio event loop by
default. `WebsiteCrawlService.execute_crawl_run`/`retry_failed` are
`async def` methods built from the same DI composition
`api/router.py`'s `get_crawl_service()` already assembles. This file
is the concrete adapter that reassembles that exact same composition
manually (calling the *existing*, already-public DI functions
directly with an explicit `database` argument — `Depends(...)` default
values are simply ignored when a parameter is passed explicitly, so
no new composition code is duplicated) and bridges sync-to-async via
`asyncio.run`:

```python
"""RQ job entrypoints for the crawling module. Called by `app.worker`'s
worker process, never by a FastAPI request. Builds the same dependency
composition `api/router.py`'s `get_crawl_service()` assembles for a
request, but manually — RQ workers run outside FastAPI's request-scoped
DI and outside any existing asyncio event loop.
"""
import asyncio
from app.db import get_database
from app.modules.crawling.api.router import (
    get_company_crawl_gateway, get_content_storage, get_crawl_repository,
    get_discovery_crawl_gateway, get_page_fetcher, get_robots_policy_gateway,
)
from app.modules.crawling.application.website_crawl_service import WebsiteCrawlService
from app.modules.crawling.domain.config import CrawlConfig
from app.modules.companies.api.router import get_company_service
from app.modules.discovery.api.router import get_discovery_repository

CRAWL_JOB_TIMEOUT = "1h"  # RQ's 180s default is far too short for a
                           # multi-target crawl run — see the feature
                           # contract's "Job timeout" section.

def _build_service() -> WebsiteCrawlService:
    database = get_database()
    company_service = get_company_service(database=database)
    discovery_repository = get_discovery_repository(database=database)
    page_fetcher = get_page_fetcher()
    return WebsiteCrawlService(
        company_gateway=get_company_crawl_gateway(company_service=company_service),
        discovery_gateway=get_discovery_crawl_gateway(discovery_repository=discovery_repository),
        robots_gateway=get_robots_policy_gateway(page_fetcher=page_fetcher),
        repository=get_crawl_repository(database=database),
        page_fetcher=page_fetcher,
        content_storage=get_content_storage(),
        config=CrawlConfig(),
    )

def run_crawl_execution(crawl_run_id: str) -> None:
    asyncio.run(_build_service().execute_crawl_run(crawl_run_id))

def run_crawl_retry(crawl_run_id: str) -> None:
    asyncio.run(_build_service().retry_failed(crawl_run_id))
```

(The exact parameter names on each `get_*` DI function must be checked
against `api/router.py`'s current signatures at implementation time —
reproduced above from direct inspection, but if any DI function's
default-`Depends()` chain doesn't allow calling it this way with a
single explicit override, this file's job is to make that composition
work, not to change `api/router.py`'s own DI functions.)

**`asyncio.run` per job, not a persistent event loop, is a deliberate,
sufficient choice for this vertical slice:** RQ's default worker model
processes one job to completion before dequeuing the next — this
already matches the crawling module's own mandated "concurrency per
company = 1, no distributed/parallel fetching" design (per
`docs/contracts/completed/crawling-module.md`). A fresh `asyncio.run`
per job introduces no correctness gap and no meaningful overhead
relative to a run's own multi-second-to-multi-minute duration.

---

# Acceptance Criteria

**AC-01 — `POST .../crawl-runs` returns immediately without executing the crawl**
Given a valid company and discovery run
When `POST /api/companies/{company_id}/crawl-runs` is called
Then the response is `201` with `data.status == "queued"`, and the
underlying `WebsiteCrawlService.execute_crawl_run` is never invoked
synchronously within the request (verified via a fake `PageFetcher`
that would record/raise if ever called, asserted un-called after the
response returns)
Verification: `pytest backend/tests/integration/crawling/test_router_rq_enqueue.py::test_create_crawl_run_returns_queued_without_executing`

**AC-02 — The correct job is enqueued with the correct arguments**
Given the same request as AC-01, with a fake `Queue` dependency override recording calls
When the request completes
Then exactly one `enqueue_call` was recorded, with `func` resolving to
`run_crawl_execution`, `args == (run.crawl_run_id,)`, `job_id == run.crawl_run_id`, and a `timeout` other than RQ's default
Verification: `pytest backend/tests/integration/crawling/test_router_rq_enqueue.py::test_enqueue_call_arguments`

**AC-03 — `enqueue_crawl_run` alone never advances company status or touches targets**
Given a valid company/discovery run
When `WebsiteCrawlService.enqueue_crawl_run` is called directly (service-level, against fakes)
Then the returned `CrawlRun.status == CrawlStatus.QUEUED`, no target was selected or persisted, and `FakeCompanyCrawlGateway.update_processing_status` was never called
Verification: `pytest backend/tests/integration/crawling/test_website_crawl_service.py::test_enqueue_crawl_run_does_not_execute`

**AC-04 — `execute_crawl_run` given a previously-enqueued run completes exactly as `start_crawl_run` did**
Given a run created via `enqueue_crawl_run`
When `execute_crawl_run(run.crawl_run_id)` is called
Then the final `CrawlRun` matches what `start_crawl_run` would have
produced for the same inputs (status progression `queued -> running -> `
a terminal status, company status advanced to `CRAWLING` then
`CRAWLED`/`FAILED`, targets selected and processed)
Verification: `pytest backend/tests/integration/crawling/test_website_crawl_service.py::test_execute_crawl_run_matches_start_crawl_run`

**AC-05 — A cancelled-before-execution run is never processed**
Given a run created via `enqueue_crawl_run`, then cancelled via `cancel_run` before `execute_crawl_run` is ever called
When `execute_crawl_run(run.crawl_run_id)` is subsequently called
Then it returns immediately with `status == CrawlStatus.CANCELLED`, no target is selected or fetched, and company processing status is never advanced
Verification: `pytest backend/tests/integration/crawling/test_website_crawl_service.py::test_execute_crawl_run_short_circuits_when_already_cancelled`

**AC-06 — `start_crawl_run` (composed convenience) still passes the full existing suite unmodified**
Given the existing `backend/tests/integration/crawling/test_website_crawl_service.py` suite (AC-01 through AC-36 of the crawling-module contract)
When the test suite is run after this task's changes
Then every existing test passes without modification to its own body (only new test functions are added to the file)
Verification: `pytest backend/tests/integration/crawling/test_website_crawl_service.py`

**AC-07 — Retry enqueues instead of running inline, and marks the run `queued` immediately**
Given a completed run with failed targets
When `POST /api/crawl-runs/{crawl_run_id}/retry-failed` is called
Then the response is `200` with `data.status == "queued"`, `retry_failed` was not executed synchronously, and a job was enqueued with `job_id == f"{crawl_run_id}-retry"`
Verification: `pytest backend/tests/integration/crawling/test_router_rq_enqueue.py::test_retry_failed_enqueues`

**AC-08 — Cancel is idempotent and never fails the request if no RQ job exists**
Given a run with no corresponding RQ job ever enqueued (e.g. created before this feature, or the job already finished)
When `POST /api/crawl-runs/{crawl_run_id}/cancel` is called
Then the response is still `200` with the run marked `cancelled` in the repository, and no exception propagates from the best-effort job-cancel attempt
Verification: `pytest backend/tests/integration/crawling/test_router_rq_enqueue.py::test_cancel_tolerates_missing_rq_job`

**AC-09 — Worker entrypoint composes a working `WebsiteCrawlService`**
Given `backend/app/modules/crawling/infrastructure/rq_jobs.py`'s `_build_service`
When called with a test database substituted for `get_database`'s return value (monkeypatched)
Then it returns a `WebsiteCrawlService` instance wired with real gateway/repository/fetcher/storage adapters (type-checked, not `None`, not a fake) — a smoke test only, no real Redis/worker process involved
Verification: `pytest backend/tests/unit/crawling/test_rq_jobs.py::test_build_service_composes_real_adapters`

**AC-10 — No path outside `modules/crawling/**`, `app/config.py`, `app/queue.py`, `app/worker.py`, and `pyproject.toml` is touched**
Given the full diff for this task
When reviewed
Then no file under `modules/companies/**`, `modules/discovery/**`, `modules/extraction/**`, `frontend/**`, `docker-compose.yml`, or `.gitignore` is modified
Verification: `git diff --stat` inspected manually against this list

---

# Required Tests

**Unit tests** (`backend/tests/unit/crawling/`, no real Redis, no real
MongoDB): `test_rq_jobs.py` — `_build_service` composition (AC-09),
with `get_database` monkeypatched to a stub/test double; does not
exercise `asyncio.run`'s actual execution path against real network
I/O (that is already covered by the existing fakes-based service
suite per AC-04/AC-06).

**Integration tests** (`backend/tests/integration/crawling/`, existing
fakes-based conftest, no real MongoDB, no real network — unchanged
infrastructure): new file `test_router_rq_enqueue.py` using a
locally-defined `FakeQueue` (records `enqueue_call` invocations,
returns a fake object with a `.id`) overriding `get_crawl_queue` via
`app.dependency_overrides`, covering AC-01, AC-02, AC-07, AC-08.
New test functions added to the existing
`test_website_crawl_service.py` (not a new file, to keep the
service-level fakes/setup shared) covering AC-03, AC-04, AC-05; AC-06
is satisfied by the existing suite requiring zero modification.

**API tests**: covered within `test_router_rq_enqueue.py` — response
shape/status-code assertions for the three changed routes (AC-01,
AC-07, AC-08). No new schema, so no new
`test_api_schema_serialization.py` cases are strictly required, though
adding one assertion there that a freshly-created run's `status` field
serializes as `"queued"` is a reasonable, cheap addition.

**Real Redis + real `rq worker` end-to-end test: explicitly NOT
required, waived.** Rationale, stated explicitly rather than silently
omitted (matching this repository's established precedent for
declaring a waived test category and why, e.g. the paste-in-importer
contract's browser-test waiver): spinning up a real Redis instance and
a real `rq worker` subprocess inside the automated test suite would
require either (a) a new CI/test-infra dependency this repository does
not otherwise have (no test currently starts an external process or
depends on a service beyond the already-established MongoDB test
database), or (b) depending on the shared `/srv/infra` Redis instance
being reachable from every environment this test suite runs in,
which is not guaranteed the way the MongoDB test database
already is (`backend/tests/conftest.py`'s fixtures are the
established, guaranteed-available precedent; no equivalent exists for
Redis). The `FakeQueue`-based router tests (AC-01, AC-02, AC-07, AC-08)
prove the *enqueue call is made correctly, instead of an inline
await*, which is the actual behavior this task changes and needs
proven. The worker side is proven correct by AC-09 (composition) plus
the existing, unmodified `execute_crawl_run`/`retry_failed` logic
already being fully covered by the pre-existing fakes-based service
suite (AC-04, AC-06) — what a real end-to-end Redis+worker test would
additionally prove is that RQ itself correctly serializes/deserializes
a string argument and calls a plain function, which is RQ's own
well-established, out-of-this-repository's-scope behavior, not this
task's logic. **Manual verification (recommended, not required):**
once implemented, run `docker` or the shared `/srv/infra` stack's
Redis, run `.venv/bin/python -m app.worker` in one terminal and
`.venv/bin/uvicorn backend.app.main:app --reload --port 8000` in
another, `POST` a real crawl run, and confirm it transitions from
`queued` to a terminal status by polling `GET /api/crawl-runs/{id}`
without the initial `POST` ever blocking.

**Browser tests**: not applicable — no frontend change is in scope.

---

# Risks

**Technical risks**
- RQ's behavior when `enqueue_call` is given a `job_id` that
  collides with an existing, already-finished job's id in Redis is
  not verified against the actual installed `rq` version as part of
  this contract (a real-Redis check, deliberately not required — see
  Required Tests). The retry-job-id decision (`f"{crawl_run_id}-retry"`,
  distinct from the create job's id) sidesteps the one collision case
  this contract can identify (retry-after-create); a second retry
  requested while a first retry job is still queued is a genuine,
  unresolved race this task does not prevent — document it as a known
  gap, do not attempt to build request-level de-duplication for it.
- If Redis is unreachable at the moment `queue.enqueue_call(...)` is
  called (after `enqueue_crawl_run` has already persisted a `queued`
  `CrawlRun` in MongoDB), the two systems are not written atomically —
  a `queued` run that will never execute can be left behind. No
  outbox/two-phase-commit pattern is built for this vertical slice;
  the router should let the enqueue exception propagate (FastAPI's
  default 500), which at least surfaces the failure to the caller
  rather than silently returning a run that looks `queued` but is
  actually orphaned. This is an accepted, documented gap for this
  vertical slice, not solved here.
- RQ's default job timeout (180s) must be overridden — see "Job
  timeout" above. Getting this wrong silently truncates long crawl
  runs; the AC-02 assertion (`timeout` other than the default) is the
  concrete guard against regressing this.

**Business risks**
- None beyond what the crawling module's own contract already
  documents (sequential fetching, `detect_only` browser-fallback
  default, etc.) — this task changes *when* that logic runs, not what
  it does.

**Performance risks**
- A single `rq worker` process (as specified in `app/worker.py`)
  processes crawl jobs one at a time — consistent with the crawling
  module's own "concurrency per company = 1, no distributed crawling"
  mandate, so this is not a regression, but it does mean multiple
  companies' crawl runs queue up behind each other rather than running
  in parallel. Running multiple `rq worker` processes against the same
  queue for horizontal scaling is a natural, unbuilt future step, not
  required by this task.

**Security risks**
- None new. Redis, per ADR 0004, is the same shared, unauthenticated
  local dev-infra instance MongoDB already uses in this environment —
  consistent with this repository's existing accepted local/single
  -tenant risk posture (no authentication anywhere yet).

**Data integrity risks**
- None new to `CrawlRun`/`CrawlTarget`/`CrawledPage` documents — no
  schema change, existing `document_version` optimistic concurrency is
  untouched and still applies to every write path (worker-issued writes
  go through the exact same `CrawlRepository.update_run`/`update_target`
  methods as the old inline path did).

---

# Dependencies

**External APIs:** None new.

**MongoDB:** Unchanged — same collections, same repository interface,
same DI (`app.db.get_database`).

**Redis:** New. Reuses the shared `/srv/infra` stack at
`localhost:6379` per ADR 0004 — no new compose service, no new
provisioning step beyond confirming that instance is reachable (it
already is, per the task brief's own investigation).

**Playwright:** Not used, unaffected by this task.

**OpenAI:** Not used, unaffected by this task.

**Environment variables:** New — `REDIS_URL` (`backend/app/config.py`,
`.env.example`).

**Required follow-up outside this task (report, do not build):**
1. Update CLAUDE.md's directory-layout listing under `backend/app/` to
   include `queue.py` and `worker.py`, and its "Local infra" section's
   Redis mention (currently: "Redis and background workers are
   deliberately not scaffolded yet") to reflect that crawling now uses
   both — a routine content-accuracy edit to the directory map/infra
   description, not a change to any instruction or rule in that file.
2. Task 012's contract line "there is no queue or worker system in
   this repository" (`docs/contracts/completed/wire-jobs-page-to-pipeline-runs.md`)
   is now stale for crawling specifically. That file is a completed,
   historical contract per CLAUDE.md's task-workflow rules and is not
   edited after the fact — flagged here as a known staleness, not
   fixed.
3. Applying the same enqueue/execute split to `WebsiteDiscoveryService.run_discovery`
   and `StructuredExtractionService.start_extraction_run`, each as its
   own future feature contract, per ADR 0004's module-by-module
   rollout plan. Not started by this task.
4. The bulk-import auto-discovery question ADR 0003 deferred is still
   deferred — queuing crawling does not, by itself, make discovery
   queued (see #3). A future ADR revisiting ADR 0003 needs discovery
   itself queued first.

---

# Out of Scope

- `modules/discovery/**` and `modules/extraction/**` — no changes,
  no RQ adoption for either in this task (ADR 0004's module-by-module
  rollout; crawling only).
- Auto-chaining crawl completion into an extraction run — not
  attempted, not enabled by this task.
- The two extraction no-ops (`update_latest_extraction_run`,
  `project_latest_facts`, `docs/contracts/completed/structured-extraction-and-evidence-module.md`) —
  unrelated to this task, not touched.
- `frontend/src/pages/JobsPage.tsx` and any of its tests — no code
  change. Its existing `queued -> queued` status mapping already
  handles a `CrawlRun` spending real time in `queued`; this is a
  behavior change in *when* that status is observed, not a new status
  value requiring new frontend mapping logic. The one place this
  creates staleness is a already-completed contract's own historical
  documentation line (see Dependencies #2), which is flagged, not
  fixed, per CLAUDE.md's rule against editing historical task/contract
  records after the fact.
- `docker-compose.yml` / root `.gitignore` — not modified (Redis
  reuses shared infra, per ADR 0004).
- Horizontal worker scaling (multiple `rq worker` processes), job
  retries/backoff at the RQ layer (distinct from the crawling
  module's own existing HTTP-level retry policy, which is unaffected),
  RQ's dashboard/monitoring tooling (e.g. `rq-dashboard`) — none
  needed for this vertical slice.
- Any change to `CrawlTarget`/`CrawledPage`'s MongoDB schema — none
  needed. **Amended:** `CrawlRun` itself did require one new field
  (`options_snapshot`), and `docs/architecture/mongodb-design.md` was
  updated accordingly — see the "Affected repositories" amendment
  above. This was a corrected premise, not new scope: the field exists
  to make AC-04 ("`execute_crawl_run` ... completes exactly as
  `start_crawl_run` did") actually true, which the original design
  failed to do without it.
- Authentication/authorization on the worker process or Redis
  connection — consistent with this repository's existing accepted
  no-auth-yet posture.

---

# Suggested Implementation Order

1. `pyproject.toml` — add `redis`, `rq` dependencies; install; confirm
   `import rq, redis` works in the project's virtualenv.
2. `backend/app/config.py` + `.env.example` — add `REDIS_URL`.
3. `backend/app/queue.py` — connection/queue factory. No dependents
   yet; independently testable by import alone.
4. `WebsiteCrawlService`: split `start_crawl_run` into
   `enqueue_crawl_run` + `execute_crawl_run` (keeping `start_crawl_run`
   as the composed wrapper) + add `enqueue_retry`. Run the full
   existing `test_website_crawl_service.py` suite immediately after
   this step, unmodified, to confirm AC-06 before touching anything
   else.
5. Add the new AC-03/AC-04/AC-05 test functions to
   `test_website_crawl_service.py`.
6. `backend/app/modules/crawling/infrastructure/rq_jobs.py` — job
   wrapper functions + `CRAWL_JOB_TIMEOUT` constant. Add
   `test_rq_jobs.py` (AC-09).
7. `backend/app/worker.py` — worker entrypoint script.
8. `api/router.py` — `get_crawl_queue` DI accessor; update the three
   route handlers (create, retry-failed, cancel) per "Router changes."
9. `backend/tests/integration/crawling/test_router_rq_enqueue.py` —
   `FakeQueue`, AC-01, AC-02, AC-07, AC-08.
10. Full local verification: `pytest backend/tests/unit/crawling backend/tests/integration/crawling`,
    `ruff check`, `pyright` on all new/changed paths.
11. Manual smoke test (recommended, not required — see Required
    Tests) against a real Redis + `rq worker` + real MongoDB.
12. Final report: files created/changed, the job-timeout value chosen
    and why, the retry-job-id collision-avoidance decision, confirmation
    that `start_crawl_run`'s existing test suite passed unmodified, and
    the "Required follow-up" list above.

---

# Success Criteria

This feature is complete only when:

✓ AC-01 through AC-10 all pass

✓ Every test file listed under "Required Tests" exists and passes,
including the pre-existing `test_website_crawl_service.py` suite
passing with zero modification to its existing test bodies (only
additions)

✓ `git diff --stat` touches only `backend/app/modules/crawling/**`,
`backend/app/config.py`, `backend/app/queue.py` (new),
`backend/app/worker.py` (new), `.env.example`, `pyproject.toml`, and
their own test directories — confirmed, no cross-module changes, no
frontend changes, no `docker-compose.yml`/`.gitignore` changes

✓ `ruff check` and `pyright` are clean on every new/changed path

✓ The "Required follow-up" list is reported, not silently built or
silently omitted

✓ Evaluator reports PASS
