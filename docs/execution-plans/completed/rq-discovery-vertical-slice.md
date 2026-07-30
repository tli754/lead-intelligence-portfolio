# Execution Plan: Adopt RQ for the Discovery Module (Task 020)

Status: Done
Contract: `docs/contracts/completed/020-rq-discovery-vertical-slice.md`
Task brief: `docs/execution-plans/tasks/020-Adopt-RQ-Discovery-Vertical-Slice.md`
ADR: `docs/decisions/0005-auto-chain-import-discovery-crawl.md`
Builds on: `docs/decisions/0004-adopt-rq-as-queue-system.md`,
`docs/contracts/completed/017-rq-crawling-vertical-slice.md`

The second application of ADR 0004's queue decision, and the direct
prerequisite ADR 0005 requires before any auto-chaining wiring (Task
021) can be built safely. Moves `WebsiteDiscoveryService`'s discovery
pass off the HTTP request/response cycle and onto an RQ background
worker, mirroring Task 017's crawling precedent — proving the pattern
generalizes to a second module with a meaningfully smaller surface (no
retry/cancel endpoints, no options object, no duplicate-active-run
check).

## Scope

Changed: `backend/app/modules/discovery/application/website_discovery_service.py` —
`run_discovery` split into `enqueue_discovery_run` (persist a `queued`
`DiscoveryRun`, no network I/O beyond the domain lookup) and
`execute_discovery_run` (re-fetches the run by id, raises
`DiscoveryRunNotFoundError` if missing, runs the full homepage/robots/
sitemap pipeline unchanged in substance). `run_discovery` kept as a
thin composed wrapper (`enqueue` then `execute`), preserving the one
existing test that calls it with a direct `cancellation_check`.

Added: `backend/app/modules/discovery/infrastructure/rq_jobs.py` —
`_build_service()`, `run_discovery_execution(discovery_run_id)`,
`DISCOVERY_JOB_TIMEOUT = "20m"` (discovery's worst case — up to 50
sequential sitemap fetches at ~15s each — is ~12.5 minutes; 20m leaves
margin while staying well under crawling's unbounded `"1h"`).

Changed: `backend/app/worker.py` — `QUEUE_NAMES` now
`["crawling", "discovery"]`. `backend/app/modules/discovery/api/router.py` —
new `get_discovery_queue()` DI accessor; `create_discovery_run` now
enqueues (`enqueue_discovery_run` + `queue.enqueue_call(...)`) instead
of awaiting the full pipeline inline; corrected the module's stale
docstring (it wrongly claimed discovery wasn't registered in
`main.py` and ran synchronously — both now accurate).

Confirmed by direct inspection during planning and again by the
evaluator: no options object exists on `run_discovery`'s signature, so
Task 017's `options_snapshot` bug (silently dropping caller-supplied
options across the enqueue/execute split) has no discovery-side
equivalent — nothing needed adding to the `DiscoveryRun` schema.

Zero changes to `modules/companies/**`, `modules/crawling/**`,
`modules/extraction/**`, `modules/imports/**`, any frontend file,
`app/config.py`, `app/queue.py`, `pyproject.toml`, `docker-compose.yml`.
No auto-chaining logic anywhere in the diff — `run_discovery_execution`
calls only `execute_discovery_run` and returns `None`; the crawl-on-
discovery-completion hook is explicitly Task 021's job, per ADR 0005.

## Status log

- ADR 0005 (`docs/decisions/0005-auto-chain-import-discovery-crawl.md`)
  and this contract were produced by a `planner` agent pass, explicitly
  instructed up front to reproduce both files' full content in its
  final message (a prior planning pass, for Task 017, had omitted one
  of two files due to the planner's read-only toolset — this time it
  complied without a follow-up needed).
- Implementation by a `generator` agent pass in an isolated git
  worktree. The worktree's branch predated Tasks 017/018/019, so the
  generator fast-forward-merged `main` into it first to bring in the
  RQ infra/pattern this task depends on — verified clean by the
  evaluator (no divergence, nothing reverted).
- Genuine discrepancy found and fixed during implementation: the
  contract claimed no changes were needed to
  `test_api_schema_serialization.py`, but two tests there
  (`test_response_shape_and_pagination`,
  `test_excluded_urls_hidden_by_default`) asserted on discovered URLs
  existing synchronously after `POST .../discovery-runs`, which is no
  longer true post-split. Fixed by having those two tests call
  `execute_discovery_run` directly after the HTTP enqueue — narrow,
  confirmed by the evaluator to not weaken any assertion.
- Evaluator pass: **PASS**. Independently re-ran every acceptance
  criterion's exact specified `pytest` node id (not just the
  generator's claimed results), confirmed the branch's fast-forward
  integrity via `git merge-base`/parent-commit inspection, confirmed
  AC-05's "zero modification to existing test bodies" via `git diff`
  (empty diff on `test_processing_status_transitions.py`, purely
  additive on `test_discovery_service.py`), confirmed the job timeout
  constant is actually wired into `enqueue_call` (not dead code), and
  confirmed `ruff`/`pyright`/architecture-check are clean (877 passed
  full suite, 249 passed discovery-scoped).
- Contract moved from `docs/contracts/active/` to
  `docs/contracts/completed/` as part of this same update.
- Merged into `main` via `git merge --no-ff` from
  `worktree-agent-a6ff5ce3de96afa00`.

Status: **Done.**

## Required follow-up (not built by this task, reported per the contract)

1. Update `CLAUDE.md`'s directory listing under
   `backend/app/modules/discovery/infrastructure/` to include
   `rq_jobs.py` (Task 017's equivalent follow-up for
   `queue.py`/`worker.py`/crawling's `rq_jobs.py` also remains
   unactioned — this is additional to, not a duplicate of, that gap).
2. ADR 0005's authorized-but-unbuilt work is entirely Task 021's job:
   `modules/companies/api/router.py`'s `create_company` still calls
   `WebsiteDiscoveryService.run_discovery` synchronously (Task 015,
   unchanged); replacing it with an enqueue call, adding the same to
   the bulk import-commit path, and wiring the discovery-completion →
   crawl-enqueue hook inside `run_discovery_execution` are all
   unstarted.
3. Extraction module's own RQ adoption, per ADR 0004's module-by-module
   rollout, remains unstarted.
