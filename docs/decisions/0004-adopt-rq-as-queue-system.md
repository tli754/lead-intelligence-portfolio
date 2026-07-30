# ADR 0004: Adopt RQ (+ Redis) as this repository's queue/background-job system

- Status: Accepted
- Date: 2026-07-29
- Feature: none scoped to this ADR alone. This is the foundational,
  repository-wide decision ADR 0003 explicitly deferred ("When
  Redis/a task queue is eventually scaffolded... this ADR's
  blocking-call conclusion for the bulk path should be revisited in a
  new ADR" —
  `docs/decisions/0003-auto-discovery-trigger-placement.md`). The
  first concrete feature built on this decision is the crawling
  vertical slice in `docs/contracts/active/017-rq-crawling-vertical-slice.md`;
  that contract designs the crawling-specific implementation, this ADR
  only authorizes the general choice of RQ + Redis.

## Context

No queue or worker system exists in this repository today. Every
pipeline stage (discovery, crawling, extraction) runs synchronously
inline from its own FastAPI route handler — confirmed directly by
reading `backend/app/modules/discovery/api/router.py`,
`backend/app/modules/crawling/api/router.py`, and
`backend/app/modules/extraction/api/router.py`, each of which carries
a comment to this effect. CLAUDE.md documents this as deliberate:
"Redis and background workers are deliberately not scaffolded yet —
nothing in the repository uses a queue."

`docs/decisions/0003-auto-discovery-trigger-placement.md` (Accepted,
2026-07-28) already reasoned through the cost of this gap for one
specific case — auto-triggering discovery after a bulk import — and
concluded that bolting a real-network-I/O pipeline stage onto a
bulk-create endpoint without a queue turns a sub-second "create
records" call into a multi-minute one, bounded by the slowest site
among N. It deliberately left the door open: once a queue exists,
that specific conclusion should be revisited "in a new ADR," not
amended in place.

Separately, on 2026-07-24 (before any code in this repository
existed), the verbal decision on the queue layer was Redis + Python
workers, with a pipeline of crawl → interpret → score as separate
queued jobs so scoring can rerun without re-crawling or re-hitting
OpenAI. That decision was never written into an ADR and nothing since
has confirmed or revisited it. This ADR is that write-up, revisited
against the codebase as it actually exists now (three built pipeline
modules, not zero).

Investigation findings, confirmed directly against source in this
repository as of this ADR:

- All three pipeline application services already take plain
  arguments, not FastAPI types, and are already documented as
  queue-ready by their own call sites:
  - `WebsiteDiscoveryService.run_discovery(self, company_id: str, *, cancellation_check: CancellationCheck | None = None) -> DiscoveryRun`
    (`backend/app/modules/discovery/application/website_discovery_service.py:73`).
  - `WebsiteCrawlService.start_crawl_run(self, company_id: str, discovery_run_id: str, options: CrawlRunOptions | None = None) -> CrawlRun`
    (`backend/app/modules/crawling/application/website_crawl_service.py:115`) —
    its module docstring states explicitly: "A future worker can call
    `start_crawl_run` exactly as the synchronous API route does."
  - `StructuredExtractionService.start_extraction_run(self, company_id: str, crawl_run_id: str, options: ExtractionRunOptions | None = None) -> ExtractionRun`
    (`backend/app/modules/extraction/application/structured_extraction_service.py:91`).
  No service-layer signature changes are needed anywhere to make these
  callable from a worker instead of a FastAPI route handler — this was
  a deliberate design choice made when each module was built, not
  something this ADR has to create.
- No backend "jobs" module exists. `frontend/src/pages/JobsPage.tsx`
  synthesizes a client-side "job" view by merging
  `GET /api/discovery-runs`, `/api/crawl-runs`, `/api/extraction-runs`
  and mapping each run's own status enum down to a shared 4-value
  `JobStatus` (`frontend/src/api/jobs.ts`). There is no `job_id`
  distinct from a run's own id, and no queue behind any of it. Task
  012's contract (`docs/contracts/completed/wire-jobs-page-to-pipeline-runs.md`)
  states outright: "there is no queue or worker system in this
  repository" — that line goes stale once RQ work lands, but nothing
  in this ADR changes `JobsPage` itself (see Consequences).
