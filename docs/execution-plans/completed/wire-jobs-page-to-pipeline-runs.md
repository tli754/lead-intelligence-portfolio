# Execution Plan: Wire Jobs Page to Pipeline Runs (Task 012)

Status: Done
Contract: `docs/contracts/completed/wire-jobs-page-to-pipeline-runs.md`
Task brief: `docs/execution-plans/tasks/012-Wire-Jobs-Page-to-Pipeline-Runs.md`

Third of three follow-up tasks (010, 011, 012) splitting "wire the
frontend off mock data" into small, independently-planned pieces, per
CLAUDE.md's Task workflow. Independent of Tasks 010/011 by design, but
built after both landed so the frontend jobs client could reuse Task
010's `listCompanies` client for `company_domain` resolution. Contract
produced directly, based on reading the real `DiscoveryRun`/`CrawlRun`/
`ExtractionRun` models and status enums against the frontend's
mock-derived `Job`/`JobStatus` Zod schema. Generator build done in an
isolated git worktree, mirroring Tasks 006/007/010/011's pattern.

## Scope

Backend: `list_runs(status, page, page_size)` added identically to
`modules/discovery`, `modules/crawling`, `modules/extraction`
(`domain/repository.py`, `infrastructure/mongo_*_repository.py`,
`api/schemas.py`, `api/router.py`), each exposing a new
`GET /api/{discovery,crawl,extraction}-runs` route. A `created_at`
index was added to each module's `ensure_indexes()` — none of the three
previously indexed it, and the new unfiltered `list_runs` sorts by it
over the whole collection.

Frontend: new `frontend/src/api/jobs.ts` (real client composing the
three endpoints, binding status-mapping table, `company_domain`
resolution via `listCompanies`), a small additive `pageSize` parameter
on `listCompanies`/`buildCompanyListQuery` (`frontend/src/api/
companies.ts`), and `frontend/src/api/queries.ts`'s `useJobs` switched
from the mock `fetchJobs` to the real `fetchPipelineJobs`.
`frontend/src/pages/JobsPage.tsx` needed no functional changes (only
its stale top-of-file docstring, updated after evaluator review) — it
already rendered whatever `useJobs` returned generically.

Zero changes to `backend/app/main.py` (routers already registered),
`frontend/src/pages/{CompaniesPage,CompanyDetailPage}.tsx`, or
`frontend/src/api/mock/**` — confirmed by the evaluator via
`git diff --stat`.

## Status log

- Contract produced and saved to `docs/contracts/active/`, including a
  binding Field & Status Mapping table (every `DiscoveryStatus`/
  `CrawlStatus`/`ExtractionStatus` literal mapped to exactly one of the
  frontend's 4 `JobStatus` values) and 8 acceptance criteria.
- Generator build in an isolated git worktree
  (`.claude/worktrees/agent-accec4ba8e4fc1411`, branch
  `worktree-agent-accec4ba8e4fc1411`), committing after each step: T1
  (discovery, reference implementation), T2 (crawling), T3 (extraction),
  a merge of `main` (to pick up Tasks 010/011 before frontend work), T4
  (frontend jobs client), T5 (wiring `useJobs`) — six commits, matching
  the task brief's explicit checkpoint-per-step request (called out
  there because Task 007 previously lost work to a mid-session
  token-exhaustion crash without this discipline).
- Two documented, judgment-call additions beyond the contract's literal
  text, both verified by the evaluator as genuine and inert:
  - `backend/tests/integration/discovery/test_mongo_discovery_repository.py`
    (new) — discovery had no real-MongoDB repository test at all before
    this task (unlike crawling/extraction's existing
    `test_mongo_{crawl,extraction}_repository.py`); added for parity.
  - A one-line `NotImplementedError` stub added to an unrelated
    `FakeCrawlRepository` in
    `backend/tests/unit/extraction/test_crawl_repository_gateway.py`,
    required to keep it instantiable after `CrawlRepository` gained the
    new abstract `list_runs` method — never exercised by that file's own
    tests.
- Evaluator pass: **PASS**, first attempt. Independently re-verified all
  8 acceptance criteria from scratch (not trusting the generator's
  self-report): re-ran `app.main.app.openapi()["paths"]` directly to
  confirm no route collisions (AC-02), re-enumerated every status enum
  literal across all three modules against the frontend mapping table
  by hand (AC-04), ran the full backend suite (850 passed) and frontend
  suite (95 passed) plus `ruff`/`pyright`/`tools/check_architecture.py`,
  and audited `git diff --stat` scope (AC-06).
  - Flagged one non-blocking design trade-off: `mapRunStatusToJobStatus`
    throws (rather than silently returning `undefined`) on an unmapped
    status, which fails the whole `Promise.all`-composed page load
    rather than degrading one row — judged a reasonable, defensible
    interpretation of AC-04 given `JobStatusBadge`'s own lookup has no
    fallback either, not a contract violation.
  - Flagged two non-blocking follow-ups, addressed/deferred as noted
    below.
- Follow-up applied immediately (trivial, low-risk): updated
  `JobsPage.tsx`'s top-of-file docstring, which still read "mock data
  only" after `useJobs` was wired to real data.
- Follow-up deferred (out of scope for this task, tracked here for
  visibility): `listDiscoveryRuns`/`listCrawlRuns`/`listExtractionRuns`
  each fetch only `page=1, pageSize=200` with no multi-page aggregation
  or truncation indicator — if any single stage ever exceeds 200 runs,
  older runs are silently omitted from `JobsPage`. Not required by the
  contract's acceptance criteria (which govern API-layer pagination
  correctness, satisfied) or Required Tests; worth a future ticket if
  run volume grows.
- Merged to `main` via `git merge --no-ff worktree-agent-
  accec4ba8e4fc1411`. This file and the contract move to their
  `completed/` counterparts as part of this same update. Full suite
  re-verified green on `main` post-merge (850 backend + 95 frontend
  tests).

Status: **Done.**

Known limitations carried forward (documented in the contract, not
defects): the frontend `JobStatus` mapping is deliberately lossy
(`completed_with_warnings`/`partial`/`stale` all collapse to
`succeeded`; `cancelled` collapses to `failed`) — `error_message`
remains the place operationally-relevant nuance can surface, per the
contract's accepted risk. `analysis`/`scoring` stages remain
permanently empty until Task 008 (AI analysis) and an eventual scoring
module exist. The 200-run-per-stage cap noted above is a new, real
scale limitation introduced by the real client (the mock had no cap) —
tracked as a follow-up, not blocking this task.
