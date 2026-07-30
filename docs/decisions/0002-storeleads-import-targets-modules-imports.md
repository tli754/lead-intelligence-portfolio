# ADR 0002: New HTML import UI wires to `modules/imports`, not the legacy paste importer

- Status: Accepted
- Date: 2026-07-28
- Feature: none yet — no feature contract exists for the StoreLeads
  import UI at the time of this ADR; this decision is recorded ahead of
  that contract because it determines which of two already-built
  backend pipelines the contract may target, and needs to survive as
  the objective reason once the contract exists.

## Context

Two independent, non-interoperating HTML-import pipelines exist in this
repository:

1. **`backend/app/domains/companies/parsing.py` +
   `domains/companies/router.py`** — parses storelead.app's Vaadin
   virtualized-grid HTML (or a plain domain list) pasted as raw text,
   exposed at `POST /api/companies/import`. It extracts `domain`, `url`,
   `estimated_sales_yearly_usd`, `source_created_at`, `emails`, and
   `phones`, but never `platform`/`country`/`city` (that grid format
   doesn't carry those columns). It writes into the `companies`
   MongoDB collection via `domains/companies/repository.py`. This is
   the only import path currently wired to the frontend
   (`frontend/src/pages/ImportPage.tsx` → `importCompanies()` in
   `frontend/src/api/companies.ts:38`).

2. **`backend/app/modules/imports/`** — parses an ordinary HTML
   `<table>` copy from StoreLeads (`domain/storeleads_html_parser.py`,
   stdlib `HTMLParser`), extracting `website`, `platform`, `country`,
   and `city`. It exposes a preview/commit pair,
   `POST /api/imports/storeleads/preview` and
   `POST /api/imports/storeleads` (`modules/imports/api/router.py`),
   and writes through `CompanyServiceImportGateway` into
   `modules/companies`' `CompanyService`, which persists to the
   `companies_pipeline` collection
   (`modules/companies/infrastructure/mongo_repository.py:21`). This
   module is fully built, tested, and registered in `main.py`
   (`imports_router`, `main.py:32,66`) — but **no frontend code calls
   it**.

These two pipelines write to two different, disjoint MongoDB
collections. Critically, `CompaniesPage` and `CompanyDetailPage` — the
actual lead-browsing UI — read from `companies_pipeline` via
`GET /api/companies` (`modules/companies/api/router.py`), **not**
`companies`. This means the only import UI that currently exists
(`ImportPage.tsx`) writes to a collection the rest of the application
never reads: companies imported today are invisible everywhere else in
the app.

We need `platform`, `country`, and `city` captured from pasted HTML.
Only pipeline 2 extracts them, and the `modules/companies` domain model
already has fields for them (`domain/models.py:19-21`, with dedicated
Mongo indexes on `identity.platform` / `identity.country`).

## Decision

Any new frontend work to import HTML with platform/country/city data
must call the `modules/imports` StoreLeads endpoints
(`POST /api/imports/storeleads/preview` and
`POST /api/imports/storeleads`), not extend or reuse
`domains/companies/parsing.py` or `POST /api/companies/import`.

The legacy `domains/companies` paste importer and its `companies`
collection are treated as superseded for the purpose of any UI that
needs to feed the pipeline the rest of the app (companies list,
company detail, discovery, crawling, extraction) actually operates on.
It is not deleted by this decision — only new import UI work is
redirected away from it.

## Rationale

- `modules/imports` is the only pipeline that extracts
  platform/country/city at all; extending the legacy Vaadin-grid parser
  to do so is not possible from that HTML format (storelead.app's grid
  export doesn't carry those columns — see the "Extra columns" test
  fixtures under `fixtures/storeleads/`, which belong to the `<table>`
  format, not the grid format).
- `modules/imports` writes into `companies_pipeline`, the collection
  every other module (`discovery`, `crawling`, `evidence`,
  `extraction`) and every other frontend page already depends on.
  Writing new companies into `companies` (the legacy collection) would
  make them permanently invisible to the rest of the product — a
  worse outcome than doing nothing.
- `modules/imports` already has a preview/commit split with per-row
  validation, duplicate, and error reporting
  (`ImportPreviewResponse`/`ImportResultResponse` in
  `modules/imports/api/schemas.py`), which is a better fit for a
  paste-and-review UI than the legacy importer's single-shot response.

## Implementation contract (binding on whatever feature contract picks this up)

Recorded here, ahead of a feature contract, so the eventual contract
author doesn't have to re-derive it from source: the exact shape of the
two endpoints this decision commits the frontend to.

### `POST /api/imports/storeleads/preview`

Request body (`StoreLeadsImportRequest`, camelCase per the module's
`CamelCaseModel`):

```json
{ "html": "<table>...</table>" }
```

`html` must be non-empty (`Field(min_length=1)`); an empty paste should
be blocked client-side before calling the endpoint, not relied on the
422 response.

Response (`ImportPreviewResponse`, all field names camelCase on the
wire — note enum *values* below are **not** camelCased, they're the
raw `StrEnum` string values):

```json
{
  "data": {
    "summary": {
      "rowsFound": 3,
      "validRows": 2,
      "invalidRows": 1,
      "existingCompanies": 1,
      "duplicateRowsInFile": 0,
      "importableRows": 1
    },
    "rows": [
      {
        "rowNumber": 1,
        "website": "https://www.summitoutfitters.com",
        "normalizedDomain": "summitoutfitters.com",
        "platform": "shopify",
        "country": "United States",
        "city": "Denver",
        "validationStatus": "valid",
        "errors": [],
        "duplicateStatus": "new",
        "outcome": null
      }
    ]
  }
}
```

### `POST /api/imports/storeleads` (commit)

Same request shape as preview (`{ "html": "..." }` — the full paste is
resubmitted, not row IDs from a prior preview call; there is no
server-side preview-session state). Response (`ImportResultResponse`):

```json
{
  "data": {
    "created": 1,
    "skippedExisting": 1,
    "skippedInvalid": 1,
    "failed": 0,
    "rows": [ /* same ImportRowResponse shape as preview, but with `outcome` set */ ]
  }
}
```

Safe to resubmit: `ImportService` re-derives its own preview internally
and creation goes through `CompanyImportGateway.create_imported_company`,
which surfaces MongoDB's unique-domain index as a typed
`CompanyAlreadyExistsError` — so re-running the same paste twice creates
nothing the second time, regardless of what an earlier preview call
said (`application/import_service.py`, class docstring).

### Enum reference (wire values, not display strings)

- `validationStatus`: `"valid"` | `"invalid"`.
- `duplicateStatus`: `"new"` | `"existing"` | `"duplicate_in_file"` |
  `"unknown"`. `"unknown"` only appears in a preview when the gateway's
  `exists_by_domain` lookup itself couldn't determine an answer; such
  rows are still counted as importable and will be attempted at commit
  time.
- `outcome` (`null` on every preview row; set on every commit-result
  row): `"created"` | `"skipped_existing"` | `"skipped_invalid"` |
  `"failed"`.
- `errors[].field`: currently only ever `"website"` (no
  platform/country/city validation exists — see below) or `null` for a
  row-level problem. `errors[].message` values currently possible:
  `"missing website"`, `"empty website value"`, `"malformed host"`,
  `"localhost is not allowed"`, `"IP addresses are not allowed"`,
  `"private/internal hostnames are not allowed"`
  (`domain/website_normalizer.py`). Treat this as a UI-facing string
  list, not a stable enum — new reasons can be added on the backend
  without a contract change.

### Field normalization the UI must not re-derive or contradict

- `platform`: normalized server-side to one of `"shopify"`,
  `"woocommerce"`, `"magento"`, `"custom"`, or `null` if the raw column
  value doesn't match one of those (case-insensitive) —
  `domain/platform_normalizer.py`. The UI should treat `null` as
  "unknown platform", not an error, and must not attempt to infer a
  platform from the domain itself (the normalizer deliberately doesn't).
- `country`/`city`: free text, whitespace-trimmed, blank -> `null`. No
  allow-list, no geocoding, no normalization to ISO country codes.
- `website`/`normalizedDomain`: `website` is the raw cell text as
  parsed; `normalizedDomain` is `null` whenever `validationStatus` is
  `"invalid"`. Display `website` (the raw value) in any row the UI
  shows, since `normalizedDomain` may be absent exactly when the user
  most needs to see what was actually pasted.

### Suggested UI flow (non-binding on layout, binding on the two-step shape)

Paste HTML → call `/preview` → render `summary` counts plus a per-row
table (badge by `validationStatus`/`duplicateStatus`, inline error
messages for invalid rows) → user reviews and confirms → call the
commit endpoint with the *same* `html` string (not a subset — there is
no partial-commit/row-selection capability in this backend contract as
built) → render final per-row `outcome`. This mirrors
`ImportPreviewService`/`ImportService`'s own two-step split
(`application/preview_service.py`, `application/import_service.py`) and
is the shape `docs/contracts/completed/wire-company-detail-to-real-api.md`
sets precedent for (typed client functions + a composing hook, wired
into `frontend/src/api/queries.ts`).

### Explicitly open questions (not decided by this ADR — for the feature contract to resolve)

- Whether the new StoreLeads-table UI **replaces** `ImportPage.tsx`
  wholesale, becomes a second tab/mode on the same page, or ships as an
  entirely separate route. The existing page's plain-domain-list paste
  and one-off "quick add domain" form have no equivalent in the
  `modules/imports` contract (no `platform`/`country`/`city`, no
  preview step) — deciding whether to keep, drop, or otherwise fold in
  that flow is a product/UX call, not an architectural one, and is
  deliberately left to the contract.
- Whether partial commit (only re-submitting rows the user didn't
  uncheck) is worth adding to the backend. As built, commit always
  processes every row the HTML parses to; there's no mechanism to
  submit a filtered subset without server-side changes out of this
  ADR's scope.

## Correction (2026-07-28)

The Context and Rationale sections above assert that "storelead.app's
grid export doesn't carry those columns" (platform/country/city) and
cite `fixtures/storeleads/` as evidence. That fixture set belongs to
the `<table>` format (pipeline 2), not the Vaadin grid format (pipeline
1) — the actual grid-export evidence for this claim was
`backend/tests/fixtures/storeleads_sample.html`, which has only 7
`<vaadin-grid-column>` columns (`domain`, `estimated_sales_yearly`,
`created`, `emails`, `phones`, `url`, `pv`).

A real StoreLeads Vaadin-grid export supplied by the user
(`.claude/data/storeLeads_prestaShop.html`, 43 rows) has **13**
columns: the same 7 above, plus `employees`, `status`, `platform`,
`categories`, `country`, and `city`. So the grid export *does* carry
platform/country/city — the checked-in fixture was simply narrower
than a real export, not representative of the format's actual ceiling.

This doesn't change the Decision above (new import UI still targets
`modules/imports`, since that's the only pipeline writing to
`companies_pipeline`, the collection the rest of the app reads). But it
does invalidate the specific reason given for why the legacy Vaadin
parser (`domains/companies/parsing.py`) can't be extended to extract
those fields — it's not that the source data lacks them, it's that
nothing has been built yet to read Vaadin-grid markup into
`companies_pipeline` with those fields populated.

As of this correction, the only thing extracting platform/country/city
from a real Vaadin-grid export is a one-off throwaway script (not
committed to the repo) written to backfill 43 companies from the file
above via `CompanyService.create_company`, run directly against Mongo
outside of any HTTP endpoint. No application code changes as a result
of this correction — if recurring Vaadin-grid imports (as opposed to
one-off backfills) are needed, that's new feature work: either
teaching `modules/imports` a second parser for this markup, or
extending `domains/companies/parsing.py` to extract these fields and
routing its output through `CompanyService` instead of the legacy
repository. Deciding between those is out of scope for this
correction and would need its own ADR or feature contract.

## Consequences

- Building the StoreLeads import UI requires a new frontend API client
  (there is currently no `frontend/src/api/imports.ts`) and either
  reworking `ImportPage.tsx` or adding a new page — this is real,
  not-yet-scoped frontend work, to be captured in its own feature
  contract before implementation.
- `POST /api/companies/import`, `domains/companies/parsing.py`, and the
  `companies` collection become dead weight from the frontend's
  perspective once the new UI ships. This ADR does not decide whether
  to delete them — that's a separate cleanup decision, out of scope
  here, and should not be done silently as a side effect of unrelated
  work.
- Any company documents already sitting in the `companies` collection
  (created via the legacy `/import` page before this decision) are not
  migrated into `companies_pipeline` by this decision. If that data
  needs to be preserved, a migration is a separate, explicit follow-up.
- This ADR does not cover the dangling "ADR 0002" reference in
  `backend/app/domains/companies/parsing.py:8` (a comment citing an ADR
  number that was never written, for the unrelated `platform_version`
  exclusion decision). That comment now points to the wrong document;
  fixing it is tracked as a separate follow-up, not folded into this
  ADR.

## Addendum (2026-07-29): `domains/companies` removed

The cleanup decision this ADR explicitly deferred ("this ADR does not
decide whether to delete them... should not be done silently as a side
effect of unrelated work") has now been made explicitly, at the
repository owner's direct request, independent of any feature contract:

- Confirmed zero frontend references to `POST /api/companies/import`
  remained (Task 014's `modules/imports` UI had already fully replaced
  it), and zero other backend code depended on `app.domains.companies`
  beyond its own router registration in `main.py`.
- The `companies` collection held zero documents at removal time — no
  migration was needed or performed. (Its contents, if any had existed,
  would not have been migrated into `companies_pipeline`; see the
  Consequences note above, which still applies to any such data lost
  before this cleanup.)
- Removed: `backend/app/domains/companies/` (router, repository,
  service, parsing, models), its registration in `backend/app/main.py`,
  `backend/tests/domains/companies/`, `backend/tests/test_company_import.py`,
  and the now-unused `backend/tests/fixtures/storeleads_sample.html`.
  Dropped the empty `companies` MongoDB collection.
- `modules/companies`' `companies_pipeline` is now the only `Company`
  model/collection in the codebase — the "unreconciled fork" ARCHITECTURE.md
  described between the flat and hexagonal conventions is resolved.
  `domains/health` is now the flat convention's only surviving example.
- This also resolves the dangling "ADR 0002" comment noted above by
  deleting the file it was in, rather than fixing the reference.
