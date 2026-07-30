# Execution Plan: Auto-trigger Discovery on Company Creation (Task 015)

Status: Done
Contract: `docs/contracts/completed/015-auto-discovery-trigger.md`
Task brief: `docs/execution-plans/tasks/015-Auto-Discovery-Trigger.md`
ADR implemented: `docs/decisions/0003-auto-discovery-trigger-placement.md`

Backend-only task, implementing ADR 0003 point 3: wire
`WebsiteDiscoveryService.run_discovery` into `POST /api/companies`,
inline and synchronously, right after `CompanyService.create_company`
succeeds. Plan produced interactively (plan mode), with the user
resolving ADR 0003's one explicitly-open question via `AskUserQuestion`
before the contract was written: the endpoint's response re-fetches the
company via `CompanyService.get_company` after discovery completes and
returns that, rather than the pre-discovery snapshot or new response
fields. Implementation done directly in this session, with a real
`evaluator` agent pass for independent verification before this record
was written, per CLAUDE.md's Task workflow.

## Scope

Changed: `backend/app/modules/companies/api/router.py` — four new
DI-assembly functions (`get_discovery_repository`,
`get_http_discovery_client`, `get_company_discovery_gateway`,
`get_discovery_service_for_company_creation`) built from
`modules/discovery`'s `application`/`domain`/`infrastructure` layers
only, deliberately not importing `discovery/api/router.py` (which
already imports this file's `get_company_service` at module level —
importing the other way would be a circular import, since `main.py`
loads `companies.api.router` first). `create_company` gains a
`discovery_service` dependency; after `create_company` succeeds it
calls `run_discovery(company.company_id)`, then re-fetches via
`service.get_company(...)` before returning. No `try/except` added
around the discovery call — `run_discovery` already catches network/
robots/sitemap failures internally (recording a `FAILED` run), and a
`CompanyNotFoundForDiscoveryError` on the id just created is left to
propagate as a 500, since it would indicate a genuine data-integrity
bug rather than an expected condition.

Test infrastructure: `backend/tests/integration/companies/conftest.py`
gained a `StubHttpDiscoveryClient` + autouse fixture overriding
`get_http_discovery_client` for the whole directory, so no test in it
makes a real network call now that company creation triggers discovery.
`test_create_company.py` got a fixed stale assertion (`"imported"` ->
`"discovered"`) plus two new tests (discovery-succeeds, discovery-fails-
but-company-still-created). Mid-implementation, a second, unanticipated
breakage was found and fixed: `test_processing_status_transitions.py`
also assumed a freshly-created company starts at `"imported"` — two of
its tests were rewritten (`discovered -> crawling` instead of
`imported -> discovering`, plus a corrected comment on the still-passing
`discovered -> ready` invalid-transition test). The contract was amended
in place (added "Known Shape Gap" #7) to record this before the
evaluator pass, rather than leaving it undocumented.

Zero changes to `backend/app/main.py`, `backend/app/modules/discovery/**`,
or `backend/app/modules/imports/**` — confirmed by the evaluator via
`git diff --stat`.

## Status log

- ADR 0003 (already Accepted, committed alongside Task 014) identified
  as the binding precedent; its one explicitly-open question (response
  shape after a synchronous discovery run) put to the user via
  `AskUserQuestion` and resolved before contract work began.
- Plan mode: one `Explore` pass over the create-company handler,
  `WebsiteDiscoveryService.run_discovery`'s signature/exception surface,
  the existing discovery-router DI chain, and the real circular-import
  hazard it surfaced; one `Plan` agent pass to design the concrete
  DI-avoiding-the-cycle approach and test plan; both independently
  spot-checked (direct file reads, grep) before the plan was finalized
  and approved.
- Task brief and feature contract written next, per CLAUDE.md's Asked/
  Decided/Built workflow — contract structured on the
  `014-storeleads-import-ui` template (Known Shape Gaps, T1-T4
  implementation tasks, AC-01..AC-07).
- Implementation done directly in this session, in contract order
  (T1 DI wiring verified import-clean before behavior changes, T2
  handler change, T3 test fixture, T4 tests), with
  `pytest`/`ruff`/`pyright` run after each major step.
- Mid-implementation discovery: `test_processing_status_transitions.py`
  had the same stale-baseline problem as `test_create_company.py`, not
  caught by the original plan's grep for the literal string `"imported"`
  alone in every file — found by actually running the suite, not by
  static search. Contract amended in place to record it as gap #7 before
  requesting evaluation, rather than fixing it silently.
- Evaluator pass: **PASS**, first attempt. Independently re-verified all
  seven acceptance criteria (including a mutation test — temporarily
  reverting the `run_discovery` call to confirm the two new tests
  actually fail without it, not just pass vacuously), re-ran the full
  backend suite (852 passed), `ruff`/`pyright` clean, confirmed no
  circular-import regression via a direct `from app.main import app`
  import, and grepped the whole companies test suite itself for any
  further hidden `"imported"`-baseline or `latestDiscoveryRunId is None`
  assumptions — found none beyond the two already fixed.
- Contract moved from `docs/contracts/active/` to
  `docs/contracts/completed/` as part of this same update.

Status: **Done.**

Known limitations carried forward (documented in the contract, not
defects): `POST /api/companies` now does real synchronous network I/O
(robots.txt/sitemap/homepage fetch) before returning, changing its
latency profile from sub-millisecond to potentially several seconds (or
up to `HttpxDiscoveryClient`'s timeout for a slow/dead site) — authorized
by ADR 0003 at single-record scale, but no frontend currently calls this
endpoint, so there's no user-visible regression yet. The bulk
`POST /api/imports/storeleads` commit path remains explicitly untouched,
per ADR 0003 point 2 — auto-triggering discovery there is blocked until
a real background-execution mechanism exists and gets its own ADR.
