# Feature Contract: Task 020 — Adopt RQ for the discovery module (vertical slice)

Task brief: `docs/execution-plans/tasks/020-Adopt-RQ-Discovery-Vertical-Slice.md`

Binding architectural precedent: `docs/decisions/0005-auto-chain-import-discovery-crawl.md`
(Accepted), which itself builds on `docs/decisions/0004-adopt-rq-as-queue-system.md`
(Accepted, RQ + Redis generally) and revisits
`docs/decisions/0003-auto-discovery-trigger-placement.md` (Accepted).
ADR 0005 authorizes the *general policy* of auto-chaining company
creation → discovery → crawl; it explicitly reserves the concrete
discovery-RQ mechanics for this contract, and explicitly reserves the
concrete auto-chain wiring (enqueue-on-create, enqueue-crawl-on-
discovery-completion) for a future, not-yet-written Task 021 contract.
**This contract does not implement any auto-chaining.** It mirrors
`docs/contracts/completed/017-rq-crawling-vertical-slice.md`'s pattern
almost exactly, applied to `WebsiteDiscoveryService` instead of
`WebsiteCrawlService`, and calls out every place discovery's actual
current shape differs from crawling's rather than assuming parity.

Depends only on `backend/app/modules/discovery/**` already existing
(Task 005) and being registered in `backend/app/main.py` (already true
— confirmed by direct inspection: `discovery_router` is included at
`backend/app/main.py:59`, contradicting `discovery/api/router.py`'s own
module docstring, which currently claims it is "Built but **not**
centrally registered in `backend/app/main.py`" — that docstring is
stale and is corrected as part of this task, since this task already
edits that file's synchronous-execution claim in the same docstring;
see "Router changes" below).

Also depends on `backend/app/queue.py`, `backend/app/worker.py`,
`backend/app/config.py`'s `REDIS_URL` setting, and the `redis`/`rq`
`pyproject.toml` dependencies already existing from Task 017 — all
confirmed present by direct inspection. **None of these four are
modified by this task except `backend/app/worker.py`'s `QUEUE_NAMES`
list** (see "New shared infrastructure" below).

# Feature

## Business Goal

