# Feature Contract: Task 016 — Vaadin-grid StoreLeads import support

Task brief: `docs/execution-plans/tasks/016-Vaadin-Grid-Import-Support.md`

Binding architectural precedent: `docs/decisions/0002-storeleads-import-targets-modules-imports.md`
(Accepted, including its "Correction (2026-07-28)" section, which is what
authorizes this task). Precedent for contract shape/testing/doc placement:
`docs/execution-plans/completed/imports-storeleads-html.md` and
`docs/contracts/completed/014-storeleads-import-ui.md`.

# Feature

## Business Goal

Users copy-paste two different StoreLeads export markup shapes into the
same paste box on `/import` (`ImportPage.tsx`, wired to `modules/imports`
since Task 014). Only the `<table>` shape currently parses; a Vaadin
virtualized-grid paste (StoreLeads' other export format) silently returns
zero rows today — `parse_storeleads_table` just returns `[]` for markup it
doesn't recognize, with no distinguishing error. Confirmed against two real
user-supplied exports (`.claude/data/storeLeads_prestaShop.html`, 43 rows,
13 columns; `.claude/data/storeLeads_openCart.html`, same markup family)
that currently parse to zero rows.

## User Story

As a user who copies a StoreLeads Vaadin-grid export (rather than a
`<table>` export) and pastes it into the existing Import page, I want the
same preview/commit flow to work and correctly populate domain/platform/
country/city, so I don't have to know or care which of StoreLeads' two
export markups I happened to copy.

## Business Value

Makes the already-shipped `modules/imports` pipeline handle both real-world
StoreLeads export shapes, closing a confirmed gap without requiring any
frontend change or a second import workflow.

---

# Architecture Impact

**Affected domains:** `modules/imports` only. No changes to `modules/companies`,
`domains/companies`, `modules/discovery`, `modules/crawling`, `modules/evidence`,
or `modules/extraction`.

**Affected services:** `application/preview_service.py`
(`ImportPreviewService.preview_storeleads_html`) — the single call site that
turns raw HTML into `RawStoreLeadsRow`s. `application/import_service.py`
needs **zero** changes: it already delegates entirely to
`ImportPreviewService` and never parses HTML itself (confirmed by reading
`import_service.py` — its only parsing-adjacent call is
`self._preview_service.preview_storeleads_html(html)`).

**Affected repositories:** none. `CompanyImportGateway` /
`CompanyServiceImportGateway` are already format-agnostic — they only ever
see `normalized_domain`/`platform`/`country`/`city` regardless of source
markup (confirmed by reading `domain/gateway.py` and
`infrastructure/company_service_gateway.py`).

**Affected APIs:** none. `POST /api/imports/storeleads/preview` and
`POST /api/imports/storeleads` keep their exact existing request/response
shape (`StoreLeadsImportRequest`, `ImportPreviewResponse`,
`ImportResultResponse` in `api/schemas.py`) — format detection is entirely
server-side and invisible on the wire. `ImportSource` (an internal-only
domain enum) is never serialized onto either response DTO today
(`ImportPreviewDataResponse`/`ImportResultDataResponse` only expose
`summary`/`rows`), so adding an enum value there is not an API change.

**Affected database collections:** none new — commit still writes into
`companies_pipeline` via the unchanged gateway.

**Affected frontend pages:** **none.** `ImportPage.tsx` /
`frontend/src/api/imports.ts` (Task 014) already send `{ html }` and render
whatever `platform`/`country`/`city`/`validationStatus`/`duplicateStatus`
come back. Since the wire contract is unchanged, this pipeline starts
handling Vaadin-grid pastes with zero frontend code changes. If a reviewer
proposes touching `frontend/`, that is out of scope for this contract.

## Explicit dependency-direction confirmation

This feature adds no new cross-module or cross-layer dependency. Both new
files (`domain/vaadin_grid_parser.py`, `domain/format_detector.py`) are pure
Pydantic/stdlib-only additions inside `modules/imports/domain/`, exactly
like the existing `storeleads_html_parser.py` — zero imports of FastAPI,
Motor, or `app.modules.companies`. The one wiring change
(`application/preview_service.py`) only calls two `domain/` functions it
now imports one more of; it does not touch `domain/gateway.py` or acquire
any new dependency on another module. `router → service → repository →
MongoDB` layering (`ARCHITECTURE.md`) and the hexagonal
`domain → application → infrastructure → api` convention are both
unaffected — this stays entirely inside `modules/imports`, same as the
`<table>` parser.

---

# Implementation Tasks

**T1 — New parser** (`backend/app/modules/imports/domain/vaadin_grid_parser.py`, new)

Function signature: `parse_storeleads_vaadin_grid(html: str) -> list[RawStoreLeadsRow]`,
importing and reusing the existing `RawStoreLeadsRow` NamedTuple from
`storeleads_html_parser.py` (do not redefine it) — `row_number`, `website`,
`platform`, `country`, `city`. `row_builder.build_import_row` needs zero
changes to consume either parser's output.

Implementation technique (a throwaway prototype proving this technique
exists at `/tmp/claude-1000/-srv-lead-intelligence/462aa487-c620-47a0-b3a9-26110440c071/scratchpad/parse_vaadin_grid.py`
— reference it for the approach only; do not copy it in as-is, rewrite with
this module's own style, docstrings, and error handling):

- A stdlib `HTMLParser` subclass tracks, in document order:
  (a) every `<vaadin-grid-column name="...">` declaration — the **full**
  column list, including columns with no destination field
  (`estimated_sales_yearly`, `created`, `emails`, `phones`, `url`, `pv`,
  `employees`, `status`, `categories`), which must still occupy a position
  in the tracked list so cell-to-column positional alignment stays correct;
  (b) every `<vaadin-grid-cell-content>` element's flattened text
  (concatenating all nested text nodes, tolerant of nesting exactly like
  the existing table parser's `_flush_cell`); (c) which cell-content
  indices correspond to a `<vaadin-checkbox aria-label="Select Row">`
  (a data-row boundary) as opposed to `aria-label="Select All"` (the header
  row's own boundary marker, which must never be tracked as a row start —
  this is what naturally excludes the header row from being emitted as a
  data row, with no separate header-skipping logic needed).
- Row grouping: for each tracked "Select Row" index `i`, the row's data
  cells are `cells[i+1 : i+1+len(columns)]`, mapped positionally against
  the tracked column-name list.
- Column-name → field mapping: an own alias map local to this file
  (`{"domain": "website", "platform": "platform", "country": "country",
  "city": "city"}`, case-insensitive match on the `name` attribute value),
  deliberately **not** shared/imported from `storeleads_html_parser.py`'s
  `_HEADER_ALIASES` (that map matches header *text*, not a `name`
  attribute — same shape of concept, different input; keep these as two
  small independent constants rather than introducing a shared
  cross-parser abstraction for a 4-entry map).
- `row_number` is 1-based over emitted data rows only, matching
  `parse_storeleads_table`'s existing contract.

Malformed/empty-grid handling (must be covered by tests, never raises):

- Zero `<vaadin-grid-column>` elements, or none of the tracked columns
  match a known field name → return `[]` (do not emit garbage all-`None`
  rows).
- Zero `<vaadin-grid-cell-content>` elements, or zero "Select Row"
  boundaries found → return `[]`.
- A trailing/truncated row (fewer cells remaining after its "Select Row"
  boundary than the full column count — plausible since StoreLeads' grid
  is virtualized and a copy can end mid-row) → still emitted, with any
  field whose column index falls outside the available cells treated as
  `None` (mirrors `parse_storeleads_table`'s own
  `index >= len(cells): continue` tolerance), rather than the whole row
  being dropped.
- Malformed `domain` cell content is **not** validated here — same
  division of responsibility as the table parser: the parser only
  extracts raw text; `row_builder.build_import_row` is what turns a bad
  `website` value into a structured `ImportRowError`.

**T2 — Format detection** (`backend/app/modules/imports/domain/format_detector.py`, new)

- `DetectedImportFormat = Literal["table", "vaadin_grid"]`
- `detect_storeleads_format(html: str) -> DetectedImportFormat` — marker-based,
  mirroring `app/domains/companies/parsing.py`'s `detect_format`: presence
  of the substring `"<vaadin-grid-cell-content"` (the same marker constant
  that file already uses) classifies as `"vaadin_grid"`; anything else
  (including empty/garbage input, or plain `<table>` markup) classifies as
  `"table"` — preserving `parse_storeleads_table`'s existing behavior as
  the fallback for anything not positively identified as the grid format
  (no regression for today's `<table>`/malformed/empty inputs).
- Pure, no FastAPI/MongoDB import — unit-testable in isolation.

**T3 — Wiring** (`backend/app/modules/imports/application/preview_service.py`, edit)

- Replace the single line `raw_rows = parse_storeleads_table(html)` with a
  small private dispatch helper (e.g. `_parse_raw_rows(html)`) that calls
  `detect_storeleads_format(html)` and dispatches to
  `parse_storeleads_vaadin_grid` or `parse_storeleads_table` accordingly.
- This is the **only** call site that needs to change.
- Recommended but non-binding on wire shape: add
  `ImportSource.STORELEADS_VAADIN_GRID = "storeleads_vaadin_grid"` to
  `domain/enums.py` and set `ImportPreview.source`/`ImportResult.source`
  from the detected format instead of hardcoding
  `ImportSource.STORELEADS_HTML` — purely internal provenance, `source` is
  never serialized onto the wire (confirmed in `api/schemas.py`). Do **not**
  add `source` to the wire DTOs as part of this task.

**T4 — Normalization reuse**

- The new parser's output must flow through the exact same
  `row_builder.build_import_row` → `website_normalizer.normalize_website` /
  `platform_normalizer.normalize_platform` pipeline the `<table>` path
  already uses. Country/city stay free-text/whitespace-trimmed/blank→`null`.
- **Amendment (Task 018, post-completion of this contract's original
  scope):** platform originally stayed exact-match-only against
  `{shopify, woocommerce, magento, custom}`, which meant a `platform`
  cell value of `"PrestaShop"` or `"OpenCart"` normalized to `null` —
  silently dropping the two platforms this task's own motivating real
  fixtures (`.claude/data/storeLeads_prestaShop.html`,
  `.claude/data/storeLeads_openCart.html`) actually contain. This was a
  premise defect, not an intentional design choice: the fixtures this
  contract was built around were never actually checked against the
  normalizer's known-platform set. `normalize_platform` now also
  recognizes `prestashop`/`opencart` (case-insensitive, same pattern as
  the existing four). Other unrecognized values (e.g. `BigCommerce`)
  are unaffected and still normalize to `null` — this amendment adds
  only the two platforms with confirmed real-fixture evidence, not a
  speculative full platform list.
- **Known, accepted, out-of-scope-to-fix inconsistency:** the real
  Vaadin-grid export's `country` column (`.claude/data/storeLeads_prestaShop.html`)
  contains ISO-ish codes (e.g. `"NZ"`), whereas the `<table>` path's
  fixtures use full country names (e.g. `"United States"`). Per the task
  brief's explicit instruction not to invent a second normalization scheme,
  pass this through as free text unchanged — do not add code to reconcile
  it.

**T5 — Fixtures** (`fixtures/storeleads/`, new files; hand-authored/sanitized,
never commit `.claude/data/*.html` verbatim)

- `vaadin_grid_standard.html` — 3-4 data rows, all 13 real columns in real
  order (`domain, estimated_sales_yearly, created, emails, phones, url, pv,
  employees, status, platform, categories, country, city`), full
  `<vaadin-custom-grid>`/header-row/`Select All`+`Select Row` checkbox
  markup, so the fixture genuinely exercises column-position tracking and
  row-boundary detection.
- `vaadin_grid_reordered_columns.html` — same data, `<vaadin-grid-column>`
  declarations in a different order, proving column-position mapping (not
  name-guessing) drives extraction.
- `vaadin_grid_missing_optional_fields.html` — blank `platform`/`country`/
  `city` cells (`<div class="default"></div>`, matching the real empty-cell
  markup) plus one unrecognized platform value (e.g. `"PrestaShop"`).
- `vaadin_grid_invalid_and_duplicate_domains.html` — one malformed/empty
  `domain` cell, two rows normalizing to the same domain.
- `vaadin_grid_truncated_row.html` — a final "Select Row" boundary with
  fewer trailing cells than the full column count.
- `vaadin_grid_empty.html` — column declarations + header row present, zero
  "Select Row" boundaries (no data rows) → expect `[]`.
- `vaadin_grid_malformed.html` — `<vaadin-grid-cell-content>` present, zero
  `<vaadin-grid-column>` declarations (corrupted paste) → expect `[]`.

**T6 — Unit tests** (`backend/tests/unit/imports/`, new files): see
Required Tests.

**T7 — Integration tests** (extend `backend/tests/integration/imports/test_preview.py`,
`test_import.py`, `test_api_schema_serialization.py`; no new conftest
needed — reuse the existing `FakeCompanyImportGateway` harness): see
Required Tests.

---

# Acceptance Criteria

**AC-01**
Given a Vaadin-grid HTML paste with 13 real columns (`vaadin_grid_standard.html`)
When `POST /api/imports/storeleads/preview` is called with that HTML
Then `data.rows` contains one row per data row with correct `website`/
`normalizedDomain`/`platform`/`country`/`city` extracted from the `domain`/
`platform`/`country`/`city` columns (not any of the other 9 columns), and
`data.summary.rowsFound` matches the fixture's row count.
Verification: `pytest backend/tests/integration/imports/test_preview.py -k vaadin`

**AC-02**
Given the same data with `<vaadin-grid-column>` declarations in a different
order (`vaadin_grid_reordered_columns.html`)
When parsed
Then extraction is unaffected by declaration order.
Verification: `pytest backend/tests/unit/imports/test_vaadin_grid_parser.py -k reordered`

**AC-03**
Given a Vaadin-grid row whose `platform` cell contains a genuinely
unrecognized value (e.g. `"BigCommerce"`)
When previewed
Then `platform` is `null` (never an error, never inferred from the domain).
Verification: `pytest backend/tests/unit/imports/test_platform_normalizer.py -k unknown_or_blank`

**AC-03a** *(added by Task 018)*
Given a Vaadin-grid row whose `platform` cell contains `"PrestaShop"` or
`"OpenCart"` (case-insensitive)
When previewed
Then `platform` is `"prestashop"`/`"opencart"` respectively, not `null`.
Verification: `pytest backend/tests/unit/imports/test_platform_normalizer.py -k normalizes_known_platforms`

**AC-04**
Given a Vaadin-grid row with a malformed/empty `domain` cell
When previewed
Then that row's `validationStatus` is `"invalid"` with a `website`-field
error, exactly like an invalid `<table>` row.
Verification: `pytest backend/tests/integration/imports/test_preview.py -k vaadin_invalid`

**AC-05**
Given a Vaadin-grid paste with two rows normalizing to the same domain
When previewed
Then the second occurrence has `duplicateStatus: "duplicate_in_file"`.
Verification: `pytest backend/tests/integration/imports/test_preview.py -k vaadin_duplicate`

**AC-06**
Given a Vaadin-grid paste with zero `<vaadin-grid-column>` declarations, or
zero `<vaadin-checkbox aria-label="Select Row">` boundaries
When previewed
Then `parse_storeleads_vaadin_grid` returns `[]` without raising, and
`data.summary.rowsFound` is `0` — not a 500, not spurious all-null rows.
Verification: `pytest backend/tests/unit/imports/test_vaadin_grid_parser.py -k "malformed or empty"`

**AC-07**
Given a Vaadin-grid paste whose final row is truncated
When parsed
Then the row is still emitted, with any field beyond the truncation point
`None` rather than the whole row dropped.
Verification: `pytest backend/tests/unit/imports/test_vaadin_grid_parser.py -k truncated`

**AC-08**
Given a plain `<table>` StoreLeads paste (any existing table fixture)
When previewed or imported after this feature ships
Then behavior is byte-for-byte unchanged from before this feature.
Verification: full existing `backend/tests/unit/imports/test_storeleads_html_parser.py`
and `backend/tests/integration/imports/test_preview.py`/`test_import.py`
suites still pass unmodified aside from additive new cases.

**AC-09**
Given a Vaadin-grid paste of new, non-duplicate, valid rows
When `POST /api/imports/storeleads` (commit) is called
Then companies are created via the unchanged `CompanyImportGateway.create_imported_company`
with the extracted `platform`/`country`/`city`, and resubmitting the same
paste a second time creates nothing (`skippedExisting` for every row).
Verification: `pytest backend/tests/integration/imports/test_import.py -k vaadin`

**AC-10**
Given any Vaadin-grid or `<table>` paste
When either endpoint responds
Then the JSON shape (`ImportPreviewResponse`/`ImportResultResponse`, field
names, enum wire-values) is byte-for-byte identical to ADR 0002's
documented shape — no new top-level field, no `source` on the wire.
Verification: `pytest backend/tests/integration/imports/test_api_schema_serialization.py`
(extended with a Vaadin-grid case).

---

# Required Tests

**Unit** (`backend/tests/unit/imports/`, no MongoDB):
- `test_vaadin_grid_parser.py`: normal 13-column grid extraction and row
  numbering; reordered column declarations; unrecognized platform value →
  parser passes raw text through unchanged (normalization happens in
  `row_builder`, not here); blank platform/country/city cells → `None`;
  malformed domain cell → row still emitted with raw `website` text
  (validation is `row_builder`'s job); duplicate domains across rows
  (parser doesn't dedupe — that's `preview_service`'s job; test only
  proves both raw rows are emitted); truncated final row; zero-column-
  declarations malformed input → `[]`; zero-row-boundary empty input →
  `[]`; extra/unmapped columns (`estimated_sales_yearly`, `emails`, etc.)
  never leak into `website`/`platform`/`country`/`city`.
- `test_format_detector.py`: `<vaadin-grid-cell-content` marker present →
  `"vaadin_grid"`; plain `<table>` markup → `"table"`; empty string →
  `"table"`; input containing both an actual `<table>` and the Vaadin
  marker substring → documented as `"vaadin_grid"` (marker-priority, same
  ambiguous-mixed-input policy `domains/companies/parsing.py`'s
  `detect_format` already uses).

**Integration** (`backend/tests/integration/imports/`, via
`FakeCompanyImportGateway`, no MongoDB):
- `test_preview.py` additions: standard Vaadin-grid summary counts,
  invalid-row detection, in-file duplicate detection, existing-company
  detection via the gateway (parallel to the four existing table-format
  test classes).
- `test_import.py` additions: commit creates companies with correct
  platform/country/city from a Vaadin-grid paste; retry-safety (resubmit
  creates nothing the second time); one forced-failure row doesn't abort
  the batch (`make_gateway(fail_domains=...)`).
- `test_api_schema_serialization.py` addition: one Vaadin-grid-sourced
  preview response asserted against the exact same camelCase shape as a
  table-sourced one.

**API tests:** covered by the integration tier above (this module has no
separate tier for that, per its own precedent).

**Browser tests:** none — no frontend change in scope. Optional manual
smoke test: paste `vaadin_grid_standard.html`'s contents into the running
`/import` page and confirm rows render and commit succeeds; not a required
automated test.

**Manual verification:** run preview/commit against a real test-MongoDB
database using the real `CompanyServiceImportGateway` (not just the fake),
pasting a sanitized Vaadin-grid fixture, confirming the created company is
subsequently visible via `GET /api/companies` — same manual check the
original `imports-storeleads-html` execution plan performed for the table
format.

---

# Risks

**Technical risks:**
- Row-boundary detection depends on the exact
  `<vaadin-checkbox aria-label="Select Row">` markup StoreLeads currently
  emits; if StoreLeads changes this markup, the parser silently returns
  `[]` rather than erroring. Mitigation: this is the same silent-empty-
  result failure mode the `<table>` parser already has for unrecognized
  markup — not a new risk introduced here.
- Column-position tracking is positional, not per-cell name-anchored — a
  future export with a different column *count* than tracked could
  misalign extraction. Mitigation: unit tests cover reordered-but-same-
  count columns; a differing column count isn't fabricated/tested since no
  evidence of that variant exists yet.

**Business risks:**
- This fixes the silent-zero-rows case but doesn't add a "we couldn't
  parse this at all" user-facing error for a genuinely unrecognized third
  markup shape — pre-existing gap in both endpoints, not introduced or
  fixed here.

**Performance risks:** none beyond what already exists (same in-memory
`HTMLParser` approach, same lack of pagination for very large pastes).

**Security risks:** none new — same stdlib `HTMLParser` (no HTML
execution), same `website_normalizer` hostname validation applied
identically regardless of source markup.

**Data integrity risks:**
- Country/city free-text passthrough means the same location can render
  as `"NZ"` (Vaadin-grid source) vs. `"New Zealand"` (`<table>` source)
  depending only on which export was pasted — accepted per T4, not fixed
  here.

---

# Dependencies

External APIs: none. MongoDB: none directly (confirmed no new Motor import
anywhere in `modules/imports/`). Playwright: none. OpenAI: none.
Environment variables: none new.

---

# Out of Scope

- Any change to `modules/companies`, `CompanyImportGateway`, or
  `CompanyServiceImportGateway`.
- Any change to `frontend/`.
- Extracting `estimated_sales_yearly`/`created`/`emails`/`phones`/`url`/
  `pv`/`employees`/`status`/`categories` beyond using them for column-
  position alignment — `companies_pipeline` has no destination field for
  them.
- Registering the imports router in `main.py` — already done (Task 009,
  confirmed present at `backend/app/main.py:32,66`).
- Any change to `domains/companies/parsing.py` or the legacy `companies`
  collection/pipeline (ADR 0002 already redirected new import work away
  from it).
- Normalizing country codes (`"NZ"`) to full country names or vice versa.
- A distinct user-facing error for HTML matching neither format (pre-
  existing gap).
- Partial commit / row-selection UI capability (unrelated, already an
  accepted gap per ADR 0002 / Task 014).

---

# Suggested Implementation Order

1. T1 (parser) + T6's parser/detector unit tests — independently testable.
2. T2 (format detector) + its unit tests.
3. T5 (fixtures) — needed before T6/T7 run; author alongside T1/T2.
4. T3 (wiring into `preview_service.py`) — depends on T1 and T2 existing.
5. T7 (integration tests) — depends on T3 being wired.
6. T4 is verification-only — confirmed via T6/T7 assertions (e.g. AC-03),
   not a separate code change.

---

# Success Criteria

This feature is complete only when:

✓ AC-01 through AC-10 pass
✓ All Required Tests pass, alongside the full existing
  `backend/tests/unit/imports/` and `backend/tests/integration/imports/`
  suites with no regression (AC-08)
✓ `ruff` and `pyright` clean on all changed/new paths
✓ No architecture violations: zero new imports of Motor/FastAPI in
  `domain/`, zero new coupling to `modules/companies` beyond the existing
  gateway, zero frontend changes
✓ `docs/execution-plans/completed/016-vaadin-grid-import-support.md`
  written once the evaluator reports PASS, and this contract moved from
  `docs/contracts/active/` to `docs/contracts/completed/`
✓ Evaluator reports PASS
