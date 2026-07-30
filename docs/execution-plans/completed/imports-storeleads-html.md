# Execution Plan: StoreLeads HTML Import Module (Task 004)

Status: Complete
Contract: none written — built directly from an ad-hoc task brief ("Task
004"), not through the planner→contract workflow used by
`paste-in-importer`.

## Scope

Isolated to `backend/app/modules/imports/**`,
`backend/tests/unit/imports/**`, `backend/tests/integration/imports/**`,
`fixtures/storeleads/**`, per the task's explicit path restrictions.
`backend/app/main.py` and `backend/app/modules/companies/**` were
off-limits — confirmed untouched. No CSV/Excel import, crawling,
discovery, platform detection, evidence, AI analysis, scoring, frontend,
background jobs, auth, or deploy work included.

## What was built

A new, isolated `imports` module (hexagonal: domain → application →
infrastructure → api) that parses an HTML `<table>` copied from
StoreLeads, previews which rows are valid/importable without writing
anything, and imports valid/new rows by creating companies **through the
companies module's own `CompanyService`** — never MongoDB directly.

**Domain** (`domain/`): pure Pydantic models (`ImportRow`,
`ImportRowError`, `ImportPreview`, `ImportResult`, `ImportBatchSummary`)
and enums (`ImportSource`, `ValidationStatus`, `DuplicateStatus`,
`ImportRowOutcome`); `storeleads_html_parser.py` (stdlib
`html.parser.HTMLParser`, no new dependency) matches table columns to
`website`/`platform`/`country`/`city` by header text, case-insensitively
and order-independently, tolerating extra columns and nested markup
(`<a>`, `<span>`) inside cells; `website_normalizer.py` (stdlib
`urllib.parse`/`ipaddress`) rejects localhost, IP literals, malformed
hosts, and private/internal hostnames, IDNA-encodes non-ASCII labels,
and strips only a leading `www.` label so other subdomains survive;
`platform_normalizer.py` does exact-match normalization only — no
inference from the website; `row_builder.py` combines these into a
validated `ImportRow`, turning bad input into a structured
`ImportRowError` rather than raising.

**Application** (`application/`): `ImportPreviewService` (parses,
validates, detects in-file duplicates, optionally checks existing
domains via the gateway — never writes) and `ImportService` (runs a
preview internally, then creates each valid/new row through the gateway,
catching a duplicate as "skipped" and any other exception as a
per-row "failed" without aborting the batch).

**The Company integration boundary** (`domain/gateway.py` +
`infrastructure/company_service_gateway.py`): `CompanyImportGateway` is
a narrow `ABC` port (`exists_by_domain`, `create_imported_company`).
Since the companies module (Task 003) was actually present in this same
worktree — not a separate one, as the task brief hedged — the **real**
adapter was built: `CompanyServiceImportGateway` wraps an injected
`CompanyService`, obtained via the companies module's own
`get_company_service` DI function (read-only reuse of a public wiring
function, not a modification of that module). No import of
`MongoCompanyRepository` or Motor anywhere in `modules/imports/`.

**API** (`api/`): `POST /api/imports/storeleads/preview` and
`POST /api/imports/storeleads`, camelCase JSON, matching the task's
exact example response shapes. **Built but not registered** in
`backend/app/main.py`, per the task's own instruction.

## The `exists_by_domain` gap

`CompanyService` has no public, non-mutating "does this domain exist"
lookup today — only `create_company`, which mutates and internally
raises `DuplicateCompanyError` on a collision. The real adapter's
`exists_by_domain` therefore always returns `None` ("unknown"), which
`ImportPreviewService` maps to `DuplicateStatus.UNKNOWN`. This degrades
only the **preview** endpoint's `existingCompanies` count (stays `0`
against the real adapter). It does not compromise **import** safety:
`create_imported_company` catches the real, race-free
`DuplicateCompanyError` (backed by MongoDB's unique index on
`normalized_domain`) regardless of what preview predicted — confirmed by
an end-to-end test proving a re-run of the same file creates nothing the
second time. Tests use a `FakeCompanyImportGateway` with real
`True`/`False` answers to exercise the `existingCompanies` code path
properly even though the real adapter can't yet.

## Testing

69 new tests, all passing:
- **Unit** (`backend/tests/unit/imports/`, 53 tests, pure domain logic):
  parser (normal table, unrelated/reordered/extra columns, nested
  anchors, blank cells, row numbers, empty-row skipping), website
  normalizer (all documented input forms, www-stripping, subdomain
  preservation, localhost/IP/malformed/private rejection, IDNA), platform
  normalizer, row builder (structured errors, not exceptions).
- **Integration** (`backend/tests/integration/imports/`, 16 tests, using
  `FakeCompanyImportGateway` + a locally-built `FastAPI()` app with only
  the imports router — no shared `app.main.app`, no real MongoDB, so
  these tests genuinely cannot touch the companies collection even by
  accident): preview performs no writes, correct summary counts incl.
  `existingCompanies`, import creates/skips-existing/skips-invalid,
  retry creates nothing the second time, one forced failure doesn't
  abort the batch, camelCase serialization end-to-end.

Additionally verified manually (not part of the automated suite) against
the **real** adapter and a real test-MongoDB database: preview → import
→ retry → inspected the actual persisted document, confirming the whole
chain (HTML → parse → normalize → `CompanyService.create_company` →
MongoDB) works without the imports module ever importing Mongo types
itself.

`ruff` and `pyright` clean on all changed/new paths. Full backend suite
(excluding the pre-existing stale Task 002 tests, unrelated to this
work): 168 passed.

## Fixtures (`fixtures/storeleads/`)

Six small, hand-authored, sanitized HTML table snippets:
`standard_table.html`, `reordered_columns.html`, `extra_columns.html`,
`invalid_websites.html`, `duplicate_websites.html`, `empty_table.html`.

## Required follow-up outside this task's allowed paths (reported, not done)

- **Register the router.** `imports_router` is fully built and tested
  but not wired into `backend/app/main.py` — required before it's
  reachable outside tests.
- **Add a read-only domain-lookup method to `CompanyService`** (in
  `backend/app/modules/companies/`) so the real adapter's
  `exists_by_domain` can return an actual answer instead of always
  `None`, making preview's `existingCompanies` count accurate.

## Known gaps / integration work still required

- No frontend wiring exists for either endpoint.
- In-file duplicate rows are folded into the import result's
  `skippedExisting` bucket — the task's 4-field result shape has no
  separate "duplicate in file" bucket.
- This parses ordinary HTML `<table>` markup, not the Vaadin
  virtualized-grid export format `backend/app/domains/companies/parsing.py`
  already handles for the (different) paste-in-importer feature — the
  two parsers are deliberately not unified, since they target different
  source markup shapes.
