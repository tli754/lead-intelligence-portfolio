# Feature Contract: Task 009 — Wire Built Module Routers into the Live API

Task brief: `docs/execution-plans/tasks/009-Wire-Backend-Modules-into-Live-API.md`

# Feature

## Business Goal

`modules/imports`, `modules/crawling`, `modules/extraction`, and
`modules/evidence` each ship a complete, independently-tested
`api/router.py`, but none is registered in `backend/app/main.py`. Their
endpoints are unreachable over HTTP — the pipeline (import → discover →
crawl → extract → evidence) is fully built module-by-module but not
callable end to end. This task closes that gap for the backend only.

## User Story

As an operator of this system, I want the crawling, extraction,
evidence, and StoreLeads-import HTTP endpoints reachable on the running
API, so the pipeline that's already built and tested can actually be
invoked, without waiting on a frontend rework.

## Business Value

Unblocks manual/scripted end-to-end exercising of the pipeline (e.g.
via curl/Postman) ahead of the frontend integration task, and unblocks
any future worker/script that would call these HTTP endpoints instead
of importing the service classes directly.

# Architecture Impact

## Affected domains

None. No domain, application, or infrastructure code in any of the four
modules changes. This is composition-root wiring only.

## Affected services

None modified. `backend/app/main.py` (the composition root) is the only
file changed.

## Affected repositories

No repository code changes. `MongoCrawlRepository.ensure_indexes()`,
`MongoExtractionRepository.ensure_indexes()`, and
`MongoEvidenceRepository.ensure_indexes()` (all pre-existing, already
tested) are called from `main.py`'s `lifespan` hook, mirroring the
existing calls for `CompanyRepository`, `MongoCompanyRepository`, and
`MongoDiscoveryRepository`. `modules/imports` has no repository of its
own (verified: `grep -rl "AsyncIOMotorDatabase\|get_database"
backend/app/modules/imports/` returns nothing) — no index call needed
for it.

## Affected APIs

Newly reachable (previously built, unregistered):
- `modules/imports`: `POST /api/imports/storeleads/preview`,
  `POST /api/imports/storeleads`
- `modules/crawling`: `POST /api/companies/{company_id}/crawl-runs`,
  `GET /api/companies/{company_id}/crawl-runs/latest`,
  `GET /api/crawl-runs/{crawl_run_id}`,
  `GET /api/crawl-runs/{crawl_run_id}/targets`,
  `GET /api/crawl-runs/{crawl_run_id}/pages`,
  `GET /api/pages/{page_id}`,
  `POST /api/crawl-runs/{crawl_run_id}/cancel`,
  `POST /api/crawl-runs/{crawl_run_id}/retry-failed`
- `modules/extraction`: `POST /api/companies/{company_id}/extraction-runs`,
  `GET /api/companies/{company_id}/extraction-runs/latest`,
  `GET /api/extraction-runs/{extraction_run_id}`,
  `GET /api/extraction-runs/{extraction_run_id}/facts`,
  `GET /api/extraction-runs/{extraction_run_id}/candidates`,
  `GET /api/companies/{company_id}/facts`,
  `GET /api/facts/{fact_id}`,
  `GET /api/facts/{fact_id}/evidence`
- `modules/evidence`: `GET /api/evidence/{evidence_id}`

Verified no path collisions against already-registered routes (health
`/api`, companies-domain `/api/companies`, companies-module
`/api/companies/*`, discovery `/api/discovery-runs/*`,
`/api/companies/{company_id}/discovery-runs*`): every new path segment
(`crawl-runs`, `extraction-runs`, `facts`, `evidence`, `pages`,
`imports/storeleads`) is distinct from every already-registered one.

## Affected database collections

No new collections, no schema changes. `ensure_indexes()` for the three
newly-wired Mongo repositories creates indexes already defined in their
own modules (Task 006/007 scope) — this task only causes those
pre-existing methods to actually run at startup.

## Affected frontend pages

None. Explicitly out of scope per the scoping decision below.

# Cross-module dependency decisions

