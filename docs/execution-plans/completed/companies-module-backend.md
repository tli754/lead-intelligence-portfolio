# Execution Plan: Companies Module Backend (Task 003)

Status: Complete
Contract: none written — built directly from an ad-hoc task brief ("Task
003"), not through the planner→contract workflow used by
`paste-in-importer`. Full plan (with the design rationale for the
transition graphs below): see the approved plan this task was implemented
from.

Supersedes the "Task 002" version of this module (same paths, rewritten in
place — the `companies_pipeline` collection was empty at rewrite time, so
there was no live-data migration to handle).

## Scope

Isolated to `backend/app/modules/companies/**`,
`backend/tests/unit/companies/**`, `backend/tests/integration/companies/**`
per the task's explicit path restrictions. No frontend, StoreLeads import,
crawling, discovery, extraction, evidence, AI analysis, scoring, jobs,
auth, deploy, or CI/CD work included.

## What was built

**Domain** (`domain/`): `Company` gained `document_version` (schema-version
marker, always `1` for now) and flat `created_at`/`updated_at` (replacing
the old nested `timestamps` object); `CompanyProcessing`'s five
`latest_*_run` timestamp fields became `latest_*_run_id` string fields
(opaque ids owned by each pipeline stage's own future module).
`ProcessingStatus` expanded from 9 to 14 values (added `discovered,
crawled, extracted, analysed, partial`); `WorkflowStatus` gained
`archived`.

New: `transitions.py` — the "reject invalid enum transitions" requirement.
Transition graphs are a **design choice** the task didn't specify, made
explicit here:
- `ProcessingStatus`: each `-ing` stage advances only to its own `-ed`
  completion or to `failed`; `scoring` reaches `ready`, `partial`, or
  `failed`; the resting states (`ready`, `partial`, `failed`, `stale`) can
  all retry from `discovering`; `ready` can additionally go `stale`.
- `WorkflowStatus`: a roughly linear review lifecycle
  (`unreviewed → reviewed → shortlisted → contacted → customer`) with
  `not_suitable`/`archived` reachable from most states, and `archived`/
  `not_suitable` able to re-open back to `unreviewed`.

Also new: `Company.created_at`/`updated_at` coerce a naive `datetime` to
UTC-aware rather than rejecting it — necessary because Motor's client
(`app/db.py`, outside this task's allowed paths) returns naive datetimes
on read unless constructed with `tz_aware=True`, so "all timestamps use
timezone-aware UTC" has to be enforced at this module's own boundary.

**Repository interface** (`domain/repository.py`): renamed
`get_by_domain` → `get_by_normalized_domain`, `exists` →
`exists_by_normalized_domain`, `list` → `list_companies`; the latter now
returns a `CompanyPage(items, total)` so pagination metadata comes from
the repository in one call.

**Infrastructure** (`infrastructure/mongo_repository.py`): same Motor
patterns as before (unchanged `ensure_indexes()` — unique
`normalized_domain`, plus `processing.status`, `workflow.manual_status`,
`identity.platform`, `identity.country`), updated for the renamed
fields/methods; `list_companies` runs `count_documents` alongside the
paginated `find().skip().limit()`.

**Application** (`application/service.py`): `change_processing_status`/
`change_workflow_status` now fetch the current company, validate the
transition via `transitions.py` (raising `InvalidStatusTransitionError` on
an invalid edge), then update — same `CompanyNotFoundError` handling as
before for a missing company.

**API** (`api/`): all JSON is camelCase, via a shared
`CamelCaseModel(alias_generator=to_camel, populate_by_name=True)` base
(`pydantic.alias_generators.to_camel`). Response DTOs
(`CompanyResponse`/`CompanyListItemResponse`) are kept separate from the
domain `Company` model — camelCase is an API concern — with mapper
functions (`company_to_response`/`company_to_list_item`) between them.
`GET /api/companies` returns `{data: CompanyListItemResponse[], pagination:
{page, pageSize, total}}`; the list projection's `opportunityScore`/
`confidence`/`mainReason` are hardcoded `None` in the mapper (scoring
doesn't exist yet — these never became placeholder fields on the domain
model). Query params are camelCase-aliased (`processingStatus`,
`workflowStatus`, `page`, `pageSize`). `InvalidStatusTransitionError` maps
to `409`, alongside the existing `DuplicateCompanyError` → `409` and
`CompanyNotFoundError` → `404`.

## Endpoints

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/companies` | filters: `processingStatus`, `workflowStatus`, `platform`, `country`; paging: `page` (default 1), `pageSize` (default 20, max 200) |
| `GET` | `/api/companies/{companyId}` | 404 if missing |
| `POST` | `/api/companies` | 201; 409 on duplicate `normalizedDomain` |
| `PATCH` | `/api/companies/{companyId}/processing-status` | 404 missing; 409 invalid transition |
| `PATCH` | `/api/companies/{companyId}/workflow-status` | 404 missing; 409 invalid transition |

## Testing

68 new tests, all passing:
- **Unit** (`backend/tests/unit/companies/`, 48 tests, no MongoDB):
  normalization, `Company` validation (incl. naive→UTC coercion), every
  valid/invalid transition edge for both enums, camelCase API-schema
  serialization.
- **Integration** (`backend/tests/integration/companies/`, 20 tests, real
  MongoDB via the existing `client`/`test_database` fixtures in
  `backend/tests/conftest.py`): create, retrieve, list envelope + filters +
  pagination math, both status-transition endpoints (valid/invalid/missing/
  malformed), duplicate-domain rejection.

`ruff` and `pyright` clean on all changed/new paths. Full suite (excluding
the now-stale paths below): 99 passed.

## Required follow-up outside this task's allowed paths (reported, not done)

- **`backend/tests/modules/companies/**` and
  `backend/tests/test_company_module_api.py`** (the old Task 002 tests) —
  **actively broken**: they `ImportError` on collection (reference
  `CompanyTimestamps`, which no longer exists) and this **aborts the whole
  `pytest backend/tests` run** rather than just failing individually.
  Recommend deleting them — the new `unit`/`integration` suites fully
  supersede their coverage. Until that happens, run this module's tests
  with `pytest backend/tests --ignore=backend/tests/modules/companies
  --ignore=backend/tests/test_company_module_api.py`, or the equivalent
  narrower `pytest backend/tests/unit/companies
  backend/tests/integration/companies`.
- No changes were needed to `backend/app/main.py` or
  `backend/tests/conftest.py` — confirmed before implementation (same
  class/module names, same collection name, existing fixtures already
  sufficient).

## Known gaps / integration work still required

- Nothing links this module to the paste-in importer's `companies`
  collection — no promotion path from an imported `Company` to a
  pipeline-tracked one.
- `opportunityScore`/`confidence`/`mainReason` are permanent `null` until
  a scoring feature exists.
- The frontend's mock-data UI (`docs/execution-plans/completed/companies-frontend-mock-ui.md`)
  is not wired to this API — it still runs entirely on fixture data.
- The transition graphs in `transitions.py` are a first-pass design choice,
  not something the task specified — worth explicit product/eng review
  before another module starts depending on them.