- `backend/app/config.py` has no `REDIS_URL` or queue-related setting
  today. `pyproject.toml` has no `rq` or `redis` dependency.
  `docker-compose.yml` runs only a `mongo` service — but the shared
  `/srv/infra` dev stack already runs Redis, confirmed reachable at
  `localhost:6379`. This exactly mirrors how this project already
  reuses a shared MongoDB instance instead of running its own
  `docker-compose.yml` Mongo service when one is already available
  (CLAUDE.md's "Local infra" section).

## Decision

1. Adopt **RQ** (the Python `rq` package) backed by **Redis** as this
   repository's general queue/background-job system — a foundational,
   repository-wide decision, not scoped to any single pipeline module.
   Any future feature that needs to move work off a synchronous
   request/response cycle should default to RQ unless a documented,
   specific reason argues otherwise.
2. Redis connectivity reuses the already-running shared `/srv/infra`
   dev stack at `localhost:6379`. No new `docker-compose.yml` service
   is added for Redis, following the exact precedent already set for
   MongoDB.
3. Rollout proceeds **one module at a time**, not all three pipeline
   stages simultaneously. **Crawling goes first** — it is the
   longest-running stage (sequential, rate-limited, real per-page
   network fetches; the crawling module's own contract documents a
   30-target run taking "at least ~30 seconds," with no fixed upper
   bound on `max_pages_per_company`), making it both the best
   candidate to validate the queue pattern end-to-end and the stage
   with the most to gain from not blocking an HTTP response on it.
   Discovery and extraction are untouched by this ADR and keep running
   synchronously inline until each gets its own follow-up contract to
   adopt RQ the same way, module by module.
4. This ADR does **not** reverse ADR 0003's conclusion that
   auto-triggering discovery must stay out of the bulk
   `POST /api/imports/storeleads` commit path. ADR 0003 itself
   anticipated that its conclusion should be revisited "in a new ADR"
   once a queue exists — that revisiting is deliberately deferred
   again here, to a future ADR scoped specifically to bulk-import
   auto-discovery once discovery itself is queued. Adopting RQ
   generally is a necessary precondition for that future ADR, not a
   substitute for writing it, and this ADR does not attempt to design
   it.
5. This ADR authorizes the *general* architectural decision only.
   Applying RQ to the crawling module specifically — where the queue
   connection factory lives, how the crawl-runs POST route changes,
   the worker entrypoint, and how the existing cancel/retry endpoints
   interact with a queued-but-not-yet-started job versus one already
   running — is designed in its own feature contract
   (`docs/contracts/active/017-rq-crawling-vertical-slice.md`), per
   CLAUDE.md's task workflow. This ADR does not itself change any
   code.

## Rationale

**Why RQ over Celery:**

- **Simplicity.** RQ is a thin queue built directly on Redis lists —
  no separate message broker to run, no result-backend configuration
  beyond the same Redis instance, no scheduler/beat process. This
  matches this repository's established preference for the smallest
  tool that solves the actual problem (e.g. Motor-only MongoDB access
  with no ORM; stdlib-only HTML cleaning in the crawling module,
  deliberately avoiding an `lxml`/`bs4` dependency per that module's
  own contract). Celery's model (task routing/queues-of-queues,
  canvases and chains, pluggable result backends, worker
  pools/concurrency models, an optional Beat scheduler) solves
  problems this repository does not have today, at the cost of
  meaningfully more configuration surface.
