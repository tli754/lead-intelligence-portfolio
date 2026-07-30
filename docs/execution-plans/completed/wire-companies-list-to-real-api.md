# Execution Plan: Wire Companies List to the Real Backend API (Task 010)

Status: Done
Contract: `docs/contracts/completed/wire-companies-list-to-real-api.md`
Task brief: `docs/execution-plans/tasks/010-Wire-Companies-List-to-Real-API.md`

First of three follow-up tasks (010, 011, 012) splitting "wire the
frontend off mock data" into small, independently-planned pieces, per
CLAUDE.md's Task workflow. Contract produced directly (not via a
separate planner agent pass) after inspecting the actual backend/
frontend code for the concrete shape mismatches; generator build done
in an isolated git worktree, mirroring Tasks 006/007's pattern.

## Scope

Isolated to `backend/app/modules/companies/api/schemas.py` (one
additive field), `backend/tests/{unit,integration}/companies/**`
(assertions for that field), and the frontend's companies-list path:
`frontend/src/api/companies.ts`, `frontend/src/api/queries.ts`,
`frontend/src/pages/CompaniesPage.tsx` (+ test), `frontend/src/schemas/
company.ts` (enum coverage only). One narrow, pre-authorized extension
beyond the original allowed paths: `frontend/src/components/status/
ProcessingStatusBadge.tsx`/`WorkflowStatusBadge.tsx`, needed because
widening the enum schemas made their exhaustive `Record<>` maps
incomplete and broke `pnpm run build`.

## Status log

- Contract produced and saved to `docs/contracts/active/`, based on a
  direct reading of the real `GET /api/companies` response shape versus
  the frontend's mock-derived Zod schemas — not a separate planner-agent
  pass.
- Generator build in an isolated git worktree
  (`.claude/worktrees/agent-acca76fd0ba5def4a`, branch
  `worktree-agent-acca76fd0ba5def4a`), committing after each of T1
  (backend `updatedAt`), T4 (enum schema fixes), T3+T2 (adapter + real
  client), T5 (wiring) per the contract's suggested order, so a
  token-exhausted session would leave a working state — this time it
  didn't run out, but the checkpointing discipline held.
- Generator flagged a real gap during its own verification: widening
  `ProcessingStatus`/`WorkflowStatus` (required by AC-03) left
  `ProcessingStatusBadge.tsx`/`WorkflowStatusBadge.tsx`'s exhaustive
  `Record<>` maps incomplete, breaking `pnpm run build`/`tsc --noEmit`.
  Authorized as a narrow, necessary scope extension; generator added the
  6 missing map entries as a separate commit (`fca3784`) and confirmed
  the build passes.
- First evaluator pass: **FAIL**. 7 of 8 acceptance criteria passed
  cleanly (all automated checks green: ruff, pyright, 74 backend tests,
  47 frontend tests, `tsc`/`build`), but AC-02 failed on live
  verification — the evaluator started the backend against the shared
  MongoDB and found that `ImportPage`'s paste-in importer
  (`backend/app/domains/companies`, collection `companies`) and the
  newly-wired `GET /api/companies` (`backend/app/modules/companies`,
  collection `companies_pipeline`) are two entirely separate,
  unreconciled `Company` models — a company pasted in via `ImportPage`
  never appears on the real `CompaniesPage`. This split is already
  documented as deliberate in `docs/product/lead-definition.md`, so this
  was a contract-authoring defect (AC-02's premise), not an
  implementation defect.
- Asked the user how to resolve it (AskUserQuestion: narrow the contract
  and merge now / block on a reconciliation task first / merge as-is and
  document as a known gap). User chose to narrow the contract and merge
  now, deferring reconciliation to a new task.
- Corrected the contract's Business Goal, User Story, Business Value,
  and AC-02 to scope to companies created via `modules/companies`'s API
  directly, added a "Known Limitation" section documenting the
  `domains/companies`/`modules/companies` split, and opened
  `docs/execution-plans/tasks/013-Reconcile-Domains-and-Modules-
  Companies.md` recording the deferred reconciliation work. Committed
  this correction to `main` ahead of the merge.
- Second evaluator pass, against the corrected contract: **PASS**.
  Independently re-verified AC-02 live (created a company via
  `POST /api/companies`, confirmed it appears via `GET /api/companies`
  in exactly the shape the frontend's adapter/schema pipeline expects,
  cleaned up the test record). All other ACs unaffected by the contract
  edit, already verified with concrete evidence in the first pass.
  Confirmed scope discipline, the badge-config fix's correctness and
  minimality, and both of the generator's documented deviations (no
  required-to-optional schema change was actually needed;
  `country`/`page`/`pageSize` correctly omitted from the client since
  `CompanyListFilters` has no such fields).
- Merged to `main` via `git merge --no-ff worktree-agent-
  acca76fd0ba5def4a`. This file and the contract move to their
  `completed/` counterparts as part of this same update.

Status: **Done.**

Known limitation carried forward (not a defect in this task): companies
created via `ImportPage`'s paste-in importer do not appear on
`CompaniesPage` — see `docs/execution-plans/tasks/013-Reconcile-
Domains-and-Modules-Companies.md`.
