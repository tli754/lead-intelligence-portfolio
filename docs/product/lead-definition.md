# Lead Definition

This is a minimal, deliberately scoped note. It exists so the term
"Lead" is not silently overloaded before a real, scored definition of it
is designed.

## What exists today: two `Company` models

There are currently **two separate, unreconciled implementations** of
`Company` in this codebase (see `ARCHITECTURE.md`'s "Module convention"
fork note and `docs/architecture/mongodb-design.md` for the full
technical detail). Both are still unscored — neither promotes a company
into anything resembling a "Lead" — but they model different things:

**1. The paste-in importer's `Company`** (`backend/app/domains/companies/`,
`companies` collection):

- A domain the user pasted or copied from storelead.app.
- Optionally enriched with whatever storelead.app's HTML export
  happened to include for that row (estimated yearly sales, a created
  date, emails, phones, the store's own URL).
- Immutable once created — raw input data, not a business decision.

**2. The pipeline-tracking `Company`** (`backend/app/modules/companies/`,
`companies_pipeline` collection):

- Tracks a company's `processing.status` (imported → discovering →
  ... → ready/failed/stale) and `workflow.manual_status` (a human
  reviewer's disposition: unreviewed → ... → customer/archived).
- Mutable — status transitions are the point of this model, validated
  against an explicit allowed-transition graph
  (`backend/app/modules/companies/domain/transitions.py`).
- Its `GET /api/companies` list response already has `opportunityScore`,
  `confidence`, and `mainReason` fields in the JSON contract — but they
  are hardcoded `null` in the API mapper
  (`backend/app/modules/companies/api/schemas.py`), not backed by any
  real scoring logic. Treat these as reserved API surface, not as
  scoring having been implemented.
- Nothing currently promotes a record from model 1 into model 2 — they
  are populated independently.

The frontend's `/companies`, `/companies/:id`, and `/jobs` pages
(`frontend/src/schemas/company.ts`) go further still: their Zod
contracts include `score`, `confidence`, and `evidence` fields, backed
only by mock fixture data (`frontend/src/api/mock/`), not by either
backend `Company` model above. This is explicitly ahead of the backend
on the frontend side only — see
`docs/execution-plans/completed/companies-frontend-mock-ui.md`.

## What "Lead" is not, yet

"Lead" is reserved for a future feature that defines how a `Company`
gets promoted into a scored/qualified entity (e.g. via a `LeadScore`
produced by the Scoring stage of the pipeline: Ingestion → Crawling →
Interpretation → **Scoring** → MongoDB → API → Frontend). That feature
will define:

- What signals feed a score (crawled site content, AI-interpreted
  signals, the raw `Company` fields above, etc.).
- What the score represents and how it's computed (in Python — AI
  output is interpretation input, never the business decision itself;
  see `ARCHITECTURE.md` and the AI rules referenced there).
- What promotes a `Company` into whatever "Lead" ends up meaning.

Until that feature exists, do not introduce a `Lead` model, collection,
or API response anywhere in the codebase — use `Company` for anything
representing an imported-but-unscored record.
