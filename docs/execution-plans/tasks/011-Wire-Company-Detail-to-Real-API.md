Task 011 — Wire the company detail page to the real backend API

Raised in conversation (not a pre-written brief), preserved here verbatim
as the record of what was actually asked. Second of three follow-up
tasks (010, 011, 012) — see Task 010 for the shared context on why these
were split out and pre-documented.

Ask, concretely: make `CompanyDetailPage` display real data instead of
`src/api/mock/fixtures.ts`, including real evidence (via `EvidenceViewer`),
by composing three already-live, already-tested endpoints — no new
backend endpoints anticipated:

- `GET /api/companies/{company_id}` (modules/companies) — identity,
  processing status, workflow status.
- `GET /api/companies/{company_id}/facts` (modules/extraction) — accepted
  facts, each with `field_path`, `evidence_ids`.
- `GET /api/facts/{fact_id}/evidence` (modules/extraction, backed by
  modules/evidence) — evidence records per fact (excerpt, source_url,
  strength, observed_at, etc.).

Allowed paths:

- frontend/src/api/companies.ts (or a new sibling client file) — add
  get-company-detail, list-facts, and list-fact-evidence functions
- frontend/src/api/queries.ts — real `fetchCompanyById`-equivalent hook
- frontend/src/pages/CompanyDetailPage.tsx and its test file
- frontend/src/components/EvidenceViewer.tsx — only if the real evidence
  shape needs a prop-level adjustment; do not redesign its grouping/
  conflict-flagging logic
- frontend/src/schemas/company.ts — only to relax fields the real API
  genuinely cannot supply yet (see below), not to add new ones

Do not modify:

- frontend/src/pages/CompaniesPage.tsx, frontend/src/pages/JobsPage.tsx
- frontend/src/api/mock/** (JobsPage still depends on it until Task 012)
- backend/app/modules/companies/**, backend/app/modules/extraction/**,
  backend/app/modules/evidence/** — this task is frontend-only; if the
  three existing endpoints turn out to be genuinely insufficient (not
  just inconveniently shaped), stop and report the gap rather than
  changing backend code under this task

Known shape gaps — these fields have no backend source yet and must be
defaulted, not fabricated:

- `score`, `score_factors` — no scoring module exists (confirmed absent
  from Task 008's AI-analysis brief too, which explicitly excludes
  opportunity scoring). Render as `null` / empty, and the UI should
  visibly show "not scored yet" rather than a blank/zero value.
- `url` — not on `CompanyResponse` and not a fact field either; derive it
  from `CompanyResponse.domain` (already returned by
  `GET /api/companies/{id}`), not from extraction facts.
- `emails`, `phones` — real field paths exist:
  `organisation.emails`, `organisation.phone_numbers` (see
  `modules/extraction/domain/field_catalogue.py`). Pull these from the
  accepted facts list by `field_path`, not fabricated.
- `evidence[].field` / `.label` — the real evidence response is keyed by
  `fact_field_path`, not the mock's `field`/`label` pair; map field_path
  to a human label the same way (or adjacent to how) `EvidenceViewer`
  already groups by field today.
- `evidence[].confidence` — the real evidence response has a 4-level
  `strength` (`weak`/`moderate`/`strong`/`authoritative`), not the
  frontend's 3-level `confidence` (`high`/`medium`/`low`). Needs an
  explicit, documented mapping (e.g. `authoritative`/`strong` -> `high`,
  `moderate` -> `medium`, `weak` -> `low`) — do not guess ad hoc in the
  component.
- `evidence[].conflicts_with` — `GET /api/facts/{fact_id}/evidence`
  returns evidence for one *accepted* (already conflict-resolved) fact;
  it does not carry a per-evidence-item list of contradicting evidence
  IDs. True cross-value conflict data lives in a separate, unfetched
  resource (`FactConflictResponse`, keyed by `field_path`+`candidate_ids`,
  not evidence IDs). Default `conflicts_with` to `[]` for this task and
  document the "Conflicting evidence" banner as not yet wired to real
  data — wiring it up for real is a follow-up task, not part of this one.

Out of scope:

- Any change to what facts/evidence exist (that's extraction/evidence
  modules' job, already built).
- JobsPage and companies-list wiring (Tasks 012 and 010).
- Pagination on the facts/evidence composition — company detail is a
  single-entity view; if a company has more facts/evidence than one
  page (`pageSize` defaults), fetch enough pages to be complete or
  document the cap chosen, rather than silently truncating.
