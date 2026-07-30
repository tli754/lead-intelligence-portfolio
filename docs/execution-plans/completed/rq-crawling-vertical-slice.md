# Execution Plan: Adopt RQ for the Crawling Module — Vertical Slice (Task 017)

Status: Done
Contract: `docs/contracts/completed/017-rq-crawling-vertical-slice.md`
Task brief: `docs/execution-plans/tasks/017-Adopt-RQ-Queue-Crawling-Vertical-Slice.md`
ADR implemented: `docs/decisions/0004-adopt-rq-as-queue-system.md`

Backend-only task, implementing ADR 0004's decision to adopt RQ + Redis
as this repository's queue/background-job system, applied first to the
crawling module (the longest-running, most queue-shaped pipeline
stage). Investigation, ADR, and contract were produced in this
session; implementation and evaluation followed CLAUDE.md's
planner/generator/evaluator workflow with real subagents at each step.

## Scope

Added: `backend/app/queue.py` (Redis connection + RQ queue factory,
sibling to `db.py`), `backend/app/worker.py` (RQ worker entrypoint,
`QUEUE_NAMES = ["crawling"]`), `backend/app/modules/crawling/infrastructure/rq_jobs.py`
(job wrapper functions `run_crawl_execution`/`run_crawl_retry`,
`_build_service` composing the same DI chain `api/router.py` already
assembles, `CRAWL_JOB_TIMEOUT = "1h"` overriding RQ's unsafe 180s
default).

Changed: `pyproject.toml` (`redis`, `rq` dependencies);
`backend/app/config.py` + `.env.example` (`REDIS_URL`);
`backend/app/modules/crawling/application/website_crawl_service.py` —
`start_crawl_run` split into `enqueue_crawl_run` (validation, persists
a `QUEUED` run, no execution) and `execute_crawl_run` (target
processing, callable by `crawl_run_id` alone, with a new
"return immediately if already `CANCELLED`" guard); `start_crawl_run`
itself kept as a thin composed wrapper so the pre-existing ~30-scenario
test suite in `test_website_crawl_service.py` keeps passing unmodified;
`enqueue_retry` added alongside the unchanged `retry_failed`.
`backend/app/modules/crawling/api/router.py` — `get_crawl_queue()` DI
accessor; `create_crawl_run`/`retry_failed_targets` now enqueue via RQ
instead of executing inline; `cancel_crawl_run` does a best-effort
cancel of both possible RQ job ids, tolerating a missing job or an
unreachable Redis without failing the request.

Zero changes to `modules/companies/**`, `modules/discovery/**`,
`modules/extraction/**`, `frontend/**`, `docker-compose.yml`, or
`.gitignore` — confirmed by the evaluator via `git diff --stat` against
the pre-task commit.

## Known Shape Gap (found by evaluation, fixed before PASS)

The contract's original design claimed no new field on `CrawlRun` was
needed, reasoning that the existing `configuration_snapshot`
(a `CrawlConfig` dump) would let `execute_crawl_run` recover everything
it needed from `crawl_run_id` alone. That premise was wrong:
`configuration_snapshot` only ever captured `max_pages`/`browser_policy`,
never the caller's `force_refresh`/`include_page_types`/
`exclude_page_types`/`manual_urls` (all real fields on the public
`CrawlRunOptionsRequest` API schema). The first evaluator pass caught
this as a critical, reproducible regression: `execute_crawl_run`
hardcoded `CrawlRunOptions()`, so every real crawl run created through
the API would silently ignore those four fields once the router
stopped calling the old single-shot `start_crawl_run`.

Fix: added `options_snapshot: dict` to `CrawlRun`
(`backend/app/modules/crawling/domain/models.py`); `enqueue_crawl_run`
persists `options.model_dump(mode="json")` into it; `execute_crawl_run`
reconstructs `options = CrawlRunOptions.model_validate(run.options_snapshot)`
instead of defaulting. `docs/architecture/mongodb-design.md`'s
`crawl_runs` schema listing was updated to document the new field. The
contract itself was amended in place (see its "Affected repositories"
and "Out of Scope" sections) to record the corrected premise, per this
repository's established precedent for handling evaluator-discovered
premise defects rather than silently building around stale contract
text.

A regression test (`test_execute_crawl_run_recovers_persisted_options`
in `test_website_crawl_service.py`) was added and confirmed, by
temporarily reverting the fix, to actually fail without it.

## Status log

- Investigated current architecture (all three pipeline stages
  synchronous inline, no queue; each service already built to accept
  plain arguments for future worker use; no backend "jobs" module;
  shared `/srv/infra` Redis confirmed reachable at `localhost:6379`).
- ADR 0004 written, adopting RQ + Redis generally and designating
  crawling as the first module to migrate, module-by-module per
  Decision #3 — does not reverse ADR 0003's bulk-import conclusion.
- Feature contract `017-rq-crawling-vertical-slice.md` written by a
  `planner` agent pass, scoping the crawling-specific design in full
  (enqueue/execute split, queue/worker infra, job ids/timeouts, cancel
  semantics, waived real-Redis end-to-end test with stated rationale).
- Implementation by a `generator` agent pass, in an isolated git
  worktree. First evaluator pass: **FAIL** — critical regression found
  (options dropped across the enqueue/execute split, reproduced
  directly, not just inferred from reading code).
- Fix applied by the same generator agent (`options_snapshot` field,
  regression test, confirmed the test fails without the fix and passes
  with it); `docs/architecture/mongodb-design.md` updated.
- Second evaluator pass: **PASS**. All ten acceptance criteria verified
  independently (including re-reproducing the original bug via a
  temporary revert), full backend suite green (861 passed), `ruff`/
  `pyright`/architecture checks clean, file-scope boundary confirmed
  unchanged. One follow-up required before completion: amend the
  contract's stale "no new field needed" claims — done as part of this
  same update, before filing to `completed/`.

Status: **Done.**

## Required follow-up (not built by this task, reported per the contract)

1. Update `CLAUDE.md`'s `backend/app/` directory listing to include
   `queue.py`/`worker.py`, and its "Local infra" Redis sentence
   (currently "Redis and background workers are deliberately not
   scaffolded yet") to reflect that crawling now uses both.
2. `docs/contracts/completed/wire-jobs-page-to-pipeline-runs.md`'s line
   "there is no queue or worker system in this repository" is now
   stale for crawling specifically — flagged, not edited (historical
   completed contract).
3. Apply the same enqueue/execute split to
   `WebsiteDiscoveryService.run_discovery` and
   `StructuredExtractionService.start_extraction_run`, each via its own
   future contract, per ADR 0004's module-by-module rollout. Not
   started by this task.
4. The bulk-import auto-discovery question ADR 0003 deferred is still
   deferred — a future ADR revisiting ADR 0003 needs discovery itself
   queued first (not done by this task).
