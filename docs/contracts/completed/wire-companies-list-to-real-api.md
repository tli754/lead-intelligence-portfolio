# Feature Contract: Task 010 — Wire the companies list page to the real backend API

Task brief: `docs/execution-plans/tasks/010-Wire-Companies-List-to-Real-API.md`

# Feature

## Business Goal

`CompaniesPage` currently renders `frontend/src/api/mock/fixtures.ts` via
`useCompanies` -> `fetchCompanies` (`frontend/src/api/mock/client.ts`).
The real `GET /api/companies` endpoint (`modules/companies`, registered
in `main.py` since Task 009) is live, tested, and backed by MongoDB, but
nothing in the frontend calls it. This task swaps the list page onto
real data.

## User Story

As a user of the CompaniesPage, I want to see companies actually stored
in the database (created via the `modules/companies` API directly — see
"Known Limitation" below for why the paste-in importer doesn't qualify
yet), not a fixed set of mock fixtures, so the page reflects real system
state for that path.

## Known Limitation (found during evaluation, binding on this contract)

`ImportPage`'s paste-in importer calls `POST /api/companies/import`,
which belongs to `backend/app/domains/companies` (the older, flat
`Company` model, collection `companies`) — a *different* module and
collection from `backend/app/modules/companies` (the hexagonal model,
collection `companies_pipeline`) that `GET /api/companies` and this
task's `CompaniesPage` wiring read from. `docs/product/lead-definition.md`
already documents this split as deliberate: "nothing currently promotes
a record from model 1 into model 2 — they are populated independently."
As a result, a company pasted in via `ImportPage` will **not** appear on
the now-real `CompaniesPage` — only companies created via
`POST /api/companies` (`modules/companies`) will. Reconciling the two
`Company` models/collections is a separate, larger architectural task,
intentionally out of scope here; see
`docs/execution-plans/tasks/013-Reconcile-Domains-and-Modules-Companies.md`.

## Business Value

First of three steps (010/011/012) toward a fully real frontend. Unblocks
manual verification that companies created via `modules/companies`'s API
actually show up in the UI — currently there is no real page to see them
on. Does **not** yet unblock verification of `ImportPage`'s paste-in
importer specifically; see "Known Limitation" above.

# Architecture Impact

## Affected domains

None. No backend domain/application logic changes.

## Affected services

None. `CompanyService.list_companies` (already implemented, already
tested) is the only backend code path exercised.

## Affected repositories

None (`MongoCompanyRepository` unchanged).

## Affected APIs

`GET /api/companies` — unchanged behavior. One additive schema change:
`CompanyListItemResponse` (`backend/app/modules/companies/api/schemas.py`)
gains `updated_at` (camelCase `updatedAt` on the wire), sourced from
`Company.updated_at`, following the exact same `.isoformat()` pattern
already used in `company_to_response`. `company_to_list_item` gets one
new line; no other field, route, or status code changes.

## Affected database collections

None.

## Affected frontend pages

`CompaniesPage.tsx` — swaps its data source; no layout/component changes
anticipated beyond what's needed to render fields that may legitimately
be absent (see gaps below).

# Cross-module dependency decisions

None — this task touches exactly one backend module (`companies`) and
the frontend; no gateway/DI questions.

# Known Shape Gaps (binding on the implementation)

1. **Envelope mismatch.** Backend: `{data: [...], pagination: {page,
   pageSize, total}}`. Frontend `companyListResponseSchema` expects
   `{items: [...], total}`. Resolve entirely in the new frontend client
   function (map `data` -> `items`, `pagination.total` -> `total`) — do
   not change the backend envelope, `modules/imports` and other future
   consumers may depend on the existing shape.
