Task 010 — Wire the companies list page to the real backend API

Raised in conversation (not a pre-written brief), preserved here verbatim
as the record of what was actually asked, per CLAUDE.md's Task workflow.

Context: the user asked whether the frontend still uses mock data.
Investigation showed `CompaniesPage`, `CompanyDetailPage`, and `JobsPage`
all read through `frontend/src/api/queries.ts`, which imports
`fetchCompanies`/`fetchCompanyById`/`fetchJobs` from
`frontend/src/api/mock/client.ts` — none are wired to the live
`modules/companies` API (registered in `main.py` since Task 009), even
though that API works and has passing integration tests. The user then
asked what it would take to wire it up, and — after a scoping
discussion — asked to split the work into small tasks and generate
task-brief documents up front, so a generator agent has something to
resume from if a build session runs out of tokens mid-way (as happened
during Task 007).

This is the first and smallest of three follow-up tasks (010, 011, 012)
covering: companies list, company detail + evidence, and a real jobs/
pipeline-runs view, respectively.

Ask, concretely: make `CompaniesPage` display real data from
`GET /api/companies` instead of `src/api/mock/fixtures.ts`.

Allowed paths:

- frontend/src/api/companies.ts (extend with a list-companies client
  function, or add a sibling file if that reads cleaner)
- frontend/src/api/queries.ts
- frontend/src/pages/CompaniesPage.tsx and its test file
- frontend/src/schemas/company.ts — two known, narrow changes: (1) a
  field needing to move from required to optional/nullable to match what
  the real API actually returns, and (2) `processingStatusSchema`/
  `workflowStatusSchema` are missing enum values the backend can
  genuinely return (`discovered`, `crawled`, `extracted`, `analysed`,
  `partial` for processing status; `archived` for workflow status — see
  `backend/app/modules/companies/domain/enums.py`) and must be extended
  to match, or every company sitting in one of those states will fail
  frontend Zod validation. Do not redesign the schema beyond these two
  changes.
- backend/app/modules/companies/api/schemas.py and
  backend/app/modules/companies/api/router.py — narrowly, only to add
  `updated_at` to `CompanyListItemResponse` (currently present on the
  domain `Company` model and on `CompanyResponse`, but missing from the
  list projection; the frontend's `CompanyListItem` schema requires it)
- backend/tests/unit/companies/** and backend/tests/integration/companies/**
  — only the tests covering the schema/response change above

Do not modify:

- frontend/src/pages/CompanyDetailPage.tsx, frontend/src/pages/JobsPage.tsx
  (Tasks 011 and 012)
- frontend/src/api/mock/** (leave in place — CompanyDetailPage and
  JobsPage still depend on it until their own tasks land)
- any module other than modules/companies
- backend/app/main.py

Known shape mismatches to resolve (this is the core of the task):

- Envelope: backend returns `{data, pagination: {page, pageSize, total}}`;
  frontend's `companyListResponseSchema` expects `{items, total}`.
- Backend's `CompanyListItemResponse` is flat (`companyName`, `platform`,
  `country`, `city`, `processingStatus`, `workflowStatus`,
  `opportunityScore`, `confidence`, `mainReason`); frontend's
  `CompanyListItem` nests `identity`/`processing`/`workflow` objects.
  Fields the list endpoint doesn't return (other run IDs, `shortlisted`,
  `notes_count`) should default sensibly (`null` / `false` / `0`) in the
  client-side adapter — do not add them to the backend response just to
  satisfy the adapter.
- `score`/`confidence` are always `null` from the backend today (no
  scoring module exists yet) — keep them `null` end to end; do not fake
  values.

Out of scope (explicitly deferred to later tasks or unplanned work):

- Anything involving `score_factors`, `evidence`, `emails`, `phones`,
  `url` — those only exist on `CompanyDetailPage` (Task 011).
- Sort/filter query params beyond what `GET /api/companies` already
  supports (`processingStatus`, `workflowStatus`, `platform`, `country`,
  `page`, `pageSize`) — if the frontend's `CompanyListFilters.sort`/`q`
  aren't backed by the API, drop them from the request or note them as a
  follow-up gap; do not implement server-side sorting/search as part of
  this task.
