# Execution Plan: Structured Extraction and Evidence Modules (Task 007)

Status: Done
Contract: `docs/contracts/active/structured-extraction-and-evidence-module.md`
Task brief: `docs/execution-plans/tasks/007—Structured-Extraction-and-Evidence-Module.md`

Second task (after Task 006, the crawling module) to go through the full
planner → generator → evaluator pipeline, per CLAUDE.md's "Task workflow"
section. The contract above was produced by the planner agent against
the raw task brief and the crawling-module contract as a style/pattern
reference before any implementation started.

## Scope

Isolated to `backend/app/modules/extraction/**`,
`backend/app/modules/evidence/**`, `backend/tests/unit/extraction/**`,
`backend/tests/unit/evidence/**`, `backend/tests/integration/extraction/**`,
`backend/tests/integration/evidence/**`, `fixtures/extraction/**`, per
the task brief's allowed paths. `frontend/**`, `modules/companies/**`,
`modules/imports/**`, `modules/discovery/**`, `modules/crawling/**`,
`backend/app/main.py`, `backend/app/api/**`, and `tools/**` must remain
untouched — verify with `git diff --stat` against every other module
before merge, same as Task 006.

## Cross-module gateway decisions

Resolved in the contract, not left for the generator to discover — see
the contract's "Cross-module dependency decisions" section:

1. `CrawlExtractionGateway` — real adapter, wraps `modules/crawling`'s
   public `get_crawl_repository`/`get_content_storage` DI functions.
2. `CompanyExtractionGateway.update_latest_extraction_run` — documented
   no-op (same shape as Task 006's `update_latest_crawl_run` gap).
3. `CompanyExtractionGateway.project_latest_facts` — documented no-op,
   larger gap than #2 (no field exists yet on `Company` to write into).
4. `CompanyExtractionGateway.update_processing_status` — real, uses the
   already-existing `EXTRACTING`/`EXTRACTED` transitions.
5. `extraction` ↔ `evidence` — a gateway port
   (`extraction/domain/gateway.py`'s `EvidenceGateway`), not a direct
   cross-module repository import, even though both ship in this task.

## Status log

- Contract produced and saved to `docs/contracts/active/`.
- Generator build starting in an isolated git worktree, mirroring Task
  006's build pattern.
- 2026-07-26: generator agent (`a783357ea88cf5a4f`) built the full
  module set (extraction + evidence, all T1-T31 items, 129 files) but
  the session ran out of tokens before committing or handing off to
  the evaluator — work sat uncommitted in the worktree overnight.
- 2026-07-27: investigated the stalled worktree
  (`.claude/worktrees/agent-a783357ea88cf5a4f`, branch
  `worktree-agent-a783357ea88cf5a4f`). Verified no stub/TODO/
  `NotImplementedError` markers, no out-of-scope file changes, fixture
  set matches brief section 26, and both unit and integration suites
  pass (151 unit + 52 integration, `pytest backend/tests/unit/extraction
  backend/tests/unit/evidence backend/tests/integration/extraction
  backend/tests/integration/evidence`). Committed the work as
  `618888b` on the worktree branch. Handing off to the evaluator agent
  against the contract next.
- 2026-07-27: evaluator reported **PASS**. 203 tests (151 unit + 52
  integration), `ruff` and `pyright` clean on every new/changed path,
  zero scope leakage, all 5 cross-module gateway resolutions match the
  contract exactly. Two non-blocking Important gaps noted for future
  follow-up (not required for this PASS): (1) `test_pattern_coverage.py`
  cites a shared generic no-signal test as the false-positive coverage
  for `click_and_collect`/`subscription`/`booking`/`custom_products`
  instead of dedicated per-rule ambiguous-context fixtures — only
  `wholesale`/`trade_accounts` have real dedicated ones; (2) AC-27's
  literal test name
  (`test_structured_extraction_service.py::test_every_accepted_fact_has_evidence_and_rule_ids`)
  doesn't exist as a committed test, though the evaluator independently
  verified the underlying behavior (every accepted fact has non-empty
  `reconciliation_rule_ids` and resolvable `evidence_ids`) via a
  temporary scratch test. Merged to `main` via `git merge --no-ff
  worktree-agent-a783357ea88cf5a4f`. This file and the contract move to
  their `completed/` counterparts as part of this same update.

Status: **Done.**