2. **Flat vs. nested list item.** Backend's `CompanyListItemResponse` is
   flat (`companyName`, `platform`, `country`, `city`, `processingStatus`,
   `workflowStatus`, `opportunityScore`, `confidence`, `mainReason`,
   `updatedAt` after this task). Frontend's `CompanyListItem` nests
   `identity: {company_name, platform, country, city}`,
   `processing: {status, latest_discovery_run, latest_crawl_run,
   latest_extraction_run, latest_analysis_run, latest_scoring_run,
   failure_reason}`, `workflow: {manual_status, shortlisted,
   notes_count}`. The adapter must:
   - Build `identity` from the four flat fields directly.
   - Build `processing` with `status` from `processingStatus` and every
     other field (`latest_*_run`, `failure_reason`) set to `null` — the
     list endpoint doesn't return them and this task does not add them
     (that would require joining run collections into the list query,
     out of scope).
   - Build `workflow` with `manual_status` from `workflowStatus`,
     `shortlisted: workflowStatus === "shortlisted"` (a derived,
     best-effort boolean — not a real stored field), `notes_count: 0`
     (not returned; there is no notes feature yet in this repo at all).
   - `score` <- `opportunityScore` (already always `null` today).
   - `confidence` <- `confidence` (already always `null` today,
     and already typed as the same `ConfidenceLevel | null` shape on
     both sides — no mapping needed beyond the rename).
3. **Enum coverage.** `frontend/src/schemas/company.ts`'s
   `processingStatusSchema` is missing `discovered`, `crawled`,
   `extracted`, `analysed`, `partial`; `workflowStatusSchema` is missing
   `archived`. Both must be extended to match
   `backend/app/modules/companies/domain/enums.py`'s `ProcessingStatus`/
   `WorkflowStatus` exactly, or real companies sitting in one of those
   states fail Zod parsing and the whole list request throws.
4. **Filters.** `CompanyListFilters.sort`/`.q` (frontend) have no backend
   equivalent (`GET /api/companies` supports `processingStatus`,
   `workflowStatus`, `platform`, `country`, `page`, `pageSize` only — no
   free-text search, no sort). Drop `sort`/`q` from the outgoing request
   in the new client function. Do not implement client-side sort/filter
   as a substitute — leave `CompaniesPage`'s sort/search UI inert or
   hidden if it currently assumes server-side behavior; report as a
   follow-up gap rather than papering over it.

# Implementation Tasks

**T1 — Backend**: add `updated_at: str` to `CompanyListItemResponse`
(`backend/app/modules/companies/api/schemas.py`), populate it in
`company_to_list_item` via `company.updated_at.isoformat()`. Update the
one existing unit test asserting `CompanyListItemResponse`'s field set
(`backend/tests/unit/companies/test_api_schemas.py`) and any integration
snapshot test under `backend/tests/integration/companies/test_list_companies.py`
that asserts the full response body.

**T2 — Frontend client**: add a `listCompanies(filters:
CompanyListFilters): Promise<CompanyListResponse>` function (in
`frontend/src/api/companies.ts`, following `importCompanies`'s existing
`fetch()`/`API_BASE_URL`/error-handling pattern) that calls
`GET /api/companies` with query params built from `processing_status`,
`workflow_status`, `platform` (mapped to the backend's camelCase query
param names: `processingStatus`, `workflowStatus`, `platform`,
`country`, `page`, `pageSize`), parses the response with
`companyListResponseSchema` after applying the T3 adapter, and throws a
typed error on non-2xx (mirroring `ImportRequestError`).

**T3 — Adapter**: a pure function mapping one `CompanyListItemResponse`
(camelCase, flat) to one `CompanyListItem` (snake_case at the TS-type
level per existing schema convention, nested) per the "Known Shape Gaps"
section above. Unit-testable in isolation.

**T4 — Schema fixes**: extend `processingStatusSchema`/
`workflowStatusSchema` in `frontend/src/schemas/company.ts` with the
missing enum values listed above.

**T5 — Wiring**: `frontend/src/api/queries.ts`'s `useCompanies` switches
its `queryFn` from `fetchCompanies` (mock) to the new `listCompanies`
(real). `CompaniesPage.tsx` needs no logic changes if `CompanyListItem`'s
shape is preserved exactly by the T3 adapter — if any UI code currently
assumes `sort`/`q` are server-applied, adjust per the "Filters" gap
above.

