# Feature Contract: Task 015 — Auto-trigger discovery on company creation

Task brief: `docs/execution-plans/tasks/015-Auto-Discovery-Trigger.md`

Binding architectural precedent: `docs/decisions/0003-auto-discovery-trigger-placement.md`
(Accepted). That ADR settles where an auto-triggered discovery run is
allowed to live and which create path it may be wired into. This contract
implements point 3 of its Decision section and resolves the one thing it
left open (both answered directly by the user — see the task brief).

No dependency on Task 014 (StoreLeads import UI) — different backend
subsystem, no shared files.

# Feature

## Business Goal

Today, no code path auto-starts discovery after a company is created —
`WebsiteDiscoveryService.run_discovery` only runs when something explicitly
calls `POST /api/companies/{company_id}/discovery-runs`. `POST /api/companies`
(the single-record create endpoint) is the one path ADR 0003 authorizes for
an inline, synchronous auto-trigger. This task wires it in.

## User Story

As a caller of `POST /api/companies`, I want discovery to run automatically
on the company I just created, so I don't have to make a second explicit
call to `POST /api/companies/{company_id}/discovery-runs` to get discovery
started.

## Business Value

Closes the gap ADR 0003 identified and scoped. No frontend page currently
calls `POST /api/companies` (confirmed by that ADR's own Context section),
so this is backend-only groundwork — not yet user-visible until a caller
of this endpoint exists.

# Architecture Impact

## Affected domains / services

`backend/app/modules/companies/api/router.py` only. No changes to
`CompanyService`, `WebsiteDiscoveryService`, or any domain/application
layer — per ADR 0003 point 1, the trigger lives exclusively at the router
layer.

## Affected APIs

`POST /api/companies` — behavior change, not a schema change. Same
request (`CreateCompanyRequest`) and response (`CompanyResponse`) shapes;
the response now reflects post-discovery company state (see "Known Shape
Gaps" #1).

Not touched: `POST /api/companies/{company_id}/discovery-runs`,
`POST /api/imports/storeleads` (explicitly blocked from this trigger by
ADR 0003 point 2), `backend/app/main.py`.

## Affected database collections

None new. `companies_pipeline` documents now get their
`processing.status`/`latest_discovery_run_id` updated synchronously within
the same request that creates them, instead of staying at `imported` until
a separate discovery-runs call.

## Affected frontend

None. No frontend page calls `POST /api/companies` today.

# Cross-module dependency decisions

`backend/app/modules/companies/api/router.py` gains a small, duplicated DI
chain (four functions: `get_discovery_repository`, `get_http_discovery_client`,
`get_company_discovery_gateway`, `get_discovery_service_for_company_creation`)
mirroring `discovery/api/router.py`'s own chain, built from discovery's
`application`/`domain`/`infrastructure` layers only — **never**
`discovery.api.router` itself. `discovery/api/router.py` already does
`from app.modules.companies.api.router import get_company_service` at
module level; since `main.py` imports `companies.api.router` before
`discovery.api.router`, a top-level `companies.api.router -> discovery.api.router`
import would be a direct A->B->A cycle, breaking at startup. None of
discovery's `application`/`domain`/`infrastructure` modules import
`companies.api.router`, so building the graph from those layers avoids the
cycle. This is a deliberate, accepted duplication of a handful of small
functions across the two router files — not a violation of
`docs/architecture/dependency-rules.md`'s dependency-direction rule, which
governs `domain`/`application`/`infrastructure` layering, not router-file
code reuse.

# Known Shape Gaps (binding on the implementation)

1. **Response reflects post-discovery state, via re-fetch.** After
   `run_discovery` completes, `create_company`'s handler calls
   `service.get_company(company.company_id)` again and returns that —
   not the pre-discovery snapshot from immediately after `create_company`.
   Same `CompanyResponse` shape; no new fields added to carry discovery
   outcome separately.
2. **`CompanyNotFoundForDiscoveryError` is not caught** — it propagates as
   an unhandled 500. `run_discovery` looks up the same `company_id` this
   handler just created, milliseconds earlier; a failure there indicates a
   genuine data-integrity bug, not an expected condition to paper over with
   a forced 201.
3. **Network/robots/sitemap failures inside `run_discovery` are NOT this
   endpoint's problem to catch** — `run_discovery` already catches those
   internally and turns them into a `FAILED` `DiscoveryRun` plus a
   `ProcessingStatus.FAILED` update on the company. The re-fetch already
   reflects this; no `try/except` wraps the `run_discovery` call for this
   class of failure.
4. **`latest_discovery_run_id` is only set on the success path.**
   `WebsiteDiscoveryService.run_discovery` calls
   `update_latest_discovery_run` only right after advancing
   `ProcessingStatus.DISCOVERED` (`website_discovery_service.py:216`) — on
   a failed run (`ProcessingStatus.FAILED`), `latest_discovery_run_id`
   stays `null` even though a `DiscoveryRun` record was created. This is
   existing `run_discovery` behavior, not something this task changes or
   should "fix" — tests must assert this asymmetry explicitly (see
   Required Tests), not paper over it.
5. **Existing companies-module integration tests break without a fixture
   fix.** Every test using the shared `create_company` fixture
   (`backend/tests/integration/companies/conftest.py`) will otherwise
   trigger a real `HttpxDiscoveryClient` network call. A local, always-
   succeeds stub `HttpDiscoveryClient` must be wired in via an autouse
   fixture overriding `get_http_discovery_client` through
   `app.dependency_overrides`, scoped to that test directory only.
6. **`test_create_company_returns_camel_case_body_with_defaults`'s existing
   assertion `body["processing"]["status"] == "imported"` must change** to
   `"discovered"` — an expected behavior change from this task, not a
   regression.
7. **`test_processing_status_transitions.py`'s two hand-written-transition
   tests assumed a freshly created company starts at `"imported"`, which
   is no longer true.** `test_valid_transition_succeeds` exercised
   `imported -> discovering`; since discovery now runs synchronously on
   create, the company is already `discovered` by the time the test runs,
   so `discovering` is no longer a valid target from there (only
   `crawling`/`failed` are, per `ALLOWED_PROCESSING_TRANSITIONS`). The test
   must be rewritten to exercise `discovered -> crawling` instead — same
   intent (assert a valid transition succeeds), different concrete states.
   `test_invalid_transition_is_rejected` (`discovered -> ready`, formerly
   `imported -> ready`) still returns 409 either way, but its comment must
   be corrected since it no longer describes the actual starting state.

# Implementation Tasks

**T1 — DI wiring** (`backend/app/modules/companies/api/router.py`): add
`get_discovery_repository`, `get_http_discovery_client`,
`get_company_discovery_gateway`, `get_discovery_service_for_company_creation`,
importing only from `modules/discovery`'s `application`/`domain`/
`infrastructure` layers.

**T2 — Handler change**: `create_company` gains a
`discovery_service: WebsiteDiscoveryService = Depends(get_discovery_service_for_company_creation)`
parameter; after the existing `create_company`/`DuplicateCompanyError`
handling, call `await discovery_service.run_discovery(company.company_id)`,
then re-fetch via `service.get_company(company.company_id)` and return
`company_to_response(...)` of the re-fetched company.

**T3 — Test fixture fix** (`backend/tests/integration/companies/conftest.py`):
a small local `StubHttpDiscoveryClient(HttpDiscoveryClient)` (canned
`resolve_homepage`/`fetch_text`/`fetch_binary` responses, `fetch_html`
raising `NotImplementedError` since it's unexercised via
`resolve_homepage`-only discovery), wired in via an autouse fixture
overriding `get_http_discovery_client` in `app.dependency_overrides`
(imported from `app.main`), matching `backend/tests/conftest.py`'s own
`get_database` override pattern. Configurable enough to support both a
success and a failure response for T4's two new tests.

**T4 — Tests** (`backend/tests/integration/companies/test_create_company.py`):
fix the existing `"imported"` -> `"discovered"` assertion; add a success-
path test (asserts `processing.status == "discovered"` and
`processing.latestDiscoveryRunId` non-null) and a failure-path test
(per-test override of the stub to fail homepage resolution — asserts
`201` still returned, `processing.status == "failed"`,
`processing.latestDiscoveryRunId` still `null`). Also fix
`test_processing_status_transitions.py` per gap #7 — rewrite
`test_valid_transition_succeeds` to exercise `discovered -> crawling`
instead of `imported -> discovering`, and correct
`test_invalid_transition_is_rejected`'s comment (its assertion doesn't
change, only the starting-state description was wrong).

# Acceptance Criteria

- AC-01: `POST /api/companies` with a valid domain returns `201` with
  `processing.status == "discovered"` and a non-null
  `processing.latestDiscoveryRunId`, when discovery succeeds.
- AC-02: `POST /api/companies` still returns `201` (company creation is
  not rolled back or failed) when discovery itself fails internally, with
  `processing.status == "failed"` and `processing.latestDiscoveryRunId`
  still `null`.
- AC-03: `POST /api/companies/import`'s bulk sibling
  (`POST /api/imports/storeleads`) is untouched — no discovery trigger
  added there, confirmed by `git diff --stat` showing zero changes under
  `modules/imports/**`.
- AC-04: No changes to `backend/app/main.py` or
  `backend/app/modules/discovery/api/router.py`.
- AC-05: No import cycle — `pytest`/app startup succeeds (a cycle would
  fail at collection/import time, not silently).
- AC-06: All pre-existing `backend/tests/integration/companies/**` tests
  pass unmodified in behavior (aside from the one documented assertion
  fix in "Known Shape Gaps" #6), with no real network calls made during
  the test run (stub-backed).
- AC-07: `DuplicateCompanyError` handling is unchanged — a duplicate
  domain still returns `409` and does not attempt to run discovery.

# Required Tests

See T4 above. Additionally: confirm no other route in
`companies/api/router.py` was touched (`list_companies`, `get_company`,
`update_processing_status`, `update_workflow_status`) via `git diff`.

# Risks

- **Risk**: `POST /api/companies` goes from a sub-millisecond DB write to
  a call bounded by robots.txt + sitemap + homepage-fetch latency against
  an arbitrary external site — potentially several seconds, or up to
  `HttpxDiscoveryClient`'s timeout for a slow/dead site.
  **Mitigation**: explicitly authorized by ADR 0003 at single-record
  scale; no frontend caller exists yet to feel this today. Flagged here so
  whoever wires a frontend caller to this endpoint later knows the latency
  profile changed.
- **Risk**: duplicated DI-assembly functions between `companies/api/router.py`
  and `discovery/api/router.py` could drift out of sync if
  `WebsiteDiscoveryService`'s constructor signature changes.
  **Mitigation**: both call sites construct the same three dependencies in
  the same order; a constructor signature change would fail loudly (a
  `TypeError` at call time, caught by any test that exercises company
  creation), not silently drift.

# Dependencies

`WebsiteDiscoveryService`, `CompanyDiscoveryGateway`,
`CompanyServiceDiscoveryGateway`, `MongoDiscoveryRepository`,
`HttpxDiscoveryClient` — all already exist, already tested via
`modules/discovery`'s own test suite. No dependency on Task 014.

# Suggested Implementation Order

1. T1 (DI wiring) — no behavior change yet, just new unused functions;
   verify no import-cycle regression by itself first.
2. T2 (handler change) — the actual behavior change.
3. T3 (test fixture fix) — needed before T4's new tests, and before
   re-running any pre-existing companies-module test.
4. T4 (tests) — last, once T1-T3 are in place.

# Success Criteria

All acceptance criteria pass; `pytest backend/tests/integration/companies/
backend/tests/unit/companies/` green with zero real network calls; full
suite (`pytest backend/tests --ignore=backend/tests/modules/companies
--ignore=backend/tests/test_company_module_api.py`) shows no regressions
elsewhere; `ruff`/`pyright` clean; `git diff --stat` confined to
`backend/app/modules/companies/api/router.py` and
`backend/tests/integration/companies/**`.
