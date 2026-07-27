# Feature Contract: Task 012 — Add cross-company pipeline-run listing and wire the jobs page

Task brief: `docs/execution-plans/tasks/012-Wire-Jobs-Page-to-Pipeline-Runs.md`

Independent of Tasks 010/011 — no shared code dependency, though reusing
Task 010's company id -> domain lookup (already fetched for the
companies list) is the recommended approach for the `company_domain`
gap below, so building this after Task 010 is preferable but not
required.

# Feature

## Business Goal

`JobsPage` renders `mock/fixtures.ts` job records with no real backend
equivalent — there is no queue or worker system in this repository.
What does exist are per-company run records in three pipeline modules
(`DiscoveryRun`, `CrawlRun`, `ExtractionRun`), each already exposing
single-company read endpoints but no cross-company listing. This task
adds that listing (mirroring `modules/companies`'s existing
`list_companies` pattern) and wires `JobsPage` to it.

## User Story

As a user of the JobsPage, I want to see real discovery/crawl/extraction
runs across all companies, so I can see what the pipeline has actually
done, instead of a static mock table.

## Business Value

Third of three steps (010/011/012). Gives the first real operational
visibility into pipeline activity without needing a queue/worker system
(explicitly out of scope for this repository right now).

# Architecture Impact

## Affected domains

`discovery`, `crawling`, `extraction` — each gains exactly one new
domain-repository method (`list_runs`) and its Mongo implementation. No
change to how runs are created or transitioned.

## Affected services

None (`WebsiteDiscoveryService`/`WebsiteCrawlService`/
`StructuredExtractionService` unchanged — this is a pure read addition
at the repository/router layer).

## Affected repositories

- `discovery/domain/repository.py` (interface) +
  `discovery/infrastructure/mongo_discovery_repository.py`: add
  `async def list_runs(self, status: DiscoveryStatus | None, page: int,
  page_size: int) -> PagedResult[DiscoveryRun]` (or this module's
  existing paged-result convention — check how
  `list_discovered_urls`/other paginated methods in this file return
  results and match it exactly).
- `crawling/domain/repository.py` + `mongo_crawl_repository.py`: same
  shape, `list_runs(status: CrawlStatus | None, page, page_size)`. This
  module already has `list_runs_by_company` — model the new method on
  its exact query/sort/pagination pattern, just without the
  `company_id` filter.
- `extraction/domain/repository.py` + `mongo_extraction_repository.py`:
  same shape, `list_runs(status: ExtractionStatus | None, page,
  page_size)`, modeled on the existing `list_runs_by_company`.

All three sort by `created_at` descending (matches "Queued" column
sorting expectation on `JobsPage`, and matches `created_at` being the
closest existing field to "queued at" — none of the three run models
have a dedicated `queued_at`; see mapping table below).

## Affected APIs

New:
- `GET /api/discovery-runs?status=&page=&pageSize=` ->
  `DiscoveryRunListResponse` (new schema, sibling to the existing
  `DiscoveryRunEnvelope`)
- `GET /api/crawl-runs?status=&page=&pageSize=` -> `CrawlRunListResponse`
- `GET /api/extraction-runs?status=&page=&pageSize=` ->
  `ExtractionRunListResponse`