`POST /api/companies/{company_id}/discovery-runs` today runs an entire
discovery pass (homepage resolution across up to four candidate URLs,
a robots.txt fetch, up to `max_sitemap_files` (50) sequential sitemap
fetches, link extraction and reconciliation) inline inside the HTTP
request/response cycle — confirmed by direct inspection of
`WebsiteDiscoveryService.run_discovery`
(`backend/app/modules/discovery/application/website_discovery_service.py:73`).
A caller's connection must stay open for the full duration, and — per
ADR 0005 — this synchronous shape is also the specific blocker that
prevented auto-triggering discovery from the bulk import-commit path
(ADR 0003's original conclusion) and from being safely auto-chained
into by any other pipeline stage. This feature moves discovery
execution onto a background worker via RQ, exactly mirroring Task 017's
crawling precedent, so the create-discovery-run endpoint returns
immediately with a `queued` run the caller can poll, and — critically
for ADR 0005's follow-up work (Task 021) — so that a future auto-
enqueue call from company creation is cheap and safe to make inline.

## User Story

As a caller of the discovery API (today: a human hitting the API
directly, or `modules/companies`' `create_company` handler calling
`WebsiteDiscoveryService` synchronously; eventually, per ADR 0005 and
Task 021: an auto-enqueue call from both company-creation paths), I
want `POST .../discovery-runs` to return immediately with a trackable
`queued` run, and the actual discovery work to happen on a background
worker, so that starting discovery is a fast, reliable operation
regardless of how many sitemap files or candidate homepages it needs to
check.

## Business Value

The second concrete application of ADR 0004's queue decision, and the
direct prerequisite ADR 0005 requires before any auto-chaining wiring
(Task 021) can be built safely. Validates that Task 017's RQ pattern
generalizes cleanly to a second pipeline module with a meaningfully
different shape (no retry/cancel endpoints, no per-target execution
loop, no options object) — proving the pattern is genuinely reusable,
not crawling-specific.

---

# Architecture Impact

## Affected domains

`backend/app/modules/discovery/` only, plus two files entirely outside
any module (`backend/app/worker.py`, edited; `backend/app/config.py`
and `backend/app/queue.py`, confirmed unchanged — see "New shared
infrastructure"). No other module's `domain/`, `application/`,
`infrastructure/`, or `api/` directory changes.

## Affected services

`WebsiteDiscoveryService`
(`backend/app/modules/discovery/application/website_discovery_service.py`)
is restructured, not rewritten: `run_discovery` is split into two
methods along the same seam Task 017 used for `start_crawl_run` — the
moment the `DiscoveryRun` document is first created and persisted, in
its default `QUEUED` status. No change to `WebsiteCrawlService`,
`StructuredExtractionService`, `CompanyService`, or any other module's
service.

**Materially smaller surface than Task 017, confirmed by direct
inspection — not assumed:**
- Discovery has **no retry endpoint and no retry method.** There is no
  `retry_failed`/`retry-failed` route analogous to crawling's
  `POST /api/crawl-runs/{crawl_run_id}/retry-failed`
  (`backend/app/modules/discovery/api/router.py` has exactly five
  routes: create, get-latest-for-company, get-by-id, list, list-urls —
  confirmed by direct inspection, no retry route exists). This task
  therefore adds **no** `enqueue_retry`-equivalent method and **no**
  retry-job-id-collision decision to make.
- Discovery has **no cancel endpoint and no cancel method.** There is
  no `cancel_run` on `WebsiteDiscoveryService` and no
  `POST .../discovery-runs/{id}/cancel` route. `DiscoveryStatus`
  (`backend/app/modules/discovery/domain/enums.py`) has exactly five
  members — `QUEUED`, `RUNNING`, `COMPLETED`,
  `COMPLETED_WITH_WARNINGS`, `FAILED` — **there is no `CANCELLED`
  value at all**, unlike `CrawlStatus`. Internally, `_finish_as_cancelled`
  is called only from within `run_discovery`'s own cancellation checks
  (see below) and represents a cancellation as `FAILED` with
  `error="cancelled"`, not a distinct status. This task therefore adds
  **no** "return early if already cancelled" guard analogous to Task
  017's `execute_crawl_run` guard (AC-05 of the crawling contract) —
  there is no external cancel mechanism that could race with a worker
  picking up a queued discovery job, because there is no cancel
  endpoint to race against.
- Discovery has **no `find_active_run`/duplicate-active-run check.**
  `DiscoveryRepository` (`backend/app/modules/discovery/domain/repository.py`)
  has no such method, and `run_discovery` never checks for one before
  creating a new run. This task therefore introduces **no**
  `DuplicateActiveCrawlRunError`-equivalent exception or 409 response —
  none exists today for discovery and this task does not add one (out
  of scope; not requested).
- Discovery has an existing internal `cancellation_check: CancellationCheck | None`
  keyword argument on `run_discovery`
  (`CancellationCheck = Callable[[], bool]`) — used by exactly one
  existing test
  (`backend/tests/integration/discovery/test_discovery_service.py:292`,
  `cancellation_check=lambda: True`) and **never exposed by the HTTP
  API** (`create_discovery_run`'s route handler never passes one — the
  route takes no request body at all beyond the `company_id` path
  parameter, confirmed by direct inspection of
  `backend/app/modules/discovery/api/router.py`). This parameter is
  preserved on the composed `run_discovery` and threaded into the new
  `execute_discovery_run` (see "Application service changes"); it is
  **not** passed across the RQ job boundary by the router's new enqueue
  call, because the router never had a way to supply one in the first
  place — this is not a new gap this task introduces, it is the
  existing, unchanged shape of the one caller (a direct-service-call
  test) that uses it.

## Affected repositories

No new method. `DiscoveryRepository`'s existing interface (`create_run`,
`update_run`, `get_run`, plus the URL methods) already has everything
the new split needs — confirmed by direct inspection of
`backend/app/modules/discovery/domain/repository.py`. The RQ job id for
a fresh discovery run is `discovery_run_id` itself (a freshly-generated
UUID per new `DiscoveryRun`), exactly mirroring Task 017's job-identity
decision for `crawl_run_id` — no new field is persisted to recover it
later.

**No `options_snapshot`-equivalent field is needed, and this is
checked explicitly below (per this contract's own obligation to verify
rather than assume parity with Task 017's crawling contract) — see
"Options/config risk assessment: explicitly checked, no equivalent
bug is possible."**

## Affected APIs

`POST /api/companies/{company_id}/discovery-runs` changes behavior
(enqueue instead of inline execution — see "Router changes"). Every GET
endpoint (`.../discovery-runs/latest`, `/api/discovery-runs/{id}`,
`/api/discovery-runs`, `/api/discovery-runs/{id}/urls`) is unchanged —
they already read whatever `DiscoveryRun.status` currently is, and that
enum already includes `queued` today (it is in fact the model's
default value — `DiscoveryRun.status: DiscoveryStatus = DiscoveryStatus.QUEUED`,
`backend/app/modules/discovery/domain/models.py:123` — unlike
`CrawlRun`, which had to explicitly set `QUEUED` in code before Task
017; discovery's model already defaulted to it). No response-schema
change is needed anywhere — `DiscoveryRunResponse.status` is a plain
`str` field (`backend/app/modules/discovery/api/schemas.py:34`), not an
enum-constrained one, so `"queued"` already serializes correctly today.

## Affected database collections

None. Same two collections (`discovery_runs`, `discoveries`), same
documents, same indexes. `DiscoveryRun.status` will now spend real
wall-clock time as `queued` (previously visible only for a database
round trip inside a single inline call), exactly the same behavior
change Task 017 made for `CrawlRun.status`.

## Affected frontend pages

None. `frontend/src/pages/JobsPage.tsx`'s status mapping
(`frontend/src/api/jobs.ts`'s `RUN_STATUS_TO_JOB_STATUS` table) already
declares its `BackendRunStatus` union to cover every literal across
`DiscoveryStatus`, `CrawlStatus`, and `ExtractionStatus` in one shared
table, with an explicit comment noting "Discovery only ever produces a
subset of these (`queued`, `running`, `completed`,
`completed_with_warnings`, `failed`)" — confirmed by direct inspection.
`queued -> queued` is already mapped. No frontend code or test changes
are required or in scope for this contract.

---

# Cross-module dependency decisions

None needed. This task adds no new gateway, no new port, and touches
no other module's `domain/`/`application/`/`infrastructure/`. The
shared Redis/queue accessor (`app.queue.get_queue`) already exists from
Task 017 and needs no changes — `get_queue(name: str) -> Queue` is
already fully generic over the queue name (confirmed by direct
inspection of `backend/app/queue.py`); it required no crawling-specific
logic to begin with.

---

# New shared infrastructure

## `backend/app/config.py`, `backend/app/queue.py`, `pyproject.toml`

**Unchanged.** `REDIS_URL` (in `Settings`), `get_redis_connection`/
`get_queue` (in `queue.py`), and the `redis>=5.0`/`rq>=1.16` dependency
entries all already exist from Task 017 — confirmed by direct
inspection of all three files/sections. No edits needed anywhere in
this trio.

## `backend/app/worker.py` (edited)

`QUEUE_NAMES` is currently a hardcoded list literal, `["crawling"]`
(`backend/app/worker.py:13`) — this **does** require a code change, it
is not already generic. New content:

```python
"""RQ worker entrypoint. Run with:
    .venv/bin/python -m app.worker
Processes jobs for every queue this repository has adopted RQ for.
Crawling was first (Task 017); discovery is second (Task 020). Add a
queue name here when extraction adopts RQ per ADR 0004 — one queue
name per module, added to this same list, not a second worker script.
"""

from rq import Worker

from app.queue import get_redis_connection

QUEUE_NAMES = ["crawling", "discovery"]

if __name__ == "__main__":
    Worker(QUEUE_NAMES, connection=get_redis_connection()).work()
```

Ordering is append, not reorder or reprioritize — `"crawling"` stays
first since it was adopted first. **Explicit, documented consequence,
not silently accepted:** RQ's `Worker(queue_names, ...)` model checks
queues in the order given each time it looks for work, meaning
`"crawling"` jobs take priority over `"discovery"` jobs whenever both
have queued work and only one worker process is running — see
"Performance risks" below. This task does not attempt to build fair-
share scheduling between the two queues; running one worker process
per queue is the natural mitigation, left as an unbuilt future
operational choice (exactly Task 017's own precedent for horizontal
worker scaling).

## `backend/app/domains/queue_stats/router.py`

**Unchanged, confirmed already fully generic.** `GET /api/queue-stats?queue=discovery`
already works with no code change: `get_queue_by_name`
(`backend/app/domains/queue_stats/router.py:34`) resolves any queue
name via the query parameter through the same already-generic
`app.queue.get_queue`, defaulting to `"crawling"` only when no `?queue=`
is supplied. Its own docstring/comment already anticipates this
("Generalizes to any future queue name (discovery, extraction, ...)
with no change here") — confirmed accurate by direct inspection, not
merely asserted.

---

# Discovery-module changes

## Current behavior (confirmed by direct inspection)

`WebsiteDiscoveryService.run_discovery(company_id, *, cancellation_check=None)`
today, in one call: resolves `root_domain` via
`company_gateway.get_company_domain(company_id)` (raises
`CompanyNotFoundForDiscoveryError` if the company doesn't exist);
builds and persists a `DiscoveryRun` (defaults to `DiscoveryStatus.QUEUED`
per the model's own default, no explicit assignment needed); immediately
flips it to `RUNNING`, sets `started_at`, persists; advances company
`processing.status` to `DISCOVERING` (best-effort, swallowing
`InvalidStatusTransitionError`); checks `cancellation_check` before each
major phase (homepage resolution, link extraction, robots fetch, sitemap
processing) — if cancelled, calls `_finish_as_cancelled` (internally,
`_finish_as_failed(..., error="cancelled")`, i.e. status becomes
`FAILED`, not a distinct cancelled status); resolves the homepage across
four candidate URLs (real network I/O; failure here aborts the whole
run via `_finish_as_failed`); extracts links, fetches robots.txt and any
declared sitemaps (each individually non-fatal — failures become
warnings, not run failures); reconciles all candidates into
`DiscoveredUrl` records, persists new ones (skipping ones already saved
for this run, an idempotency-adjacent duplicate-URL guard, **not** a
duplicate-*run* guard); computes the final `DiscoverySummary` and
terminal status (`COMPLETED` or `COMPLETED_WITH_WARNINGS`); persists;
advances company status to `DISCOVERED`; calls
`company_gateway.update_latest_discovery_run`; returns the completed
run. `api/router.py`'s `create_discovery_run` route awaits this entire
chain inline before responding.

## Options/config risk assessment: explicitly checked, no equivalent bug is possible

Task 017's crawling contract's original design assumed
`configuration_snapshot` captured everything `execute_crawl_run` needed
to recover from `crawl_run_id` alone, and that assumption was wrong —
several fields on `CrawlRunOptions` (`force_refresh`,
`include_page_types`, `exclude_page_types`, `manual_urls`) were silently
dropped across the enqueue/execute split until an evaluation pass
caught it, requiring a new `options_snapshot` field to fix.

**This exact class of bug cannot occur here, checked explicitly rather
than assumed away:** `run_discovery`'s full signature is
`run_discovery(self, company_id: str, *, cancellation_check: CancellationCheck | None = None) -> DiscoveryRun`
(`backend/app/modules/discovery/application/website_discovery_service.py:73`).
There is no options object analogous to `CrawlRunOptions` at all — the
*only* real input beyond `company_id` is `cancellation_check`, an
in-process `Callable` that is never populated by any HTTP caller (the
route takes no request body — see "Affected services" above) and was
never a candidate for persistence in the first place (a `Callable`
cannot be stored in MongoDB or passed across an RQ job boundary
regardless of this task). Every other piece of state
`execute_discovery_run` needs to resume from a bare `discovery_run_id`
— `root_domain`, `company_id` — is already captured on the persisted
`DiscoveryRun` document itself at creation time (`root_domain` is a
required, non-optional field on the model, set from the very first line
of what becomes `enqueue_discovery_run` — see below). There is nothing
this split can drop, because there is nothing beyond `company_id` for a
caller to configure per-call in the first place.

## Application service changes (`website_discovery_service.py`)

Split `run_discovery` into two methods along the exact seam already
present in its own code (the moment the `DiscoveryRun` document is
first created and persisted):

1. **`async def enqueue_discovery_run(self, company_id: str) -> DiscoveryRun`**
   — everything `run_discovery` does *before* execution starts:
   resolve `root_domain` via `company_gateway.get_company_domain`
   (raises `CompanyNotFoundForDiscoveryError`), build and persist the
   `DiscoveryRun` record via `create_run`. Returns the persisted run,
   still in its default `DiscoveryStatus.QUEUED` state, with `started_at`
   unset and no network I/O attempted. This method's only I/O is the
   domain lookup (a gateway call, itself backed by a Mongo read via
   `CompanyService.get_company`) and the run's own persistence — safe
   and fast to run synchronously inside the HTTP request, exactly Task
   017's reasoning for why `enqueue_crawl_run` belongs in the
   synchronous path.

2. **`async def execute_discovery_run(self, discovery_run_id: str, *, cancellation_check: CancellationCheck | None = None) -> DiscoveryRun`**
   — everything `run_discovery` did *after* run creation, unchanged in
   substance, re-anchored on a `discovery_run_id` looked up fresh from
   the repository instead of an in-memory `run` object carried over
   from creation: `run = await self._repository.get_run(discovery_run_id)`,
   raising `DiscoveryRunNotFoundError` if missing (this exception
   already exists — `backend/app/modules/discovery/domain/exceptions.py` —
   and is already used by the GET-by-id route; this is its first use
   inside the service itself, exactly mirroring `CrawlRunNotFoundError`'s
   equivalent new use inside `execute_crawl_run`). No "already
   cancelled" short-circuit guard is added — see "Affected services"
   above for why none is needed (no cancel endpoint, no `CANCELLED`
   status value exists for discovery at all). Otherwise: set
   `run.status = RUNNING`/`started_at`, persist, advance company status
   to `DISCOVERING` (best-effort, unchanged), run the cancellation-
   gated homepage/link/robots/sitemap pipeline unchanged, compute final
   summary/status, persist, advance company status to `DISCOVERED`,
   call `update_latest_discovery_run`, return the completed run.

3. **`async def run_discovery(self, company_id: str, *, cancellation_check: CancellationCheck | None = None) -> DiscoveryRun`**
   — **kept**, not deleted, as a thin composed convenience:
   ```python
   run = await self.enqueue_discovery_run(company_id)
   return await self.execute_discovery_run(
       run.discovery_run_id, cancellation_check=cancellation_check
   )
   ```
   This preserves the existing test suite's external contract exactly,
   **including the one existing test that calls `cancellation_check`
   directly**
   (`backend/tests/integration/discovery/test_discovery_service.py:292`,
   `service.run_discovery("company-1", cancellation_check=lambda: True)`).
   Do not remove `run_discovery`; do not have the router call it going
   forward.

No `enqueue_retry` equivalent is added — there is nothing to enqueue a
retry for (see "Affected services" above).

## Router changes (`api/router.py`)

Add one new DI accessor, matching Task 017's `get_crawl_queue` pattern:

```python
def get_discovery_queue() -> Queue:
    return get_queue("discovery")
```
(`Queue` imported from `rq`, `get_queue` from `app.queue` — this
router's other `get_*` functions already return concrete infrastructure
directly, e.g. `get_discovery_repository` returns `MongoDiscoveryRepository`
directly, so this is consistent with, not a deviation from, this file's
existing convention.)

**`POST /api/companies/{company_id}/discovery-runs`** (`create_discovery_run`):
replace the current `await service.run_discovery(company_id)` call
with:
```python
run = await service.enqueue_discovery_run(company_id)
except CompanyNotFoundForDiscoveryError:
    ... (unchanged 404 handling)
queue.enqueue_call(
    func=run_discovery_execution,   # see "Job wrapper functions" below
    args=(run.discovery_run_id,),
    job_id=run.discovery_run_id,
    timeout=DISCOVERY_JOB_TIMEOUT,  # see "Job timeout" below
)
return DiscoveryRunEnvelope(data=run_to_response(run))
```
Response status/shape unchanged (`201`, `DiscoveryRunEnvelope`) — the
returned run's `status` will now read `"queued"` instead of whatever
the inline run eventually finished as. This is the intended, documented
behavior change, identical in kind to Task 017's for crawling.

**Also correct this file's own module docstring as part of this
change** (it currently makes two claims that become stale, one of
which is already stale today): "Built but **not** centrally registered
in `backend/app/main.py`" (already false today — `discovery_router` is
in fact registered, `backend/app/main.py:59` — a pre-existing
documentation staleness this task corrects while already editing this
file) and "The `POST` route runs `WebsiteDiscoveryService` synchronously
inline" (true today, false after this task). New docstring content
should describe the enqueue/execute split, mirroring
`modules/crawling/api/router.py`'s own updated module docstring from
Task 017 as the template.

**Job timeout — explicit decision:** RQ's default job timeout is 180
seconds. Discovery's own worst case is bounded but not trivial: up to
`max_sitemap_files` (50, `DiscoveryConfig.max_sitemap_files`) sequential
sitemap fetches, each individually bounded by
`connect_timeout_s` (5.0) + `read_timeout_s` (10.0) — i.e. up to
~12.5 minutes in the sitemap-fetch phase alone if every fetch times out,
before accounting for the homepage-resolution and robots.txt phases.
`DISCOVERY_JOB_TIMEOUT` must therefore be set generously — a
module-level constant in `infrastructure/rq_jobs.py`,
**`DISCOVERY_JOB_TIMEOUT = "20m"`** (RQ's string duration syntax),
chosen to comfortably exceed the ~12.5-minute worst case with margin,
while deliberately staying well short of crawling's unbounded `"1h"`
(discovery's own work is fundamentally more bounded than crawling's
per-target fetch loop, which has no fixed upper bound on
`max_pages_per_company`). Document this constant's rationale in a
one-line comment at its definition, same as Task 017's precedent.

**Job identity — explicit decision:** the RQ job for a fresh discovery
run uses `job_id=run.discovery_run_id` directly — `discovery_run_id` is
a freshly-generated UUID per new `DiscoveryRun`, so no collision is
possible for a create. Unlike crawling, there is no retry job id to
worry about (no retry endpoint exists), so this is the only job-identity
decision this task needs to make.

## Job wrapper functions — `backend/app/modules/discovery/infrastructure/rq_jobs.py` (new file)

Following Task 017's `rq_jobs.py` pattern exactly — reassembling the
same DI composition `api/router.py`'s `get_discovery_service()`
assembles for a request, but manually, since RQ workers run outside
FastAPI's request-scoped DI and outside any existing asyncio event
loop:

```python
"""RQ job entrypoints for the discovery module. Called by `app.worker`'s
worker process, never by a FastAPI request. Builds the same dependency
composition `api/router.py`'s `get_discovery_service()` assembles for a
request, but manually — RQ workers run outside FastAPI's request-scoped
DI and outside any existing asyncio event loop.
"""

import asyncio

from app.db import get_database
from app.modules.companies.api.router import get_company_service
from app.modules.discovery.api.router import (
    get_company_discovery_gateway,
    get_discovery_repository,
    get_http_discovery_client,
)
from app.modules.discovery.application.website_discovery_service import WebsiteDiscoveryService

# RQ's default job timeout is 180 seconds. Discovery's own worst case —
# up to max_sitemap_files (50) sequential sitemap fetches, each bounded
# by connect_timeout_s (5s) + read_timeout_s (10s) — is already
# ~12.5 minutes before accounting for the homepage/robots fetches; 20
# minutes leaves comfortable margin without being unbounded like
# crawling's "1h". See the feature contract's "Job timeout" section.
DISCOVERY_JOB_TIMEOUT = "20m"


def _build_service() -> WebsiteDiscoveryService:
    database = get_database()
    company_service = get_company_service(database=database)
    return WebsiteDiscoveryService(
        company_gateway=get_company_discovery_gateway(company_service=company_service),
        discovery_repository=get_discovery_repository(database=database),
        http_client=get_http_discovery_client(),
    )


def run_discovery_execution(discovery_run_id: str) -> None:
    asyncio.run(_build_service().execute_discovery_run(discovery_run_id))
```

(As with Task 017, the exact parameter names on each `get_*` DI
function must be checked against `api/router.py`'s current signatures
at implementation time — reproduced above from direct inspection of
`get_company_discovery_gateway(company_service=...)`,
`get_discovery_repository(database=...)`, and
`get_http_discovery_client()` (no arguments) — but if any DI function's
default-`Depends()` chain doesn't allow calling it this way, this
file's job is to make that composition work, not to change
`api/router.py`'s own DI functions.)

**`asyncio.run` per job, not a persistent event loop — same
justification as Task 017:** discovery has no documented concurrency
requirement beyond "one discovery run in flight per job," and RQ's
default one-job-at-a-time worker model already matches that.

> **Note for Task 021 (do not build this now):** this job wrapper
> function — `run_discovery_execution` — is the natural, symmetric place
> a future auto-chain-to-crawl hook would go, once Task 021 designs and
> authorizes it (per ADR 0005's Decision #5): the one place that already
> knows, synchronously, the exact moment a discovery run reaches a
> terminal status (immediately after `execute_discovery_run` returns,
> inside this same function body). **This task does not add any such
> hook.** `run_discovery_execution` above calls `execute_discovery_run`
> and returns `None` — no crawl-enqueue call, no import of
> `WebsiteCrawlService` or any crawling-module symbol, nothing. Task 021
> is responsible for designing exactly what that hook looks like
> (whether it enqueues unconditionally right here, what
> `CrawlRunOptions` it supplies, how a crawl-enqueue failure is
> reported/logged) as its own, separate feature contract.

---

# Acceptance Criteria

**AC-01 — `POST .../discovery-runs` returns immediately without executing discovery**
Given a valid company
When `POST /api/companies/{company_id}/discovery-runs` is called
Then the response is `201` with `data.status == "queued"`, and the
underlying `WebsiteDiscoveryService.execute_discovery_run` is never
invoked synchronously within the request (verified via a fake
`HttpDiscoveryClient` that would record/raise if ever called, asserted
un-called after the response returns)
Verification: `pytest backend/tests/integration/discovery/test_router_rq_enqueue.py::test_create_discovery_run_returns_queued_without_executing`

**AC-02 — The correct job is enqueued with the correct arguments**
Given the same request as AC-01, with a fake `Queue` dependency override recording calls
When the request completes
Then exactly one `enqueue_call` was recorded, with `func` resolving to
`run_discovery_execution`, `args == (run.discovery_run_id,)`, `job_id == run.discovery_run_id`, and a `timeout` other than RQ's default
Verification: `pytest backend/tests/integration/discovery/test_router_rq_enqueue.py::test_enqueue_call_arguments`

**AC-03 — `enqueue_discovery_run` alone never advances company status or performs network I/O**
Given a valid company
When `WebsiteDiscoveryService.enqueue_discovery_run` is called directly (service-level, against fakes)
Then the returned `DiscoveryRun.status == DiscoveryStatus.QUEUED`, `started_at is None`, `FakeCompanyDiscoveryGateway.status_updates` is empty, and the fake `HttpDiscoveryClient` recorded no calls
Verification: `pytest backend/tests/integration/discovery/test_discovery_service.py::test_enqueue_discovery_run_does_not_execute`

**AC-04 — `execute_discovery_run` given a previously-enqueued run completes exactly as `run_discovery` did**
Given a run created via `enqueue_discovery_run`
When `execute_discovery_run(run.discovery_run_id)` is called
Then the final `DiscoveryRun` matches what `run_discovery` would have
produced for the same inputs (status progression `queued -> running -> `
a terminal status, company status advanced to `DISCOVERING` then
`DISCOVERED`/`FAILED`, discovered URLs persisted), and calling
`execute_discovery_run` with an unknown `discovery_run_id` raises
`DiscoveryRunNotFoundError`
Verification: `pytest backend/tests/integration/discovery/test_discovery_service.py::test_execute_discovery_run_matches_run_discovery`
and `::test_execute_discovery_run_raises_for_unknown_run`

**AC-05 — `run_discovery` (composed convenience) still passes the full existing suite unmodified, including its direct `cancellation_check` usage**
Given the existing `backend/tests/integration/discovery/test_discovery_service.py` and `test_processing_status_transitions.py` suites
When the test suites are run after this task's changes
Then every existing test passes without modification to its own body (only new test functions are added), including the one test that calls `run_discovery(..., cancellation_check=lambda: True)` directly
Verification: `pytest backend/tests/integration/discovery/test_discovery_service.py backend/tests/integration/discovery/test_processing_status_transitions.py`

**AC-06 — Worker entrypoint composes a working `WebsiteDiscoveryService`**
Given `backend/app/modules/discovery/infrastructure/rq_jobs.py`'s `_build_service`
When called with a test database substituted for `get_database`'s return value (monkeypatched)
Then it returns a `WebsiteDiscoveryService` instance wired with real gateway/repository/http-client adapters (type-checked, not `None`, not a fake) — a smoke test only, no real Redis/worker process involved
Verification: `pytest backend/tests/unit/discovery/test_rq_jobs.py::test_build_service_composes_real_adapters`

**AC-07 — No path outside `modules/discovery/**` and `app/worker.py` is touched**
Given the full diff for this task
When reviewed
Then no file under `modules/companies/**`, `modules/crawling/**`, `modules/extraction/**`, `modules/imports/**`, `frontend/**`, `app/config.py`, `app/queue.py`, `pyproject.toml`, `docker-compose.yml`, or `.gitignore` is modified
Verification: `git diff --stat` inspected manually against this list

---

# Required Tests

**Unit tests** (`backend/tests/unit/discovery/`, no real Redis, no real
MongoDB): new `test_rq_jobs.py` — `_build_service` composition (AC-06),
with `get_database` monkeypatched to a stub/test double; does not
exercise `asyncio.run`'s actual execution path against real network
I/O (already covered by the existing fakes-based service suite per
AC-04/AC-05).

**Integration tests** (`backend/tests/integration/discovery/`, existing
fakes-based conftest, no real MongoDB, no real network — unchanged
infrastructure): new file `test_router_rq_enqueue.py` using a
locally-defined `FakeQueue` (records `enqueue_call` invocations,
returns a fake object with a `.id`) overriding `get_discovery_queue` via
`app.dependency_overrides`, covering AC-01, AC-02. New test functions
added to the existing `test_discovery_service.py` (not a new file, to
keep the service-level fakes/setup shared) covering AC-03, AC-04; AC-05
is satisfied by the existing suite (`test_discovery_service.py` and
`test_processing_status_transitions.py`) requiring zero modification.

**API tests**: covered within `test_router_rq_enqueue.py` — response
shape/status-code assertions for the one changed route (AC-01). No new
schema, so no changes needed to
`backend/tests/integration/discovery/test_api_schema_serialization.py`
— `DiscoveryRunResponse.status` is already a plain `str` and already
handles `"queued"` correctly.

**Real Redis + real `rq worker` end-to-end test: explicitly NOT
required, waived — same rationale as Task 017's crawling contract,
restated here for discovery rather than silently omitted.** Spinning up
a real Redis instance and a real `rq worker` subprocess inside the
automated test suite would require either a new CI/test-infra
dependency this repository does not otherwise have, or depending on the
shared `/srv/infra` Redis instance being reachable from every
environment this suite runs in, which is not guaranteed the way the
MongoDB test database already is. The `FakeQueue`-based router tests
(AC-01, AC-02) prove the enqueue call is made correctly instead of an
inline await, which is the actual behavior this task changes. The
worker side is proven correct by AC-06 (composition) plus the existing,
unmodified `execute_discovery_run`/`run_discovery` logic already being
fully covered by the pre-existing fakes-based service suite (AC-04,
AC-05) — what a real end-to-end Redis+worker test would additionally
prove is that RQ itself correctly serializes/deserializes a string
argument and calls a plain function, which is RQ's own well-established,
out-of-this-repository's-scope behavior, not this task's logic.
**Manual verification (recommended, not required):** once implemented,
run the shared `/srv/infra` stack's Redis, run
`.venv/bin/python -m app.worker` in one terminal (now serving both
`"crawling"` and `"discovery"` queues) and
`.venv/bin/uvicorn backend.app.main:app --reload --port 8000` in
another, `POST` a real discovery run, and confirm it transitions from
`queued` to a terminal status by polling
`GET /api/discovery-runs/{id}` without the initial `POST` ever
blocking.

**Browser tests**: not applicable — no frontend change is in scope.

---

# Risks

**Technical risks**
- Same enqueue/persist non-atomicity gap Task 017 accepted for
  crawling: if Redis is unreachable at the moment
  `queue.enqueue_call(...)` is called (after `enqueue_discovery_run`
  has already persisted a `queued` `DiscoveryRun` in MongoDB), a
  `queued` run that will never execute can be left behind. No
  outbox/two-phase-commit pattern is built here either; the router
  should let the enqueue exception propagate (FastAPI's default 500).
  Accepted, documented gap, not solved by this vertical slice, exactly
  mirroring Task 017's own accepted risk.
- RQ's default job timeout (180s) must be overridden — see "Job
  timeout" above. Getting this wrong silently truncates long discovery
  runs (large sitemap trees); the AC-02 assertion (`timeout` other than
  the default) is the concrete guard against regressing this.
- The internal `cancellation_check` parameter is a `Callable` and
  cannot cross an RQ job boundary (RQ workers receive plain,
  JSON/pickle-serializable arguments). This is **not a new gap**
  introduced by this task — the router never had a way to supply one
  before this task either, so no caller-visible capability is lost.
  Documented explicitly so a future reader doesn't mistake this for an
  oversight.

**Business risks**
- None beyond what the discovery module's own existing contract already
  documents (homepage-candidate resolution order, sitemap depth/file
  limits, etc.) — this task changes *when* that logic runs, not what it
  does.

**Performance risks**
- `backend/app/worker.py`'s single `Worker(QUEUE_NAMES, ...)` process
  now serves two queues, `["crawling", "discovery"]`, in that priority
  order — RQ checks earlier-listed queues first each time it looks for
  work. If crawling jobs are queued continuously, discovery jobs can be
  starved behind them (and vice versa is not possible given this
  ordering, only the reverse is). This task does not attempt fair-share
  scheduling between the two queues; running one worker process per
  queue is the natural, unbuilt mitigation, exactly Task 017's own
  precedent for horizontal scaling being left as a future operational
  choice, not a defect requiring an immediate fix.

**Security risks**
- None new. Same shared, unauthenticated local dev-infra Redis instance
  already used by crawling since Task 017.

**Data integrity risks**
- None new to `DiscoveryRun`/`DiscoveredUrl` documents — no schema
  change (see "Options/config risk assessment" above — confirmed no
  snapshot field is needed, unlike crawling's `options_snapshot`
  amendment). Worker-issued writes go through the exact same
  `DiscoveryRepository.update_run`/`save_discovered_urls` methods as the
  old inline path did.

---

# Dependencies

**External APIs:** None new — same real target websites discovery
already contacts today.

**MongoDB:** Unchanged — same collections, same repository interface,
same DI (`app.db.get_database`).

**Redis:** None new — reuses the same shared `/srv/infra` instance
already wired for crawling by Task 017. No new provisioning step.

**Playwright:** Not used, unaffected by this task.

**OpenAI:** Not used, unaffected by this task.

**Environment variables:** None new — `REDIS_URL` already exists from
Task 017.

**Required follow-up outside this task (report, do not build):**
1. Update CLAUDE.md's directory-layout listing under
   `backend/app/modules/discovery/infrastructure/` to include
   `rq_jobs.py` — a routine content-accuracy edit to the directory map,
   not a change to any instruction or rule in that file. (Task 017's
   own equivalent CLAUDE.md follow-up for `queue.py`/`worker.py`/
   crawling's `rq_jobs.py` and the "Redis... deliberately not
   scaffolded yet" line appears not yet actioned either, per direct
   inspection of the current CLAUDE.md content — this item is
   additional to, not a duplicate of, that still-open one.)
2. `docs/decisions/0005-auto-chain-import-discovery-crawl.md`'s
   authorized-but-unbuilt work: `modules/companies/api/router.py`'s
   `create_company` handler still calls `WebsiteDiscoveryService.run_discovery`
   synchronously (Task 015's wiring, unchanged by this task) — replacing
   it with an enqueue call, adding the same to the bulk import-commit
   path, and wiring the discovery-completion → crawl-enqueue hook
   inside `run_discovery_execution` are all Task 021's job, not started
   here.
3. Extraction module's own RQ adoption, per ADR 0004's module-by-module
   rollout, remains unstarted.

---

# Out of Scope

- `modules/companies/**` — no changes. Specifically,
  `create_company`'s existing synchronous `WebsiteDiscoveryService.run_discovery`
  call (Task 015) is **not** touched or replaced by this task — that is
  Task 021's job, per ADR 0005.
- `modules/imports/**` — no changes. The bulk `POST /api/imports/storeleads`
  commit path gains no discovery auto-trigger in this task — that is
  also Task 021's job.
- `modules/crawling/**` and `modules/extraction/**` — no changes.
- Auto-chaining discovery-run completion into an automatically-enqueued
  crawl run — not attempted, not enabled by this task. The job wrapper
  function (`run_discovery_execution`) is deliberately left with no
  such hook — see the "Note for Task 021" callout above.
- A cancel or retry-failed endpoint for discovery runs — neither exists
  today and neither is added by this task.
- Any change to `DiscoveryRun`'s or `DiscoveredUrl`'s MongoDB schema —
  none needed; see "Options/config risk assessment" above for why no
  `options_snapshot`-equivalent field is required (unlike crawling's own
  post-evaluation amendment).
- `docker-compose.yml` / root `.gitignore` — not modified.
- `backend/app/config.py`, `backend/app/queue.py`, `pyproject.toml` —
  not modified; all already carry what this task needs from Task 017.
- Horizontal worker scaling (multiple `rq worker` processes), fair-share
  scheduling between the `"crawling"` and `"discovery"` queues, RQ job
  retries/backoff at the queue layer, RQ's dashboard/monitoring tooling
  — none needed for this vertical slice.
- Authentication/authorization on the worker process or Redis
  connection — consistent with this repository's existing accepted
  no-auth-yet posture.

---

# Suggested Implementation Order

1. Confirm `pyproject.toml`'s `redis`/`rq` dependencies,
   `backend/app/config.py`'s `REDIS_URL`, and `backend/app/queue.py`'s
   `get_redis_connection`/`get_queue` are already present and importable
   (all from Task 017) — no changes expected here, verify only.
2. `WebsiteDiscoveryService`: split `run_discovery` into
   `enqueue_discovery_run` + `execute_discovery_run` (keeping
   `run_discovery` as the composed wrapper, threading `cancellation_check`
   through unchanged). Run the full existing
   `test_discovery_service.py` and `test_processing_status_transitions.py`
   suites immediately after this step, unmodified, to confirm AC-05
   before touching anything else.
3. Add the new AC-03/AC-04 test functions to `test_discovery_service.py`.
4. `backend/app/modules/discovery/infrastructure/rq_jobs.py` — job
   wrapper function + `DISCOVERY_JOB_TIMEOUT` constant. Add
   `test_rq_jobs.py` (AC-06).
5. `backend/app/worker.py` — add `"discovery"` to `QUEUE_NAMES`, update
   its docstring.
6. `discovery/api/router.py` — `get_discovery_queue` DI accessor;
   update `create_discovery_run`; correct the module's own stale
   docstring (registered-in-`main.py`/synchronous-inline claims).
7. `backend/tests/integration/discovery/test_router_rq_enqueue.py` —
   `FakeQueue`, AC-01, AC-02.
8. Full local verification:
   `pytest backend/tests/unit/discovery backend/tests/integration/discovery`,
   `ruff check`, `pyright` on all new/changed paths.
9. Manual smoke test (recommended, not required — see Required Tests)
   against a real Redis + `rq worker` (serving both queues) + real
   MongoDB.
10. Final report: files created/changed, the job-timeout value chosen
    and why, confirmation that `run_discovery`'s existing test suite
    (including its `cancellation_check` test) passed unmodified, and
    the "Required follow-up" list above.

---

# Success Criteria

This feature is complete only when:

✓ AC-01 through AC-07 all pass

✓ Every test file listed under "Required Tests" exists and passes,
including the pre-existing `test_discovery_service.py` and
`test_processing_status_transitions.py` suites passing with zero
modification to their existing test bodies (only additions)

✓ `git diff --stat` touches only `backend/app/modules/discovery/**` and
`backend/app/worker.py`, and their own test directories — confirmed, no
cross-module changes, no frontend changes, no `docker-compose.yml`/
`.gitignore`/`app/config.py`/`app/queue.py`/`pyproject.toml` changes

✓ `ruff check` and `pyright` are clean on every new/changed path

✓ The "Required follow-up" list is reported, not silently built or
silently omitted

✓ No auto-chaining wiring (enqueue-on-create, enqueue-crawl-on-
discovery-completion) exists anywhere in the diff — confirmed absent,
per ADR 0005's explicit deferral to Task 021

✓ Evaluator reports PASS
