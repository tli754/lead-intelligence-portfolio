# Feature Contract: Task 014 — StoreLeads import UI (replaces `ImportPage.tsx`)

Task brief: `docs/execution-plans/tasks/014-StoreLeads-Import-UI.md`

Binding architectural precedent: `docs/decisions/0002-storeleads-import-targets-modules-imports.md`
(Accepted). That ADR fully specifies the two endpoints this task wires up —
exact request/response JSON, all enum wire-values, and field-normalization
rules the UI must not re-derive or contradict. This contract does not repeat
those details; it says where they land in the frontend and resolves the two
product questions the ADR deliberately left open (both answered directly by
the user — see the task brief).

No dependency on Tasks 010-013 landing in any particular order; this task
reuses their established client/hook conventions
(`API_BASE_URL`, per-feature error class, `queries.ts` composing hooks) but
has no runtime coupling to any of them.

# Feature

## Business Goal

The only import UI that currently exists (`ImportPage.tsx`) writes to the
`companies` collection via the legacy `domains/companies` pipeline, which
nothing else in the app reads — companies imported today are invisible on
`CompaniesPage`, `CompanyDetailPage`, and to the discovery/crawling/
extraction pipeline. `modules/imports` is fully built, tested, and
registered (`backend/app/main.py:32,66`) but has no frontend caller. This
task closes that gap for the one HTML-import format that carries
platform/country/city.

## User Story

As a user pasting a StoreLeads HTML `<table>` export, I want to preview
what will be imported (with per-row validation and duplicate detection)
before committing, so I can catch bad rows and see the results actually
appear elsewhere in the app afterward.

## Business Value

Makes the `modules/imports` pipeline (built, but dark since it shipped)
usable by a human for the first time, and — per ADR 0002 — the first
import path whose output every other page in the app can actually see.

# Architecture Impact

## Affected domains / services / repositories

None. No backend code changes — both endpoints already exist, are already
tested, and are already registered in `main.py`. If, during implementation,
they turn out to be genuinely insufficient (not just inconveniently
shaped), stop and report the gap; do not add or change backend endpoints
under this contract.

## Affected APIs

Consumes, unchanged:
- `POST /api/imports/storeleads/preview` → `ImportPreviewResponse`
- `POST /api/imports/storeleads` → `ImportResultResponse`

(Both defined in `backend/app/modules/imports/api/schemas.py` /
`api/router.py`; shapes reproduced in full in ADR 0002.)

## Affected database collections

None directly — commit writes to `companies_pipeline` via the existing
`CompanyServiceImportGateway`, unchanged by this task.

## Affected frontend

- `frontend/src/pages/ImportPage.tsx` — full rewrite.
- `frontend/src/pages/ImportPage.test.tsx` — full rewrite.
- `frontend/src/api/imports.ts` — new file.
- `frontend/src/schemas/imports.ts` — new file.
- `frontend/src/api/queries.ts` — two new hooks added.
- `frontend/src/api/companies.ts` — `importCompanies`/`ImportRequestError`
  removed (dead once `ImportPage.tsx` no longer calls them).
