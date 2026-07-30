# Execution Plan: StoreLeads Import UI (Task 014)

Status: Done
Contract: `docs/contracts/completed/014-storeleads-import-ui.md`
Task brief: `docs/execution-plans/tasks/014-StoreLeads-Import-UI.md`
ADR implemented: `docs/decisions/0002-storeleads-import-targets-modules-imports.md`

Frontend-only task, replacing the paste-in importer's single-shot flow
with a paste -> preview -> commit flow against `modules/imports`' two
already-built, already-tested endpoints. No backend changes. Plan
produced interactively (plan mode) with the user resolving ADR 0002's
two explicitly-open product questions via `AskUserQuestion` before the
contract was written: (1) `ImportPage.tsx` is replaced wholesale, not
given a second tab or a new route; (2) the legacy plain-domain-list
paste / quick-add form is dropped entirely, not kept alongside the new
flow. Implementation done directly in this session (no isolated
worktree/generator hand-off), with a real `evaluator` agent pass for
independent verification before merge, per CLAUDE.md's Task workflow.

## Scope

New: `frontend/src/api/imports.ts` (typed client —
`previewStoreLeadsImport`/`commitStoreLeadsImport`,
`StoreLeadsImportRequestError`, mirroring `companyDetail.ts`'s style),
`frontend/src/schemas/imports.ts` (Zod schemas pinning every
`validationStatus`/`duplicateStatus`/`outcome` wire-enum value),
`frontend/src/api/imports.test.ts` (17 tests exercising the real
fetch/JSON/Zod code path, not a mocked client).

Changed: `frontend/src/api/queries.ts` (two new `useMutation` hooks,
`useStoreLeadsPreview`/`useStoreLeadsCommit` — the file's first
mutation hooks), `frontend/src/pages/ImportPage.tsx` (full rewrite:
paste textarea -> Preview -> summary badges + per-row table -> Confirm
import, gated on a `previewedHtml` staleness check since commit
resubmits the full HTML string with no server-side preview session ->
final per-row outcome table -> Start over), `frontend/src/pages/
ImportPage.test.tsx` (full rewrite, 11 tests).

Removed: `importCompanies`/`ImportRequestError` from
`frontend/src/api/companies.ts`; `frontend/src/types/company.ts`
deleted in full (every export was legacy-import-only) — confirmed via
repo-wide grep, by both the generator and independently by the
evaluator, that nothing outside `ImportPage.tsx`/`ImportPage.test.tsx`
referenced any of it.

Zero changes to `backend/**` or `frontend/src/App.tsx` (the `/import`
route keeps its path and component name; only `ImportPage`'s contents
changed).

## Status log

- ADR 0002 (already Accepted, found untracked in git status) identified
  as the binding precedent; its two explicitly-open product questions
  put to the user via `AskUserQuestion` and resolved before contract
  work began.
- Plan mode: one `Explore` pass over the current frontend import UI/
  client/hook conventions, one `Plan` agent pass to design the concrete
  file-by-file implementation, both independently spot-checked (grep,
  direct file reads) before the plan was finalized and approved.
- Task brief (`docs/execution-plans/tasks/014-StoreLeads-Import-UI.md`)
  and feature contract (`docs/contracts/active/014-storeleads-import-ui.md`
  at the time) written next, per CLAUDE.md's Asked/Decided/Built
  workflow — contract structured on the `wire-company-detail-to-real-api`
  template (Known Shape Gaps, T1-T6 implementation tasks, AC-01..AC-10).
- Implementation done directly in this session, in contract order
  (T1/T2 client+Zod, T3 hooks, T4 page rewrite, T5 test rewrite, T6
  legacy removal), with `pnpm run test`/`tsc --noEmit`/`vite build` run
  after each major step rather than only at the end.
- First evaluator pass: **FAIL** — every acceptance criterion and known
  shape gap independently verified as met, automated checks clean, but
  the contract's "Required Tests" bullet for the new `imports.ts`
  client had no dedicated test file at all (every sibling client module
  in the repo has one). Fixed immediately: added
  `frontend/src/api/imports.test.ts` (17 tests, real fetch/Zod code
  path, every enum value, both FastAPI error-detail shapes).
- Second evaluator pass: **PASS**. Re-verified the new test file
  actually exercises real code (not mocked-out client functions),
  re-ran the full suite (117 passed) and `tsc --noEmit` clean,
  re-confirmed `git diff --stat` scope matched the contract exactly
  plus the one new test file it mandates. Flagged one non-blocking gap:
  `ImportPage.test.tsx` asserted the Preview button's pending spinner
  but not the Confirm-import button's — implemented correctly, just
  untested.
- Follow-up applied immediately (trivial, contract wording literally
  requires "loading spinners on both buttons"): added the missing
  commit-button pending-spinner test. Full suite re-verified green
  (118 passed) and `tsc --noEmit` clean afterward.
- Contract moved from `docs/contracts/active/` to
  `docs/contracts/completed/` as part of this same update.

Status: **Done.**

Known limitations carried forward (documented in the contract, not
defects): no pagination/virtualization for very large StoreLeads pastes
(hundreds of rows render in a single unvirtualized table) — not specced
by ADR 0002, deferred as a v1 limitation. Editing the textarea and
re-clicking Preview while a prior preview is showing briefly hides the
whole preview card (summary/rows/hint/Confirm) for the duration of the
new request, since TanStack Query's `useMutation` resets `isSuccess` on
`mutate()` — not a violation of any acceptance criterion, flagged by
the evaluator as a UX gap worth knowing about, not fixed under this
contract. Backend cleanup (`domains/companies/*`,
`POST /api/companies/import`, the `companies` collection, and any
company documents already sitting in it) remains explicitly out of
scope, per ADR 0002's own "Consequences" section.
