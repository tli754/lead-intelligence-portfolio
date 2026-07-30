# Feature Contract: Task 011 — Wire the company detail page to the real backend API

Task brief: `docs/execution-plans/tasks/011-Wire-Company-Detail-to-Real-API.md`

Depends on Task 010 (companies list) landing first only insofar as it
establishes the real-client conventions (`API_BASE_URL`, error class
pattern) this task reuses — there is no runtime dependency; this task
can be built and tested independently against a company id typed
directly into the URL.

# Feature

## Business Goal

`CompanyDetailPage` currently renders `mock/fixtures.ts` data, including
fabricated evidence via `EvidenceViewer`. Three real, already-tested
endpoints exist that together contain everything the page needs except
score/score_factors (which don't exist anywhere in the system yet — no
scoring module). This task composes those three endpoints into one real
detail view.

## User Story

As a user viewing a company's detail page, I want to see its actual
accepted facts and the evidence backing them, sourced from real crawl/
extraction runs, so I can verify what the system actually found instead
of looking at fixture data.

## Business Value

Second of three steps (010/011/012). Makes the extraction+evidence
pipeline (Task 007) visible to a human for the first time outside of
direct API calls or tests.

# Architecture Impact

## Affected domains

None. No backend code changes anticipated (frontend-only task per the
brief). If, during implementation, the three existing endpoints turn out
to be genuinely insufficient (not just inconveniently shaped), stop and
report the gap — do not add backend endpoints under this contract.

## Affected services

None.

## Affected repositories

None.

## Affected APIs

Consumes, unchanged:
- `GET /api/companies/{company_id}` -> `CompanyResponse`
- `GET /api/companies/{company_id}/facts` -> `FactListResponse`
  (paginated; see AC-04 for the pagination-completeness requirement)
- `GET /api/facts/{fact_id}/evidence` -> evidence list (per fact,
  paginated)

## Affected database collections

None.

## Affected frontend pages

`CompanyDetailPage.tsx`, `EvidenceViewer.tsx` (prop-shape only, not its
grouping/conflict logic).

# Cross-module dependency decisions

None — frontend composes three already-public HTTP APIs; no new
cross-module backend wiring.

# Known Shape Gaps (binding on the implementation)

1. **Company summary fields.** `CompanyResponse` maps to
   `CompanyDetail`'s `identity`/`processing`/`workflow`/`score`/
   `confidence` the same way Task 010's adapter maps the list item
   (reuse that mapping logic if Task 010 has landed; duplicate it locally
   if not — do not block this task on Task 010's merge order).
2. **`url`**: `CompanyDetail.url` <- `CompanyResponse.domain`. Not a
   fact, not fabricated.
3. **`emails`/`phones`**: pulled from `GET .../facts` results by
   filtering `field_path === "organisation.emails"` /
   `"organisation.phone_numbers"`. These fields' `value`/
   `normalized_value` shape must be inspected at implementation time
   (likely a list already, given the field descriptions — "Deduplicated
   business email addresses" / "phone numbers" — verify against
   `modules/extraction/domain/extractors/organisation/organisation_extractor.py`
   before assuming a bare list vs. list-of-objects). If no such fact
   exists for a company, render `[]`, not an error.
4. **`score`/`score_factors`**: always `null` / `[]`. The UI must render
   an explicit "not scored yet" state — copy this from wherever
   `CompaniesPage` (Task 010) already renders a null score, for
   consistency between the two pages.
5. **Evidence composition**: for each fact returned by
   `GET .../facts`, call `GET /api/facts/{fact_id}/evidence` and flatten
   the results into `CompanyDetail.evidence`. N+1 request pattern is
   accepted for this task given company detail pages show a bounded
   number of facts (typically under `field_catalogue`'s total field
   count); do not add a bulk endpoint to avoid it.
6. **`evidence[].field`/`.label`**: `field` <- `fact_field_path` (the
   dotted path, e.g. `"business.wholesale"`); `label` <- a human string
   derived from it (e.g. title-cased tail segment, or reuse
   `field_catalogue.py`'s per-field label/description strings if
   accessible to the frontend build — more likely: implement a small
   local `FIELD_LABELS` map in the frontend keyed by the same dotted
   paths, since the catalogue itself is backend-only Python).
7. **`evidence[].confidence`**: map `EvidenceStrength` (backend:
   `weak`/`moderate`/`strong`/`authoritative`) to `ConfidenceLevel`
   (frontend: `low`/`medium`/`high`) via: `authoritative` -> `high`,
   `strong` -> `high`, `moderate` -> `medium`, `weak` -> `low`. Document
   this mapping as a named constant, not inline conditionals.
8. **`evidence[].conflicts_with`**: hardcode `[]` for every item in this
   task. `EvidenceViewer`'s "Conflicting evidence" banner will therefore
   never show for real data until a follow-up task wires in
   `FactConflictResponse` data (which is keyed differently — by
   `field_path`+`candidate_ids`, not evidence IDs — and needs its own
   design work to translate into per-evidence-item conflict flags). Note
   this explicitly in the PR/completion notes as a known limitation, not
   a silent gap.
9. **`evidence[].source`**: `EvidenceResponse` has no single `source`
   string field — nearest equivalents are `source_url` (already a
   separate `EvidenceItem` field) and `evidence_type`/`page_type`. Map
   `source` <- `evidence_type` (e.g. `"page_text"`, `"meta_tag"`) unless
   `page_type` reads better in the UI at implementation time — either is
   defensible; pick one and document it in the PR.

# Implementation Tasks

**T1 — Real client functions** (in `frontend/src/api/companies.ts` or a
new sibling file): `getCompany(id)`, `listCompanyFacts(id)`,
`listFactEvidence(factId)`, following Task 010's `API_BASE_URL`/error
pattern if it has landed, or `importCompanies`'s existing pattern
otherwise.

**T2 — Composition function**: `fetchCompanyDetail(id):
Promise<CompanyDetail>` that calls T1's three functions (paginating
through all pages of facts and, per fact, all pages of evidence — see
AC-04), applies the field mappings from "Known Shape Gaps" 1-9, and
returns a fully-formed `CompanyDetail`.