None to resolve — all five gateway/DI questions were already resolved
in Task 006's and Task 007's contracts. This task performs no new
cross-module wiring; it only registers routers whose internal DI
(`Depends(...)` factory functions defined in each module's own
`api/router.py`) already exists and is already tested via each module's
own integration tests (which build locally-scoped `FastAPI()` apps
containing just that module's router).

# Out of Scope (explicit, per user's scoping decision)

- Resolving `CompanyExtractionGateway`/`CompanyCrawlGateway`'s
  documented no-op methods (`update_latest_crawl_run`,
  `update_latest_extraction_run`, `project_latest_facts`) into real
  implementations. Both Task 006's and Task 007's contracts flag this
  as needing its own dedicated task (a `Company`/`CompanyProcessing`
  schema design decision: flattened vs. nested fact storage).
- Wiring `frontend/src/api/mock/` to any of these newly-live endpoints.
- Any change to `modules/discovery` or `modules/companies` (already
  registered, untouched).

# Implementation Tasks

**T1 — `backend/app/main.py`**: add four imports
(`from app.modules.imports.api.router import router as imports_router`,
similarly for `crawling_router`, `extraction_router`,
`evidence_router`), four `app.include_router(...)` calls (order:
existing four unchanged, then imports, crawling, extraction, evidence —
alphabetical-by-module among the new ones, matching the existing
alphabetical-by-module pattern for `companies_module_router`/
`discovery_router`), and three `MongoCrawlRepository(get_database())
.ensure_indexes()` / `MongoExtractionRepository(get_database())
.ensure_indexes()` / `MongoEvidenceRepository(get_database())
.ensure_indexes()` calls inside the `lifespan` context manager,
following the exact same construction pattern as the three existing
`ensure_indexes()` calls there.

# Acceptance Criteria

- AC-01: `GET /openapi.json` against the running app (or
  `TestClient(app).get("/openapi.json")`) lists all 13 newly-registered
  paths listed under "Affected APIs" above, in addition to every
  already-registered path.
- AC-02: No path listed under "Affected APIs" collides (same path +
  method) with any pre-existing registered route.
- AC-03: `backend/tests/` full suite (excluding the pre-existing,
  already-documented-stale `backend/tests/modules/companies/**` and
  `backend/tests/test_company_module_api.py`, per CLAUDE.md's "Known
  stale" note — unrelated to this task) passes, including
  `backend/tests/test_health.py` and
  `backend/tests/test_company_import.py`, which use the shared
  `app.main.app` instance and must be unaffected by the newly-added
  routers.
- AC-04: Each module's own existing unit/integration suite
  (`backend/tests/unit/{crawling,extraction,evidence,imports}`,
  `backend/tests/integration/{crawling,extraction,evidence,imports}`)
  still passes unmodified — this task does not touch any file under
  those paths or under any module's `domain/`, `application/`, or
  `infrastructure/` directories.
- AC-05: `git diff --stat` shows exactly one file changed:
  `backend/app/main.py`.
- AC-06: Starting the app (`uvicorn app.main:app`) against a reachable
  MongoDB does not raise on startup — `ensure_indexes()` for all six
  repositories (three pre-existing + three newly added) completes
  without error.
- AC-07: No `BackgroundTasks` introduced — this task adds no new route
  handlers, only registers existing ones verbatim.

# Required Tests

No new test files required (AC-03/AC-04 are regression checks against
existing suites — this task adds no new behavior of its own to test).
If desired as a light integration confirmation, a single assertion in
an existing or new smoke test that `app.main.app`'s OpenAPI schema
contains all 13 new paths satisfies AC-01 directly; this is optional
and left to the generator's judgment given the task's small size.

# Risks

- **Risk**: registering `modules/crawling`'s router pulls in
  `LocalFilesystemContentStorage`, which lazily creates directories on
  write (`path.parent.mkdir(parents=True, exist_ok=True)`) — no risk at
  import/registration time, only at actual crawl-run time, out of this
  task's scope to exercise.
  **Mitigation**: none needed; verified by reading
  `local_filesystem_content_storage.py` — no eager filesystem access at
  construction.
- **Risk**: `ensure_indexes()` calls could fail at startup if MongoDB is
  unreachable, taking down app startup entirely.
  **Mitigation**: this is the exact same failure mode the three
  existing `ensure_indexes()` calls already have — not a new risk
  introduced by this task, and consistent with this repo's established
  pattern (fail fast at startup rather than serve with missing
  indexes).

# Dependencies

None outside this task's own scope. All four modules' code, DI
factories, and Mongo repositories already exist and are already tested
(Tasks 004/005/006/007).

# Suggested Implementation Order

1. Add the four router imports and `include_router` calls.
2. Add the three new `ensure_indexes()` calls to `lifespan`.
3. Run the full backend suite (respecting the documented `--ignore`
   flags for known-stale paths) and confirm no regressions.
4. Manually inspect `app.main.app.openapi()["paths"]` (or run the app
   and hit `/openapi.json`) to confirm all 13 new paths are present and
   no path collides.

# Success Criteria

All acceptance criteria pass; `backend/app/main.py` is the only file
changed; the evaluator confirms scope discipline and no regressions in
any module's own test suite.
