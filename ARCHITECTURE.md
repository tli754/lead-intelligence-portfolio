# Architecture

This document describes the layering rules and directory conventions
established by the first feature in this repository (the paste-in
importer). Every subsequent feature must follow the same conventions
unless a new contract explicitly changes them.

## System overview

The product is a pipeline: **Ingestion → Crawling → Interpretation →
Scoring → MongoDB → API → Frontend**. This repository currently
implements the Ingestion stage (importing raw lead data pasted by a
user into structured `Company` records) and a second, separate
pipeline-tracking module (`backend/app/modules/companies/`) that
records *where* a company sits in Discovery/Crawling/Extraction/
Analysis/Scoring — without those stages existing yet. See "Module
convention (hexagonal variant)" below for why this is a second module
rather than an extension of the first.

## Layering rules

Each backend domain is organised as: **router → service → repository →
MongoDB**.

- **Routes are thin.** A router function validates the request via a
  Pydantic model (handled automatically by FastAPI), calls exactly one
  service method, and returns the result. Routes never talk to MongoDB
  directly and never contain business rules (dedupe, scoring, parsing,
  etc.).
- **Services own business logic.** All business rules — format
  detection, deduplication, orchestration between parsing and
  persistence, and any future scoring/qualification logic — live in a
  domain's `service.py`. Services depend on a repository (or a
  repository-shaped Protocol, for testability) and never import MongoDB
  driver code directly.
- **Repositories own MongoDB access.** All reads/writes for a domain's
  collection(s) are confined to that domain's `repository.py`. No
  dedupe or other business rules live in a repository — it only knows
  how to query/insert/update documents.
- **Configuration lives in configuration modules.** Environment
  variables are read only in `backend/app/config.py` via
  pydantic-settings. No other module reads `os.environ` directly.
- **Validation is Pydantic-based.** Every request/response model, and
  every MongoDB document shape, is defined as a Pydantic model in the
  owning domain's `models.py`. Hand-rolled validation in routes or
  services is not permitted where a Pydantic model can express the same
  constraint.

## Dependency direction

```
frontend  --HTTP-->  router  -->  service  -->  repository  -->  MongoDB
```

- The frontend never accesses MongoDB directly — only through the API.
- A router may depend on a service, but never on a repository or on
  MongoDB driver types.
- A service may depend on a repository (or a narrower Protocol
  describing the subset of methods it needs), but never on FastAPI
  request/response types or on MongoDB driver types directly (Motor
  types are confined to `repository.py` and `db.py`).
- A repository may depend on MongoDB driver types (Motor/pymongo), but
  never on service-layer business rules.

This direction is enforced by code review today (see AC-12 in the
paste-in importer contract); `tools/check_architecture.py` is reserved
for automating this check in a future feature and is currently a
0-byte stub.

## Domain module convention (flat variant)

Backend business domains live under `backend/app/domains/<name>/`, each
containing (as needed):

- `models.py` — Pydantic models: the domain's MongoDB document shape(s)
  plus request/response models.
- `repository.py` — MongoDB access for this domain's collection(s).
- `service.py` — business logic and orchestration.
- `parsing.py` — pure, I/O-free transformation functions, where a
  domain needs them (e.g. turning pasted text into structured rows).
- `router.py` — thin FastAPI route handlers.

The first domain implementing this convention is `companies`
(`backend/app/domains/companies/`), created by the paste-in importer
feature — immutable records in the `companies` collection, one per
imported store. `health` (`backend/app/domains/health/`) is a minimal
scaffolding-only domain with just a `router.py`, used to verify the
backend boots.

## Module convention (hexagonal variant)

A second convention now also exists: `backend/app/modules/<name>/`,
organised as **domain → application → infrastructure → api**
(ports-and-adapters), instead of the flat `models.py`/`repository.py`/
`service.py`/`router.py` files above:

- `domain/` — pure Pydantic models, enums, typed domain errors, and an
  abstract repository *interface* (`abc.ABC`, not a `Protocol`). Zero
  imports of FastAPI, Motor, or any other external SDK — stricter than
  the flat convention, which only forbids Mongo driver types in
  `service.py`.
- `application/` — business logic; depends only on the `domain/`
  repository interface, never a concrete Mongo class.
- `infrastructure/` — the Motor-backed implementation of that
  interface. All MongoDB access for the module is confined here.
- `api/` — FastAPI routes plus request/response DTOs. Where a module's
  JSON contract needs different casing than its domain fields (e.g.
  camelCase via a Pydantic `alias_generator`), that translation lives
  here, out of `domain/`.

First implementation: `companies` (`backend/app/modules/companies/`) —
tracks a company through the discovery→scoring pipeline (processing
status, manual review/workflow status) in its own `companies_pipeline`
collection. This is a **different `Company` model** from the flat
`domains/companies` one above, not an extension of it.

**This is an unreconciled fork, not a documented decision.** Two
conventions and two different `Company` models coexist here for
historical reasons — each was built by a separately-scoped task, not by
a single design decision. No ADR yet says which convention a new
module should follow, or whether/how the two `Company` concepts should
eventually be unified. Read the worked examples for both in
`docs/architecture/dependency-rules.md` before adding a new domain or
module, and raise this explicitly with whoever owns the next feature
that touches `companies` rather than silently picking one.