**T3 — Field label map**: a small `FIELD_LABELS: Record<string, string>`
(or function) covering every `FieldPath` value currently in
`field_catalogue.py`, for gap #6. Unknown/future field paths should fall
back to a readable default (e.g. the raw dotted path) rather than
crashing.

**T4 — Wiring**: `frontend/src/api/queries.ts`'s `useCompany` switches
from `fetchCompanyById` (mock) to `fetchCompanyDetail` (real).

# Acceptance Criteria

- AC-01: `CompanyDetailPage` for a real company (with accepted facts and
  evidence) renders identity, processing status, workflow status, and at
  least one evidence-backed fact group, sourced from real API calls
  (verifiable via network inspection or a mocked-fetch test asserting
  the three endpoints were called).
- AC-02: A company with zero accepted facts renders `EvidenceViewer`'s
  existing empty state (`"No evidence collected yet."`) — not an error,
  not an infinite loader.
- AC-03: `score`/`score_factors` render as an explicit "not scored yet"
  state, consistent with Task 010's list-page treatment of the same
  gap.
- AC-04: If a company has more facts or more evidence-per-fact than one
  page (`pageSize` default), `fetchCompanyDetail` paginates through all
  pages rather than silently truncating — verified with a fixture/mock
  scenario forcing more than one page.
- AC-05: Every `EvidenceStrength` value maps to a defined
  `ConfidenceLevel` (no `undefined` reaching `CONFIDENCE_TONE` in
  `EvidenceViewer`, which would throw on an unmapped key).
- AC-06: `conflicts_with` is always `[]` for real data (explicit, tested,
  not accidental) and the PR notes this as a known limitation.
- AC-07: `emails`/`phones` render as `[]` (not an error) for a company
  with no `organisation.emails`/`organisation.phone_numbers` fact.
- AC-08: `frontend/src/api/mock/**` untouched; `JobsPage` still works off
  it until Task 012.
- AC-09: `pnpm run test` passes for `CompanyDetailPage.test.tsx` and any
  new test files (T2 composition function, T3 label map).

# Required Tests

- Unit tests for T2's composition function: full pagination across facts
  and evidence, empty-facts company, missing-optional-field company,
  every `EvidenceStrength` -> `ConfidenceLevel` mapping.
- Unit tests for T3's label map: known field paths, unknown/fallback
  path.
- `CompanyDetailPage.test.tsx`: update to mock the real client functions
  (or fetch, per the test file's existing pattern) instead of the mock
  module; cover the zero-facts empty state and a populated case.

# Risks

- **Risk**: N+1 fetch pattern (one evidence request per fact) could be
  slow for a company with many accepted facts.
  **Mitigation**: accepted as a known tradeoff for this task's scope
  (see gap #5); `field_catalogue.py` bounds the total possible fact
  count per company, so this is not unbounded. Note as a follow-up
  optimization (e.g. a bulk `evidenceIds` endpoint) rather than solving
  it now.
- **Risk**: guessing wrong on gap #9 (`source` <- `evidence_type` vs.
  `page_type`) is a UI wording choice, not a functional bug — low
  severity either way.
  **Mitigation**: document the choice made; trivially changeable later.

# Dependencies

`GET /api/companies/{id}`, `GET /api/companies/{id}/facts`,
`GET /api/facts/{id}/evidence` — all already exist, already registered,
already tested (Tasks 006/007/009). No dependency on Task 012. Soft
dependency on Task 010 for shared adapter/client conventions only (not
blocking).

# Suggested Implementation Order

1. T3 (field label map) — no dependencies, independently testable.
2. T1 (three client functions) — independently testable against a
   running backend or mocked fetch.
3. T2 (composition function, including pagination and all field
   mappings) — the bulk of the work; commit once its own unit tests are
   green.
4. T4 (wire `useCompany`) — commit last.

# Success Criteria

All acceptance criteria pass; `git diff --stat` confined to the allowed
paths in the task brief; no backend files touched; evaluator confirms
gaps #8 (`conflicts_with`) and #4/#3 (`score`) are documented as known
limitations rather than silently hidden.
