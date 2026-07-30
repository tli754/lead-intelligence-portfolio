# Execution Plan: Companies Ranking/Detail/Jobs Frontend (Mock Data)

Status: Complete
Contract: none written — built directly from an ad-hoc task brief, not
through the planner→contract workflow used by `paste-in-importer`.

## What was built

Four routed pages (`react-router-dom`, added as a new dependency —
previously the frontend had no router, per `ARCHITECTURE.md`'s "introduce a
router when a second page is needed" note):

- `/import` — the existing paste-in importer screen, now living under a
  shared `Layout` nav bar instead of being rendered directly by `App.tsx`.
- `/companies` (`src/pages/CompaniesPage.tsx`) — company ranking table.
  TanStack Table for sortable columns; filters (search text, processing
  status, workflow status, platform) sent through the mock API's query-param
  contract rather than filtered client-side, so a real backend list endpoint
  could take over unchanged.
- `/companies/:companyId` (`src/pages/CompanyDetailPage.tsx`) — identity,
  processing timeline, score breakdown, and an evidence viewer
  (`src/components/EvidenceViewer.tsx`) that groups evidence by field and
  flags disagreeing values as conflicts.
- `/jobs` (`src/pages/JobsPage.tsx`) — read-only pipeline job queue view.

## Data layer

- `src/schemas/company.ts`, `src/schemas/job.ts` — Zod contracts shaped to
  match what a future FastAPI endpoint should return (mirrors the backend
  `modules/companies` domain's `identity`/`processing`/`workflow` nesting;
  extends it with `score`/`confidence`/`evidence` for the not-yet-built
  scoring feature).
- `src/api/mock/fixtures.ts` — 13 hand-authored companies covering the
  required review scenarios (high score, low score, high-score/
  low-confidence, in-progress, partial, failed, conflicting evidence,
  unknown values, stale analysis, plus a few ordinary ones) and 8 pipeline
  jobs.
- `src/api/mock/client.ts` — filters/sorts the fixtures and validates the
  result through the same Zod schemas a real `fetch()` client would use.
  Swapping this file's function bodies for real HTTP calls is the only
  change needed later; callers (`src/api/queries.ts` TanStack Query hooks,
  the pages) don't change.
- **Not wired to the real backend.** Only `/import` calls the real FastAPI
  backend (`POST /api/companies/import`) — verified end-to-end against a
  running backend + MongoDB. `/companies`, `/companies/:id`, and `/jobs` run
  entirely on the mock layer above.

## Reusable components

`src/components/status/` — `ProcessingStatusBadge`, `WorkflowStatusBadge`,
`JobStatusBadge`, `ConfidenceMeter`, built on a fixed status-tone palette
(good/warning/serious/critical, per the `dataviz` skill's reference
palette) with one categorical-violet accent for the "customer" workflow
milestone. Every badge pairs a color dot with a text label — never color
alone.

## Testing

19 Vitest + React Testing Library tests: ranking table rendering/filtering/
sorting, company detail rendering, unknown-value placeholders, failed
processing status, evidence viewer (incl. conflict detection and the
empty-evidence state). Strict-mode `tsc` and `vite build` both pass.

## Known gaps / not done

- `score`/`confidence`/`evidence`/`jobs` concepts don't exist in any backend
  model yet — the mock contracts are forward-looking, not backed by a real
  endpoint. `docs/product/lead-definition.md` currently reserves
  scoring-adjacent concepts for a future feature; this frontend work is
  ahead of that on the frontend side only, deliberately, per the task brief
  ("mock API layer... designed so the FastAPI backend can implement the
  same responses later").
- No importer↔pipeline-module linkage exists on the backend — nothing
  promotes an imported `Company` (paste-in importer) into a pipeline-tracked
  one (`modules/companies`).