### Cross-module dependencies: the gateway/port pattern

A hexagonal module that needs data from *another* module (not MongoDB
directly) defines its own narrow `abc.ABC` **port** in its own `domain/`
— never imports the other module's repository or MongoDB collection.

Second implementation: `imports` (`backend/app/modules/imports/`) —
parses StoreLeads HTML and creates companies through `companies`. Its
`domain/gateway.py` defines `CompanyImportGateway` (`exists_by_domain`,
`create_imported_company`); `infrastructure/company_service_gateway.py`
is the adapter, wrapping the *other* module's own public application
service (`companies`' `CompanyService`, obtained via that module's own
`get_company_service` FastAPI dependency function) rather than
constructing `MongoCompanyRepository` itself. `modules/imports/` has
zero imports of Motor anywhere, and its only import from
`app.modules.companies` at all is that one service class plus the DI
function that builds it.

This is the same shape as the domain→infrastructure port pattern within
one module (an `ABC` interface in `domain/`, a concrete adapter in
`infrastructure/`), just crossing a module boundary instead of crossing
into MongoDB. Tests substitute a fake implementing the same port
(`FakeCompanyImportGateway` in `backend/tests/integration/imports/conftest.py`)
exactly as MongoDB-backed modules substitute a fake repository.

**Known limitation of the current adapter:** the target module
(`companies`) doesn't yet expose a public, non-mutating way to check
whether a domain already exists — only a mutating `create_company` that
internally raises a typed conflict error. `CompanyServiceImportGateway.exists_by_domain`
therefore always returns "unknown" today; import-time duplicate
detection still works correctly (it relies on that same typed conflict
error, not on `exists_by_domain`), but the `imports` module's *preview*
endpoint can't yet report an accurate "already exists" count. See
`docs/execution-plans/completed/imports-storeleads-html.md` for the
full write-up.

**Not yet reachable over HTTP:** unlike every other router described in
this document, `modules/imports/api/router.py` is not registered in
`backend/app/main.py` — it was built and tested (including real end-to-
end runs against a locally-constructed `FastAPI()` app in its own test
suite) but deliberately left unwired, per the task that created it. A
future task must add the `app.include_router(...)` call before
`POST /api/imports/storeleads` and `POST /api/imports/storeleads/preview`
are reachable outside tests.

## Frontend structure

- `frontend/src/pages/` — top-level screens, routed via `react-router-dom`
  (`App.tsx` defines `<Routes>`; `src/components/Layout.tsx` is the
  shared nav shell). A router was introduced once a second page
  (`/companies`) was added — the paste-in importer's `ImportPage` used
  to be the only screen and was rendered directly by `App.tsx`.
- `frontend/src/api/` — typed HTTP clients, one module per backend
  domain, calling `${VITE_API_BASE_URL}/api/...` (e.g. `companies.ts`,
  used by the real paste-importer integration).
- `frontend/src/api/mock/` — a **mock API layer** (`client.ts` +
  `fixtures.ts`) for pages not yet wired to a real backend endpoint
  (`/companies`, `/companies/:id`, `/jobs`). Validates its fixture
  responses through the same Zod schemas (`frontend/src/schemas/`) a
  real `fetch()` client would use, so swapping in real HTTP calls later
  only changes this file, not callers.
- `frontend/src/api/queries.ts` — TanStack Query hooks wrapping the
  mock (or real) API clients; pages depend on these, never on the
  client modules directly.
- `frontend/src/schemas/` — Zod schemas + inferred TypeScript types for
  data validated at a JSON boundary (currently the mock API layer).
  Distinct from `frontend/src/types/`, which holds hand-written
  interfaces with no runtime validation, mirroring backend Pydantic
  models by hand (no code generation step in v1).
- `frontend/src/components/status/` — reusable status/confidence
  indicators (`ProcessingStatusBadge`, `WorkflowStatusBadge`,
  `JobStatusBadge`, `ConfidenceMeter`), built on a fixed status-tone
  palette (see the `dataviz` skill's reference palette) defined as CSS
  custom properties in `index.css`. Every indicator pairs a color dot
  with a text label — never color alone.
- `frontend/src/components/ui/` — shadcn/ui primitives (Tailwind CSS v4
  + Radix UI underneath, via `components.json`), plus a couple of
  hand-written ones in the same style where the CLI doesn't have a
  matching primitive (`table.tsx`, `select.tsx`). These are treated as
  generated code matching the canonical shadcn source — compose them
  into page-level components rather than editing their internals or
  putting business logic inside them. Add new primitives with
  `npx shadcn@latest add <component>` (non-interactive: pass
  `-b radix -p base-nova -y`) where the CLI cooperates, or hand-write
  them following the existing files' style otherwise.
- `frontend/src/lib/utils.ts` — the `cn()` class-merging helper
  (`clsx` + `tailwind-merge`) shadcn components depend on.
  `frontend/src/lib/format.ts` — shared display-formatting helpers
  (dates, scores, "Unknown" placeholders for null fields).
- TanStack Table (`@tanstack/react-table`) is used for the ranking
  table in `CompaniesPage.tsx` — client-side column sorting over
  whatever page of results the API/mock layer returned; filtering is
  sent as query params instead of done client-side, matching how a
  real backend list endpoint would work.

## Testing layout

See `CLAUDE.md` for where tests live.