- `frontend/src/types/company.ts` — deleted in full (every export is
  legacy-import-only; see "Known Shape Gaps" #5).
- `frontend/src/App.tsx` — **not** changed. Same route, same path
  (`/import`), same component name, only its contents differ.

# Cross-module dependency decisions

Both product questions ADR 0002 left open are resolved here, binding on
this implementation:

1. **UI placement**: `ImportPage.tsx` is replaced wholesale. Not a second
   tab, not a new route.
2. **Legacy flow**: the plain-domain-list paste and "quick add domain"
   form are dropped entirely, not kept alongside the new flow. Backend
   cleanup (`domains/companies/*`, `POST /api/companies/import`, the
   `companies` collection) remains explicitly out of scope, per ADR 0002's
   "Consequences" section — this task only removes the now-dead *frontend*
   caller.

# Known Shape Gaps (binding on the implementation)

1. **No server-side preview session.** Commit resubmits the full `html`
   string, not row IDs from a prior preview (ADR 0002, confirmed in
   `ImportService`'s docstring). The page must track the exact HTML string
   that was last successfully previewed (`previewedHtml`) and disable
   "Confirm import" whenever the live textarea value differs from it —
   otherwise a user could commit something they never actually reviewed.
   Show a "Textarea changed since preview — preview again" hint when they
   diverge, rather than silently allowing a stale commit.
2. **No partial commit.** There is no mechanism to submit a filtered
   subset of rows (ADR 0002, "Explicitly open questions"). The UI must not
   offer row checkboxes/exclusion — every previewed row is committed.
3. **Enum wire-values are exactly as ADR 0002 documents them**:
   `validationStatus`: `"valid"` | `"invalid"`. `duplicateStatus`: `"new"`
   | `"existing"` | `"duplicate_in_file"` | `"unknown"`. `outcome`: `null`
   on every preview row, one of `"created"` | `"skipped_existing"` |
   `"skipped_invalid"` | `"failed"` on every commit-result row. Validate
   these client-side with Zod (`schemas/imports.ts`) so a future backend
   enum addition fails loudly (a Zod parse error) instead of silently
   rendering an undefined badge.
4. **`platform`/`country`/`city` display**: `platform: null` renders as an
   explicit "unknown platform" badge, not an error and not inferred from
   the domain (the backend normalizer deliberately doesn't infer it —
   don't second-guess that client-side). `country`/`city` are free text,
   render as-is, blank/`null` renders as an em-dash or "—", no geocoding.
5. **`website` vs `normalizedDomain`**: always display `website` (the raw
   pasted cell text) in the row table — `normalizedDomain` is `null`
   exactly when `validationStatus` is `"invalid"`, i.e. precisely when the
   user most needs to see what was actually pasted. Show
   `normalizedDomain` as a secondary/muted value when present, never as
   the only rendered identifier for a row.
6. **`errors[].message` is a UI-facing string list, not a stable enum**
   (ADR 0002) — render it as plain text per invalid row; do not attempt to
   map it to icons/categories beyond the existing `validationStatus`
   badge.
7. **Legacy code deletion is safe, not deferred**: confirmed via grep that
   `importCompanies`/`ImportRequestError` (`api/companies.ts`) and every
   export of `types/company.ts` (`Company`, `CompanySource`,
   `SkippedInvalidEntry`, `DetectedFormat`, `ImportResponse`) have no
   callers outside `ImportPage.tsx`/`ImportPage.test.tsx`. Delete them as
   part of this task's rewrite, not as a separate follow-up.

# Implementation Tasks

**T1 — Client** (`frontend/src/api/imports.ts`, new): `StoreLeadsImportRequestError`
error class; DTO interfaces matching the wire shape 1:1 (`ImportRowErrorDto`,
`ImportRowDto`, `ImportBatchSummaryDto`, `ImportPreviewResponseDto`,
`ImportResultResponseDto`); `previewStoreLeadsImport(html)` →
`POST /api/imports/storeleads/preview`; `commitStoreLeadsImport(html)` →
`POST /api/imports/storeleads`. Follow `companyDetail.ts`'s style
(own `API_BASE_URL`, local `FastApiErrorBody`/`extractErrorMessage`).

**T2 — Zod validation** (`frontend/src/schemas/imports.ts`, new): enum
schemas for `validationStatus`/`duplicateStatus`/`outcome` per gap #3;
client functions in T1 `.parse()` the response before returning.

**T3 — Hooks** (`frontend/src/api/queries.ts`): add
`useStoreLeadsPreview()` and `useStoreLeadsCommit()`, each a thin
`useMutation` wrapper around T1's client functions. Two separate mutations,
not one hook hiding both steps — matches two independently-rendered user
actions and this file's existing one-hook-per-call convention.

**T4 — Page rewrite** (`frontend/src/pages/ImportPage.tsx`): paste
textarea → "Preview" button → summary stat badges (rowsFound/validRows/
invalidRows/existingCompanies/duplicateRowsInFile/importableRows) → per-row
`@/components/ui/table` (columns: row#, website, normalizedDomain,
platform, country, city, validationStatus, duplicateStatus, errors) →
"Confirm import" button (gated per gap #1) → final per-row table with
`outcome` badges → "Start over" button resetting both mutations and the
textarea. No `dangerouslySetInnerHTML` anywhere — preserve the existing
docstring's explicit callout about this.

**T5 — Test rewrite** (`frontend/src/pages/ImportPage.test.tsx`): see
"Required Tests" below.

**T6 — Legacy removal**: delete `importCompanies`/`ImportRequestError`
from `api/companies.ts`; delete `frontend/src/types/company.ts` in full;
re-grep after T4/T5 land to confirm zero remaining references before
deleting.

# Acceptance Criteria

- AC-01: Pasting a valid StoreLeads `<table>` HTML sample and clicking
  "Preview" renders the summary counts and a row per parsed table row,
  each with correct `validationStatus`/`duplicateStatus` badges.
- AC-02: An invalid row (bad `website`) shows its `errors[].message` text
  inline and a `"invalid"` badge; `normalizedDomain` renders empty/absent
  for that row, `website` still renders (gap #5).
- AC-03: `platform: null` renders as an explicit "unknown" state, never
  blank/undefined and never inferred from the domain.
- AC-04: Editing the textarea after a successful preview disables "Confirm
  import" and shows the "preview again" hint until a new preview matching
  the current textarea value succeeds.
- AC-05: Clicking "Confirm import" after a matching preview calls
  `commitStoreLeadsImport` with the same `html` string and renders the
  final per-row `outcome` badges (all four outcome values covered across
  test fixtures).
- AC-06: A preview or commit request rejection renders a visible error
  message (via `StoreLeadsImportRequestError`), not a silent failure or
  crash.
- AC-07: "Start over" clears the textarea, both mutation states, and any
  rendered results.
- AC-08: No row-selection/checkbox affordance exists anywhere (gap #2 —
  no partial commit capability).
- AC-09: The legacy plain-domain-list paste and quick-add form are gone;
  `importCompanies`/`ImportRequestError`/`types/company.ts` are deleted
  with zero remaining references (`pnpm run build`/`tsc --noEmit` clean).
- AC-10: `App.tsx`'s `/import` route is unchanged (same path, same
  component name).

# Required Tests

- `frontend/src/api/imports.ts` unit tests: happy path for both functions;
  every `validationStatus`/`duplicateStatus` (incl. `"unknown"`)/`outcome`
  value round-trips through the Zod schema; non-ok response → typed error
  via both FastAPI `detail`-string and validation-array cases.
- `ImportPage.test.tsx` (same `vi.spyOn` convention, now on `../api/imports`):
  renders textarea + "Preview" button, "Confirm import" absent/disabled
  pre-preview; preview success renders summary + rows + invalid-row error
  text; preview failure renders an error alert; textarea edited after
  preview disables commit + shows hint; commit success renders all four
  outcome values across fixture rows; commit failure renders an error
  alert; "Start over" resets everything; loading spinners on both buttons
  while their respective mutation is pending.

# Risks

- **Risk**: large StoreLeads pastes (hundreds of rows) render as a single
  unvirtualized `<Table>`, no pagination.
  **Mitigation**: accepted as a v1 limitation — not specced by ADR 0002;
  `rowsFound` is visible in the summary to inform a follow-up if this
  becomes a real complaint.
- **Risk**: deleting `types/company.ts` and `companies.ts` exports could
  break an unnoticed caller.
  **Mitigation**: grep-confirmed zero external callers before this
  contract was written; re-confirm with a final grep plus a clean
  `tsc --noEmit` before merge (AC-09).

# Dependencies

`POST /api/imports/storeleads/preview`, `POST /api/imports/storeleads` —
both already exist, already registered, already tested. No dependency on
Tasks 010-013.

# Suggested Implementation Order

1. T1 + T2 (client + Zod validation) — independently testable against a
   running backend or mocked fetch.
2. T3 (hooks) — thin wrappers, quick.
3. T4 (page rewrite) — the bulk of the work.
4. T5 (test rewrite) — alongside or immediately after T4.
5. T6 (legacy removal) — last, once T4/T5 are green and a final grep
   confirms no remaining references.

# Success Criteria

All acceptance criteria pass; `pnpm run test` and `tsc --noEmit` (or
`pnpm run build`) are clean; `git diff --stat` confined to the files
listed in "Affected frontend"; no backend files touched; a manual smoke
test (paste a real fixture from `fixtures/storeleads/`, preview, commit)
shows the created company subsequently visible on `CompaniesPage`.