- **Matches this codebase's existing "one thing per call" synchronous
  pattern exactly.** Every pipeline application service —
  `run_discovery`, `start_crawl_run`, `start_extraction_run` — is
  already a single `async def` taking plain, JSON-serializable-shaped
  arguments (strings, small option objects) and doing one bounded unit
  of work end-to-end, deliberately built so "a future worker can call
  it identically" (verified directly in each module's own source/
  docstrings, see Context). RQ's execution model is: a worker dequeues
  one job, calls one Python callable with plain positional/keyword
  arguments, runs it to completion, dequeues the next. That is a
  1:1 match for the shape these services were already built in —
  zero impedance mismatch, no restructuring of business logic into a
  different concurrency/task-graph model. Celery would work too, but
  would be adopting more machinery than the actual shape of the
  problem calls for.
- **No need for scheduled/periodic jobs today.** Every pipeline stage
  in this repository is triggered by an explicit action (create a
  company, commit an import, POST a discovery/crawl/extraction run) —
  there is no cron-like "re-crawl every N hours" requirement in
  `docs/product/` or any task brief to date. Celery Beat's scheduling
  machinery would sit entirely unused. If a periodic job is ever
  genuinely needed, RQ has its own lightweight `rq-scheduler`
  add-on — that can be adopted then, on its own merits, rather than
  paying for scheduling complexity now on the chance it might be
  needed later.

**Why Redis via the shared `/srv/infra` stack, not a new compose
service:** identical reasoning already applied to MongoDB in this
repository — a shared instance is already running and reachable
(`localhost:6379`, confirmed), and running a second, competing Redis
container via this project's own `docker-compose.yml` would either
conflict on the port or introduce a redundant, divergent instance for
no benefit. `docker-compose.yml` is not modified by this ADR.

**Why crawling first, not discovery or extraction:** crawling is the
only one of the three stages whose own contract already documents
open-ended, potentially multi-minute run durations from real,
sequential, rate-limited network I/O per target — the exact shape of
work a synchronous HTTP request/response cycle should not be blocking
on. Discovery's own network I/O (robots.txt, sitemap(s), homepage
candidates) is comparatively bounded and it's a much smaller task
surface; extraction has no network I/O at all (it operates on already
-crawled content). Validating the RQ pattern once, on the stage with
the strongest incentive and the clearest existing evidence for the
problem, is lower-risk than rolling all three stages onto a new
mechanism at once.

## Consequences

- `pyproject.toml` gains `rq` and `redis` as explicit dependencies
  (both — not `rq` alone — since the queue connection factory needs
  `redis.Redis`/`redis.from_url` directly, not merely transitively via
  `rq`). This is designed concretely in the crawling contract, not
  built by this ADR.
- `backend/app/config.py`'s `Settings` gains a `REDIS_URL` field (and
  `.env.example` gains a matching documented line), following the
  exact pattern `MONGODB_URI` already established — the crawling
  contract specifies the exact default value and wiring.
- A new, small, cross-cutting module is added under `backend/app/`
  (sibling to `config.py`/`db.py`/`main.py`) to own the Redis
  connection/queue-accessor factory, mirroring `db.py`'s existing
  "one shared client factory, reused by every module" precedent — its
  exact name/shape is decided in the crawling contract, not this ADR,
  since this ADR does not touch code.
- Nothing changes yet for discovery or extraction — both keep running
  synchronously inline until each gets its own future contract
  following this ADR's precedent. `frontend/src/pages/JobsPage.tsx`
  and its synthesized job view are unaffected by this ADR directly;
  any staleness in its own or Task 012's documentation ("there is no
  queue or worker system in this repository") is a known, accepted
  side effect once the crawling contract lands, to be corrected as
  part of that contract's own documentation updates, not this ADR's.
- ADR 0003's bulk-import blocking-call conclusion stands, unchanged,
  until a future ADR — scoped specifically to auto-discovery once
  discovery itself is queued — revisits it. This ADR does not
  authorize wiring auto-discovery (or any other cross-module
  auto-chaining, e.g. crawl → extraction) into any bulk or
  single-record endpoint; that remains a separate, unscoped decision.
- The immediate, concrete follow-through on this ADR is
  `docs/contracts/active/017-rq-crawling-vertical-slice.md`, which
  must be implemented and evaluated before any second module (discovery
  or extraction) is queued — rollout is sequential, not parallelized
  across modules, per Decision #3.