No path collisions: verified against `docs/contracts/completed/
wire-modules-into-live-api.md`'s registered-path list — `/api/discovery-
runs`, `/api/crawl-runs`, `/api/extraction-runs` (bare, no path param)
are currently unregistered; only `/api/discovery-runs/{id}`,
`/api/crawl-runs/{id}`, `/api/extraction-runs/{id}` exist today, which
are distinct routes from the new bare-path ones under FastAPI's routing
(different path templates, same prefix is fine).

## Affected database collections

None — same collections (`discovery_runs`, `crawl_runs`,
`extraction_runs`), new query pattern (unfiltered by `company_id`) using
existing indexes where possible. If `list_runs` needs a `status`-only
index not already present, add it to that module's `ensure_indexes()`
and note it in the PR — do not skip index coverage for a
production-shaped query.

## Affected frontend pages

`JobsPage.tsx` (data source only — filters/table/columns unchanged).

# Cross-module dependency decisions

None — the three additions are symmetric, independent, single-module
changes. No new gateway/DI wiring; `list_runs` is a same-module
repository method exposed by that module's own already-registered
router.

# Field & Status Mapping (binding on the implementation)

Run-model field -> `Job` field, identical across all three modules
(none has a dedicated `queued_at`; `created_at` is the closest
equivalent — the run document is created at enqueue time, before
`started_at` is set):

| Job field       | Run model field |
|-----------------|------------------|
| `job_id`        | `{discovery,crawl,extraction}_run_id` |
| `company_id`    | `company_id` |
| `company_domain`| not on the run — resolve client-side via the companies list (Task 010's already-fetched data, or a dedicated lookup if Task 010 hasn't landed) |
| `stage`         | literal `"discovery"` / `"crawl"` / `"extraction"` per source endpoint |
| `queued_at`     | `created_at` |
| `started_at`    | `started_at` |
| `finished_at`   | `completed_at` |
| `error_message` | `error` |

Status mapping (frontend `JobStatus` has exactly 4 values: `queued`,
`running`, `succeeded`, `failed` — every backend enum has more, so this
mapping is necessarily lossy; document it exactly as follows, do not
improvise per-module):

- `queued` -> `queued`
- `running` -> `running`
- `completed` -> `succeeded`
- `completed_with_warnings` -> `succeeded` (the frontend has no
  "succeeded with warnings" state; the run did complete — surface the
  nuance, if desired, via `error_message` being non-null even on a
  "succeeded" row, rather than inventing a new `JobStatus` value)
- `partial` (crawl, extraction) -> `succeeded` (same reasoning — the run
  finished; `error_message` can carry a note)
- `failed` -> `failed`
- `cancelled` (crawl, extraction) -> `failed` (closest existing bucket;
  a cancelled run did not produce a usable result)
- `stale` (extraction only) -> `succeeded` (the run completed
  successfully; staleness is about the *result* being superseded later,
  not the run's own outcome — do not conflate with `failed`)

If this mapping feels lossy enough to be misleading during
implementation, that's expected and acceptable for this task's scope —
flag it in the PR notes rather than expanding `JobStatus` to 8+ values,
which would be a larger frontend schema change outside this task.

# Out of Scope Reaffirmed

- Real queue/worker/retry infrastructure.
- `analysis`/`scoring` stages (no backend module exists for either).
- Extending `crawling`'s existing `/cancel`/`/retry-failed` actions to
  `JobsPage`'s UI (read-only view only, matching the mock's current
  read-only behavior and the existing `JobsPage.tsx` docstring: "Read-
  only view of the pipeline job queue").

# Implementation Tasks

**T1 — `modules/discovery`**: add `list_runs` to
`domain/repository.py`'s `DiscoveryRepository` protocol, implement in
`infrastructure/mongo_discovery_repository.py`, add
`DiscoveryRunListResponse` to `api/schemas.py`, add
`GET /api/discovery-runs` to `api/router.py`. Unit test (repository, if
this module tests repositories directly — check existing pattern) +
integration test (real Mongo, via `backend/tests/integration/discovery`).
Commit.

**T2 — `modules/crawling`**: same shape as T1, `GET /api/crawl-runs`.
Commit independently of T1's commit.

**T3 — `modules/extraction`**: same shape as T1, `GET /api/extraction-
runs`. Commit independently.

**T4 — Frontend real jobs client**: `listDiscoveryRuns`,
`listCrawlRuns`, `listExtractionRuns` client functions; a
`fetchPipelineJobs(filters: JobListFilters): Promise<JobListResponse>`
that calls whichever of the three are implied by `filters.stage` (or all
three if unset), maps each via the Field & Status Mapping table, resolves
`company_domain` (see mapping table), merges, sorts by `queued_at`
descending, and paginates/limits consistently with the mock's current
behavior.

**T5 — Wiring**: `frontend/src/api/queries.ts`'s `useJobs` switches from
`fetchJobs` (mock) to `fetchPipelineJobs` (real).

# Acceptance Criteria

- AC-01: `GET /api/discovery-runs`, `GET /api/crawl-runs`,
  `GET /api/extraction-runs` each return paginated results across all
  companies, filterable by `status`, sorted by `created_at` descending.
- AC-02: None of the three new routes collides with any existing
  registered route (verify via `app.main.app.openapi()["paths"]`, same
  method as Task 009's AC-01/AC-02).
- AC-03: `JobsPage` renders real discovery/crawl/extraction runs; stage
  filter for `analysis`/`scoring` yields an empty result set (not an
  error) since no backend data can ever exist for those stages yet.
- AC-04: Every real run's status maps to exactly one of `queued`/
  `running`/`succeeded`/`failed` per the mapping table — no unmapped
  status reaches `JobStatusBadge` (which would presumably throw or
  render undefined on an unrecognized key; verify its current behavior
  before relying on this).
- AC-05: `company_domain` resolves correctly for a run whose company
  exists; a run whose company was deleted after the run was created
  (edge case) renders a documented fallback (e.g. the raw `company_id`)
  rather than crashing the page.
- AC-06: `git diff --stat` for backend changes touches only the three
  modules' `domain/repository.py`, `infrastructure/mongo_*_repository.py`,
  `api/schemas.py`, `api/router.py`, and their own test directories — no
  cross-module changes, no `main.py` changes (routes are added to
  already-registered routers).
- AC-07: Each module's full existing unit/integration suite still
  passes unmodified apart from the new test files added for `list_runs`.
- AC-08: `pnpm run test` passes for `JobsPage.test.tsx` and any new test
  files (T4's composition/mapping functions).

# Required Tests

- Backend, per module (discovery/crawling/extraction): `list_runs` with
  no filter (all runs, paginated), with a `status` filter, with zero
  matching runs, sort-order assertion. Integration test hitting the new
  route end to end with a real Mongo-backed repository.
- Frontend: unit tests for the status-mapping function (every enum value
  from all three modules maps to exactly one `JobStatus`, per the table
  above — this table is the test's source of truth), the `company_domain`
  resolution (found vs. not-found company), and merge/sort-across-three-
  sources behavior.

# Risks

- **Risk**: lossy status mapping (`completed_with_warnings`, `partial`,
  `cancelled`, `stale` all folding into `succeeded`/`failed`) could hide
  operationally-relevant nuance from a user scanning the jobs table.
  **Mitigation**: explicitly accepted for this task's scope (see mapping
  table); `error_message` remains a place to surface it; documented as a
  known simplification, not silently dropped.
- **Risk**: unfiltered `list_runs` queries (no `company_id`) may need a
  new index depending on existing index coverage per module.
  **Mitigation**: AC-07 requires each module's own test suite (including
  any index-dependent query-plan assumptions) to still pass; add an index
  via `ensure_indexes()` if profiling/`explain()` during implementation
  shows a full collection scan for the `status`-filtered case.
- **Risk**: three near-identical repository/router changes across three
  modules increases the chance of copy-paste drift (e.g. one module's
  pagination response shape subtly differing from the others').
  **Mitigation**: T1 (discovery) should be treated as the reference
  implementation; T2/T3 should be reviewed for structural parity with T1
  before considering the task done, not just independently correct.

# Dependencies

None blocking. Soft dependency on Task 010 for `company_domain`
resolution reuse only.

# Suggested Implementation Order

Exactly the four steps in the task brief's "Recommended build order",
each committed independently so a token-exhausted session leaves a
working state:

1. T1 (`modules/discovery`) — reference implementation, commit.
2. T2 (`modules/crawling`) — commit.
3. T3 (`modules/extraction`) — commit.
4. T4 (frontend client + mapping) — commit.
5. T5 (wire `useJobs`) — commit last, only after T1-T4 are each green.

# Success Criteria

All acceptance criteria pass; `git diff --stat` confined to the allowed
paths in the task brief; T1/T2/T3 are structurally symmetric; evaluator
confirms the status-mapping table was followed exactly (not improvised
per-module) and that `analysis`/`scoring` stages are handled as empty
results rather than errors or fabricated data.
