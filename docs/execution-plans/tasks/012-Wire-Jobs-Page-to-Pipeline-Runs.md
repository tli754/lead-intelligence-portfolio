Task 012 — Add cross-company pipeline-run listing and wire the jobs page

Raised in conversation (not a pre-written brief), preserved here verbatim
as the record of what was actually asked. Third of three follow-up tasks
(010, 011, 012) — see Task 010 for shared context.

Investigation finding this task is built on: there is no queue or
background-worker system in this repository (CLAUDE.md is explicit that
Redis and workers are "deliberately not scaffolded yet"), so
`JobsPage`'s mock concept of a job (stage: discovery/crawl/extraction/
analysis/scoring, status: queued/running/succeeded/failed) has no
literal backend equivalent and cannot be fully real in this task. What
does exist, per module, is a run record (`DiscoveryRun`, `CrawlRun`,
`ExtractionRun`) with its own status enum — but every existing read
endpoint for these is scoped to one company
(`get_latest_run_for_company`, `list_runs_by_company`); none of
`modules/discovery`, `modules/crawling`, `modules/extraction` currently
expose a "list runs across all companies" endpoint, which is what a
jobs table needs.

Ask, concretely: add a small, paginated, filterable "list all runs"
capability to each of the three pipeline modules (mirroring
`modules/companies`'s existing `list_companies` pattern), and wire
`JobsPage` to merge those three real endpoints into its existing `Job`
view. `analysis` and `scoring` stages stay absent from the list — those
modules don't exist yet (Task 008 covers analysis; scoring is
unplanned) — `JobsPage` must tolerate a partial stage set rather than
assuming all five are present.

Recommended build order (checkpoint / commit after each numbered step,
specifically so a generator session that runs out of tokens mid-way
leaves a working, testable state behind rather than a half-edited
module — this is exactly what went wrong on Task 007):

1. `modules/discovery`: add `list_runs(status=None, page, page_size)` to
   `domain/repository.py`'s interface, implement in
   `infrastructure/mongo_discovery_repository.py`, add
   `GET /api/discovery-runs` to `api/router.py`. Unit + integration
   tests.
2. `modules/crawling`: same shape, `GET /api/crawl-runs`. Unit +
   integration tests.
3. `modules/extraction`: same shape, `GET /api/extraction-runs`. Unit +
   integration tests.
4. Frontend: real jobs client that calls the three endpoints, maps each
   module's run status enum to the frontend's `JobStatus`
   (`queued`/`running`/`succeeded`/`failed` — check each module's actual
   `*Status` enum values in `domain/enums.py` before assuming a 1:1
   mapping; some may need a documented merge, e.g. a crawl's
   `partial_failure` collapsing to `failed` or a new frontend status),
   merges and sorts client-side (`queued_at` descending, matching the
   mock's default), and replaces `fetchJobs` in `src/api/queries.ts`.

Allowed paths:

- backend/app/modules/discovery/domain/repository.py,
  infrastructure/mongo_discovery_repository.py, api/router.py,
  api/schemas.py
- backend/app/modules/crawling/domain/repository.py,
  infrastructure/mongo_crawl_repository.py, api/router.py, api/schemas.py
- backend/app/modules/extraction/domain/repository.py,
  infrastructure/mongo_extraction_repository.py, api/router.py,
  api/schemas.py
- backend/tests/unit/{discovery,crawling,extraction}/**,
  backend/tests/integration/{discovery,crawling,extraction}/** — only
  tests covering the new `list_runs` method/endpoint
- frontend/src/api/jobs.ts (new client file) or frontend/src/api/companies.ts
  if a shared client file is preferred
- frontend/src/api/queries.ts
- frontend/src/pages/JobsPage.tsx and its test file
- frontend/src/schemas/job.ts — only to relax fields the real endpoints
  can't supply (see below)

Do not modify:

- frontend/src/pages/CompaniesPage.tsx, frontend/src/pages/CompanyDetailPage.tsx
- frontend/src/api/mock/** (fine to leave in place even after this task
  — CompaniesPage/CompanyDetailPage no longer use it after Tasks 010/011,
  but deleting the mock layer entirely is a separate cleanup, not this
  task)
- application/domain business logic of any of the three modules beyond
  adding the one read method each — no behavior changes to how runs are
  created, transitioned, or crawled/extracted/discovered
- backend/app/main.py (the three routers are already registered; the
  new endpoints just add routes to existing routers)

Known shape gaps:

- `company_domain` on the frontend's `Job` type — none of the three run
  records carry the company's domain directly, only `company_id`. Either
  add a denormalized `company_domain` snapshot field to each run record
  (bigger change, avoid unless cheap) or have the frontend resolve it via
  the companies list already fetched for Task 010 — prefer the latter.
- `job_id` — use each module's own run id (`discovery_run_id`,
  `crawl_run_id`, `extraction_run_id`) as the frontend `job_id`; no new
  id concept needed.
- Real "queued" vs "running" distinction may not exist identically across
  all three modules' status enums — check before assuming symmetry;
  document any module where the mapping is lossy.

Out of scope:

- Any real queue, worker, retry-scheduling, or job-cancellation UI beyond
  what already exists (`crawling` already has `/cancel` and
  `/retry-failed`; do not extend that surface here).
- Analysis/scoring stages — not buildable until Task 008 (analysis) and
  an eventual scoring module exist.
- Companies-list and company-detail wiring (Tasks 010 and 011).