# Acceptance Criteria

- AC-01: `GET /api/companies` response includes `updatedAt` on every
  list item, ISO-8601 formatted, matching `Company.updated_at`.
- AC-02: `CompaniesPage` renders companies created via
  `POST /api/companies` (`modules/companies`, real MongoDB data in the
  `companies_pipeline` collection), not `mock/fixtures.ts` data —
  verified by creating a company through that endpoint and confirming it
  appears on `CompaniesPage` without a page reload assumption beyond
  normal query invalidation. Per the "Known Limitation" above, a company
  created via `ImportPage`'s paste-in importer is explicitly **not**
  required to appear — that's a separate, already-documented gap between
  `domains/companies` and `modules/companies`, not a regression
  introduced by this task.
- AC-03: A company in any of `ProcessingStatus`'s 14 values (including
  the 5 the frontend schema was missing) and any of `WorkflowStatus`'s 7
  values (including `archived`) renders without a Zod validation error.
- AC-04: `score`/`confidence` render as "not available"/"unscored" (or
  equivalent existing empty-state UI) — not `0`, not blank, not a thrown
  error.
- AC-05: Pagination controls (if present in `CompaniesPage`) correctly
  reflect `pagination.total`/`page`/`pageSize` from the real response.
- AC-06: `frontend/src/api/mock/**` is untouched and still exports
  working mock functions (still used by `CompanyDetailPage` and
  `JobsPage` until Tasks 011/012).
- AC-07: Existing backend companies-module test suite
  (`backend/tests/unit/companies`, `backend/tests/integration/companies`)
  passes with the `updated_at` addition reflected in any assertions that
  enumerate the full response shape.
- AC-08: `pnpm run test` (Vitest) passes for `CompaniesPage.test.tsx` and
  any new test file for the T3 adapter.

# Required Tests

- Backend: extend `backend/tests/unit/companies/test_api_schemas.py`
  (assert `updatedAt` present and correctly formatted) and
  `backend/tests/integration/companies/test_list_companies.py` (assert
  the field on a real persisted company).
- Frontend: unit tests for the T3 adapter covering (a) a company with
  every optional field present, (b) a company with all-null optional
  fields, (c) each of the newly-added enum values round-tripping through
  Zod parsing without error. Update `CompaniesPage.test.tsx` to mock the
  real client function instead of the mock module (or keep MSW/fetch
  mocking if that's the test's existing pattern — check the current test
  file before choosing).

# Risks

- **Risk**: `CompaniesPage.test.tsx` may currently import from
  `src/api/mock/client.ts` directly for test setup; swapping the query
  hook's dependency could break test mocking if done carelessly.
  **Mitigation**: inspect the existing test file first; keep the test
  passing by updating what it mocks, not by changing `CompaniesPage`'s
  public behavior.
- **Risk**: silently dropping `sort`/`q` support could look like a
  regression to a user comparing before/after.
  **Mitigation**: AC-05/the Filters gap note require this to be reported
  explicitly, not silently absorbed.

# Dependencies

None outside this task. `GET /api/companies` already exists and is
already tested (companies module, pre-Task-010 work).

# Suggested Implementation Order

1. T1 (backend `updated_at` addition) — small, independently testable,
   commit first.
2. T4 (frontend enum fixes) — small, independently testable, commit
   second; unblocks T3 without needing the real client yet.
3. T3 (adapter, unit-tested against fixtures shaped like real API
   responses).
4. T2 (real client function using the T3 adapter).
5. T5 (wire `useCompanies` to the real client) — commit last, after
   T1-T4 are each independently green.

# Success Criteria

All acceptance criteria pass; `git diff --stat` shows changes confined
to the allowed paths in the task brief; `frontend/src/api/mock/**`
remains functionally intact for `CompanyDetailPage`/`JobsPage`; evaluator
confirms no regressions in the companies-module backend suite or the
existing frontend test suite.
