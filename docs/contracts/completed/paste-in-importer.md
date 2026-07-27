# Feature

## Business Goal

The business currently sources prospective e-commerce leads (Shopify-style stores) manually from storelead.app and ad-hoc domain lists. Today there is no way to get that data into the system at all — there is no backend, no database schema, and no frontend. Before any crawling, AI interpretation, or scoring can exist, raw lead data must be able to enter the system in a structured, deduplicated form.

This feature builds the entry point of the Ingestion stage of the product pipeline (Ingestion → Crawling → Interpretation → Scoring → MongoDB → API → Frontend): a paste-in importer that turns either (a) a plain list of domains or (b) raw HTML copied from storelead.app's lead grid into stored `Company` records in MongoDB.

Because this is the first feature in the repository, this contract also stands up the base technical skeleton (backend package layout, FastAPI entrypoint, MongoDB connectivity, frontend scaffold) that every subsequent feature will build on.

## User Story

As a user sourcing leads, I want to paste either a raw list of domains or the raw HTML I copied from storelead.app's results grid into a single text box, so that the system extracts and stores each store's domain and any available contact/sales data, without me needing to manually reformat or copy fields one at a time.

## Business Value

Removes the single biggest manual bottleneck (copy-pasting individual fields per lead) between "I found leads on storelead.app" and "leads exist in our system, ready to be crawled and scored." Establishes the first working vertical slice (frontend → API → service → repository → MongoDB) that all future domains (crawling, interpretation, scoring) will be modeled on.

---

# Architecture Impact

## Affected domains

New domain: `companies` (backend/app/domains/companies/). This is the first backend domain module and establishes the convention: one directory per business domain, containing `models.py`, `repository.py`, `service.py`, `parsing.py`, `router.py`.

**Naming decision (explicit, must be recorded as an ADR — see Task list):** The entity created by this feature is stored as `Company`, not `Lead`. This repository's own planning conventions (worked examples in `.claude/agents/planner.md`) reference `CompanyRepository` and `test_company_import.py` for exactly this kind of dedupe-by-domain import, and `LeadScore` as a separate, later, downstream artifact of a scoring feature. `docs/product/lead-definition.md` is reserved for a future feature to define what promotes a `Company` into a "Lead" (i.e., a scored/qualified entity). This feature does not populate any scoring/qualification field and therefore does not create anything called "Lead."

## Affected services

New: `CompanyImportService` (backend/app/domains/companies/service.py) — owns all business rules: format detection, parsing orchestration, domain normalization, in-paste dedupe, DB-existing dedupe, and persistence orchestration.

## Affected repositories

New: `CompanyRepository` (backend/app/domains/companies/repository.py) — owns all MongoDB access for the `companies` collection: `get_existing_domains(domains)`, `insert_many(companies)`, `ensure_indexes()` (unique index on `domain`).

## Affected APIs

New: `POST /api/companies/import` — thin route, delegates entirely to `CompanyImportService`.

New (scaffolding): `GET /api/health` — minimal liveness endpoint used to verify the backend skeleton boots; not part of the import feature's business logic, but required to make the scaffolding tasks below independently verifiable.

## Affected database collections

New: `companies` collection in MongoDB (first collection in the system). Minimal schema (only fields this feature populates — no speculative scoring/status fields):

```
{
  _id: ObjectId,
  domain: string,                      # normalized, unique, indexed
  source: "paste_domain_list" | "paste_storeleads_html",
  url: string | null,                  # store's own URL, storeleads mode only
  estimated_sales_yearly_usd: float | null,   # storeleads mode only; currency assumed USD (source-fixed)
  source_created_at: date | null,      # the "created" date reported by storeleads.app; date-only, no time/timezone
  emails: string[],                    # default []
  phones: string[],                    # default []
  imported_at: datetime                # UTC, set once at insert time
}
```

Records are immutable once created in v1 — there is no update/upsert path (see Dedupe decision below and Out of Scope).

A unique index on `domain` is created at application startup (`ensure_indexes()`), providing defense-in-depth against race conditions beyond the app-level dedupe check in the service layer.

## Affected frontend pages

New: `ImportPage` (frontend/src/pages/ImportPage.tsx) — the only page in the frontend for this feature. No router library is introduced for v1; `App.tsx` renders `ImportPage` directly (single-page app). This decision must be documented (see Task list) so future features know whether to introduce a router or keep adding pages this way.

---

# Scaffolding This Contract Also Establishes

Nothing is scaffolded yet. This contract's first tasks stand up the base skeleton that the feature (and every future feature) depends on:

- Root `pyproject.toml` with backend dependencies and tool config (ruff, pytest, pyright settings).
- Minimal FastAPI entrypoint (`backend/app/main.py`) with CORS and a health route.
- MongoDB connectivity module (Motor async client + FastAPI dependency).
- `docker-compose.yml` providing a local MongoDB service only (Redis/worker services are explicitly deferred — see Out of Scope — since nothing in this feature uses the queue yet).
- `.env.example` populated with the environment variables this feature needs.
- Minimal Vite + React + TypeScript frontend scaffold (`frontend/`) with a placeholder page that builds successfully, plus Vitest + React Testing Library wired in for frontend tests.
- Initial `ARCHITECTURE.md` and `CLAUDE.md` content (currently 0-byte stubs) documenting the layering rules and directory conventions this feature establishes, so the next feature's planner/generator/evaluator have something real to read per their own required reading order.

---

# Implementation Tasks

**Scaffolding**

Task 1 — Root `pyproject.toml`: add `fastapi`, `uvicorn`, `pydantic` (v2), `pydantic-settings`, `motor`, `pymongo` (transitive dependency of motor; also reserved for future sync worker scripts — not used directly by this feature's repository), `python-dotenv`; dev dependencies `ruff`, `pyright`, `pytest`, `pytest-asyncio`, `httpx` (for FastAPI `TestClient`). Configure `[tool.ruff]` and `[tool.pytest.ini_options]` (testpaths = `backend/tests`).

Task 2 — Backend entrypoint skeleton: `backend/app/main.py` (FastAPI app, CORS middleware reading allowed origins from config, router registration, startup event calling `CompanyRepository.ensure_indexes()`), `backend/app/config.py` (pydantic-settings `Settings`: `MONGODB_URI`, `MONGODB_DB_NAME`, `CORS_ALLOWED_ORIGINS`), `backend/app/db.py` (Motor client factory + FastAPI dependency `get_database()`), `backend/app/domains/health/router.py` (`GET /api/health` → `{"status": "ok"}`).

Task 3 — `docker-compose.yml`: single `mongo` service (official `mongo` image, port 27017, named volume). Populate `.env.example` with `MONGODB_URI`, `MONGODB_DB_NAME`, `CORS_ALLOWED_ORIGINS`, `VITE_API_BASE_URL`.

Task 4 — Frontend scaffold: `frontend/` with Vite + React + TypeScript (`package.json`, `vite.config.ts`, `tsconfig.json`, `index.html`, `src/main.tsx`, `src/App.tsx` placeholder). Add Vitest + React Testing Library as dev dependencies and a minimal test config. Verify `npm run build` succeeds on the placeholder before feature UI is added.

**Backend — companies domain**

Task 5 — Domain models (`backend/app/domains/companies/models.py`): `Company` (the Mongo document shape above), `ImportRequest` (`raw_text: str`, `min_length=1`, whitespace-only rejected via validator), `SkippedInvalidEntry` (`raw_value: str`, `reason: str`), `ImportResponse` (`detected_format`, `total_rows_detected`, `created: list[Company]`, `created_count`, `skipped_duplicate_in_paste: list[str]`, `skipped_existing_in_db: list[str]`, `skipped_invalid: list[SkippedInvalidEntry]`).

Task 6 — `CompanyRepository` (`backend/app/domains/companies/repository.py`): `ensure_indexes()` (unique index on `domain`), `get_existing_domains(domains: list[str]) -> set[str]` (single batch query via `$in`), `insert_many(companies: list[Company]) -> list[Company]` (catches `DuplicateKeyError` per-document if a race occurs, treats as a skipped duplicate rather than a 500). All MongoDB access is confined to this file.

Task 7 — Parsing functions (`backend/app/domains/companies/parsing.py`), pure functions, no I/O:
- `normalize_domain(raw: str) -> str | None`: trims whitespace; strips a leading `https?://` scheme if present; strips everything from the first `/` onward (path/query/fragment); strips a trailing dot; lowercases. Does **not** strip a leading `www.` (kept as a distinguishing part of the hostname — documented decision, avoids silently merging `www.example.com` and `example.com` as one domain). Validates against hostname pattern `^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$`; returns `None` if invalid.
- `detect_format(raw_text: str) -> Literal["domain_list", "storeleads_html"]`: returns `"storeleads_html"` if `"<vaadin-grid-cell-content"` appears in the text, else `"domain_list"`. If HTML is detected, the entire input is parsed only as HTML — any stray non-grid text in the same paste is not separately parsed as domain-list lines (explicit decision, avoids ambiguous double-parsing of pathological mixed input).
- `parse_domain_list(raw_text: str) -> ParsedRows`: splits on newlines, drops blank lines, runs each line through `normalize_domain`; invalid lines become `skipped_invalid` entries with reason `"not a valid domain"`; duplicate normalized domains within the paste keep the first occurrence and record the rest as `skipped_duplicate_in_paste`.
- `parse_storeleads_html(raw_text: str) -> ParsedRows`: regex/anchor based extraction, **not** DOM-tree-position based (see rationale below). Domain matches are used as row-boundary anchors: `re.finditer(r'<div class="default">(?:<!--.*?-->)*\s*([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\s*</div>', raw_text)`. For each anchor match `i`, the row's chunk is `raw_text[match[i].start():match[i+1].start()]` (or to end-of-string for the last match). Within each chunk: `estimated_sales_yearly_usd` via `re.search(r'USD \$([0-9,]+\.[0-9]{2})/year', chunk)` (strip commas, cast float); `source_created_at` via `re.search(r'\b(\d{1,2} [A-Z][a-z]{2} \d{4})\b', chunk)`; `emails` via `re.findall(r'href="mailto:([^"]*)"', chunk)` filtered to non-empty strings; `phones` via `re.findall(r'href="tel:([^"]*)"', chunk)` filtered to non-empty strings; `url` via `re.search(r'<a class="tdu pc cpoint"[^>]*href="(https?://[^"]+)"', chunk)` (the `https?://` scheme requirement alone disambiguates it from `mailto:`/`tel:` links — no need to key off the `target="_blank"` attribute). The extracted domain itself is re-validated through `normalize_domain` for defense-in-depth. In-paste duplicate domains follow the same rule as `parse_domain_list`.

Task 8 — **Explicit scope decision on `platform_version`, must be documented (see Task 19 ADR):** v1 does **not** attempt to capture `platform_version`. Confirmed against the actual sample file (`docs/data/storeLeads.html`, lines ~2900–3022): platform-version values (`"2.4"`, `"2.3"`, etc.) are rendered as a trailing block of bare version-like strings, decoupled from any row, with no domain anchor adjacent to them — there is no reliable way to associate them back to a specific row from the raw paste alone. Silently guessing an association would violate the "no silent failure/ambiguity" requirement. The domain-anchored row-segmentation algorithm above naturally never captures this block (version strings like `2.4`/`1.9.3.2` do not match the hostname pattern, so they never become anchors, and they contain no `mailto:`/`tel:`/`href="https`-pattern content, so they cannot contaminate the last row's overextended trailing chunk either). No code changes are required to "filter out" `pv` — it is simply never selected by design. `Company` has no field for it.

Task 9 — `CompanyImportService` (`backend/app/domains/companies/service.py`): calls `detect_format`, calls the corresponding parser, calls `repository.get_existing_domains()` on the surviving normalized domains, splits into "new" vs. `skipped_existing_in_db`, builds `Company` documents (`source` = `"paste_domain_list"` or `"paste_storeleads_html"`, `imported_at` = `datetime.utcnow()`), calls `repository.insert_many()`, assembles and returns `ImportResponse`. All dedupe/business rules live here — not in the router, not in the repository.

Task 10 — Router (`backend/app/domains/companies/router.py`): `POST /api/companies/import` accepts `ImportRequest`, calls `CompanyImportService.import_companies(raw_text)`, returns `ImportResponse`. No parsing, no dedupe logic, no MongoDB calls in this file. Register router in `main.py`.

**Frontend**

Task 11 — `ImportPage` component: textarea for pasted content, submit button, loading state, error state.

Task 12 — Typed API client (`frontend/src/api/companies.ts`): `importCompanies(rawText: string): Promise<ImportResponse>` posting to `${VITE_API_BASE_URL}/api/companies/import`; TS types in `frontend/src/types/company.ts` mirroring the backend `ImportResponse` schema exactly.

Task 13 — Render import results: created count, `skipped_duplicate_in_paste`, `skipped_existing_in_db`, `skipped_invalid` (with reasons) after a successful submit; render the validation error message on a 422 response. No use of `dangerouslySetInnerHTML` anywhere — results are rendered as plain text/data only, never as raw HTML (avoids reflecting pasted-HTML content back into the DOM unsafely).

Task 14 — Wire `ImportPage` as the app's only screen in `App.tsx` (no router library for v1 — documented decision).

**Documentation**

Task 15 — Write initial `ARCHITECTURE.md`: layering rules (routes thin / services own business logic / repositories own MongoDB access), the `domains/<name>/` module convention, dependency direction (router → service → repository → MongoDB; frontend → API only, never direct DB access).

Task 16 — Write initial `CLAUDE.md`: stack summary, directory layout, where tests live (`backend/tests/`, mirroring `backend/app/` structure; top-level `tests/` is reserved for future full-stack/browser tests spanning frontend+backend and is not used by this feature), pointer to `ARCHITECTURE.md`.

Task 17 — Populate `docs/architecture/dependency-rules.md` (the layering rules above, using this feature as the reference example) and `docs/architecture/mongodb-design.md` (the `Company` schema, the unique index on `domain`, collection name `companies`).

Task 18 — Populate `docs/product/lead-definition.md` with a minimal, scoped note: an imported record is a raw, unscored `Company`; "Lead" is explicitly not yet defined and is reserved for a future scoring feature. This prevents the term from being silently overloaded before it has a real definition.

Task 19 — Record an ADR in `docs/decisions/` covering: (a) imported records are stored as `Company`, not `Lead` — rationale above; (b) `platform_version` is excluded from v1 — rationale above; (c) dedupe policy is "ignore, never update" — rationale below.

**Testing**

Task 20 — `backend/tests/conftest.py`: async Motor test client bound to a dedicated test database (e.g. `MONGODB_DB_NAME + "_test"`), FastAPI `TestClient` with the `get_database` dependency overridden to the test client, and a fixture that drops the `companies` collection before/after each test.

Task 21 — Unit tests, `backend/tests/domains/companies/test_parsing.py`: `parse_domain_list` (valid lines, blank lines skipped, invalid hostnames skipped with reason, `https://` and path-suffixed lines normalized, in-paste duplicates reported); `parse_storeleads_html` using `docs/data/storeLeads.html` as a literal fixture (copied into `backend/tests/fixtures/storeleads_sample.html`) — assert extraction of exactly the row count present in the fixture, spot-check the first two known rows' exact field values (`www.efilive.com` → sales `5100094.68`, created `2016-12-30`, `emails=[]`, `phones=["+64 9-534 1188", "+1 661-775-5620"]`, `url="https://www.efilive.com"`; `www.stihlshop.co.nz` → 4 emails, 2 phones), and assert no row's parsed output contains a platform-version-like field. `detect_format` for both input kinds.

Task 22 — Unit tests, `backend/tests/domains/companies/test_service.py`: in-paste duplicate handling, existing-in-DB duplicate handling (using a fake/mock repository), correct `source` tagging per format, correct `ImportResponse` counts.

Task 23 — Repository tests, `backend/tests/domains/companies/test_repository.py` (against the real test MongoDB): `ensure_indexes()` creates a unique index on `domain`; `get_existing_domains()` batch lookup correctness; `insert_many()` persists correctly and a duplicate-key race is caught and reported, not raised as an unhandled 500.

Task 24 — Integration/API tests, `backend/tests/test_company_import.py` (matches this repository's own worked-example naming convention) — full request/response cycle via `TestClient` against the real test MongoDB: valid domain-list paste → 200 + correct counts; valid storeleads HTML paste (fixture file) → 200 + correct counts and field values; empty/whitespace-only `raw_text` → 422; a domain re-pasted in a second request after the first succeeded → reported under `skipped_existing_in_db`, no second document created, original document unchanged.

Task 25 — Frontend test, `frontend/src/pages/ImportPage.test.tsx` (Vitest + RTL): renders textarea and submit button; submit is disabled while a request is in flight; given a mocked successful API response, the created/skipped counts render; given a mocked 422 response, the error message renders.

---

# Acceptance Criteria

**AC-01**
Given the scaffolded backend
When `uvicorn backend.app.main:app` is started and `GET /api/health` is called
Then it returns HTTP 200 with `{"status": "ok"}`
Verification: `curl -f http://localhost:8000/api/health` (manual) and `pytest backend/tests/test_health.py`

**AC-02**
Given the scaffolded frontend
When `npm run build` is run in `frontend/`
Then the build completes with exit code 0 and produces a `dist/` bundle
Verification: manual — `npm run build` inside `frontend/`

**AC-03**
Given a paste containing three unique, valid, newline-separated domains
When `POST /api/companies/import` is called
Then all three are created as `Company` documents with `source="paste_domain_list"` and `created_count == 3`
Verification: `pytest backend/tests/test_company_import.py::test_domain_list_all_new_created`

**AC-04**
Given a paste containing the same domain twice (identical or differing only by case/protocol/path)
When `POST /api/companies/import` is called
Then only one `Company` document is created and the second occurrence appears in `skipped_duplicate_in_paste`
Verification: `pytest backend/tests/test_company_import.py::test_duplicate_domain_in_paste_ignored`

**AC-05**
Given a domain that already exists in the `companies` collection
When a paste containing that same domain is imported again
Then no new document is created, the domain appears in `skipped_existing_in_db`, and the pre-existing document is unchanged
Verification: `pytest backend/tests/test_company_import.py::test_duplicate_domain_against_db_ignored`

**AC-06**
Given the raw HTML fixture `backend/tests/fixtures/storeleads_sample.html` (copy of `docs/data/storeLeads.html`)
When it is pasted into `POST /api/companies/import`
Then `detected_format == "storeleads_html"`, the correct number of rows is extracted, and the `www.efilive.com` row's fields match exactly: `url="https://www.efilive.com"`, `estimated_sales_yearly_usd=5100094.68`, `source_created_at="2016-12-30"`, `emails=[]`, `phones=["+64 9-534 1188", "+1 661-775-5620"]`
Verification: `pytest backend/tests/domains/companies/test_parsing.py::test_parse_storeleads_html_known_row`

**AC-07**
Given the same storeleads HTML fixture (which contains a trailing block of platform-version strings)
When it is parsed and imported
Then no created `Company` document, `ImportResponse`, or Pydantic model contains any platform-version field or value
Verification: `pytest backend/tests/domains/companies/test_parsing.py::test_platform_version_never_captured`

**AC-08**
Given a domain-list paste containing one syntactically invalid line (e.g. `"not a domain!!"`) alongside valid domains
When imported
Then the invalid line appears in `skipped_invalid` with a reason string, no exception is raised, and the valid domains are still created
Verification: `pytest backend/tests/domains/companies/test_parsing.py::test_invalid_domain_line_skipped_not_fatal`

**AC-09**
Given `raw_text` that is empty or whitespace-only
When `POST /api/companies/import` is called
Then the API returns HTTP 422 and no `Company` documents are created
Verification: `pytest backend/tests/test_company_import.py::test_empty_paste_rejected`

**AC-10**
Given a plain domain-list paste and, separately, a storeleads HTML paste
When each is passed to `detect_format`
Then the plain list is classified `"domain_list"` and the HTML is classified `"storeleads_html"`
Verification: `pytest backend/tests/domains/companies/test_parsing.py::test_detect_format`

**AC-11**
Given the `companies` collection has a unique index on `domain`
When two insert attempts for the same new domain race (simulated by calling `repository.insert_many` twice with the same domain before either check completes)
Then the second insert is caught as a duplicate-key conflict at the repository layer and does not raise an unhandled exception or produce two documents
Verification: `pytest backend/tests/domains/companies/test_repository.py::test_duplicate_key_race_handled`

**AC-12**
Given the completed implementation
When the code is inspected
Then `router.py` contains no MongoDB calls, `repository.py` contains no dedupe/business rules, and all request/response validation uses Pydantic models
Verification: manual evaluator code review (see Risks — `tools/check_architecture.py` is currently an empty stub and cannot yet automate this check)

---

# Required Tests

**Unit tests**
`backend/tests/domains/companies/test_parsing.py` (normalization, both parsers, format detection, fixture-based storeleads extraction, platform_version exclusion), `backend/tests/domains/companies/test_service.py` (dedupe orchestration with a fake repository).

**Integration tests**
`backend/tests/domains/companies/test_repository.py` (real test MongoDB: indexes, batch lookup, insert, duplicate-key handling), `backend/tests/test_company_import.py` (full API → service → repository → MongoDB cycle via `TestClient` against the real test database).

**API tests**
Covered within `backend/tests/test_company_import.py`: 200/422 status codes, response schema shape, count correctness.

**Browser tests**
Not required for this feature. Rationale: the frontend is a single paste form with no multi-step user flow; API-level tests already cover parsing/dedupe correctness, and a lightweight Vitest/RTL component test covers rendering behavior. Playwright is reserved for the future Crawling domain per the product pipeline, not frontend E2E testing at this stage. This is an explicit scope decision, not an omission.

**Manual verification**
Start `docker-compose up mongo`, run the backend and frontend dev servers, paste the literal contents of `docs/data/storeLeads.html` into the running UI, and confirm the displayed created/skipped counts match the automated test's expected row count.

---

# Risks

**Technical risks**
- storelead.app's HTML structure (class names, slot numbering, the specific signals relied on here) is external and can change without notice; regex extraction would silently start returning fewer/zero rows rather than erroring. Mitigated by the fixture-based regression test (Task 21) against the real sample file — a structural change upstream will break that test loudly.
- The row-segmentation-by-domain-anchor algorithm assumes the platform-version block always trails all rows rather than being interleaved between them. Verified true in the one sample provided; not guaranteed true for all future storelead.app exports. Flagged, not solved — mitigated by the same fixture regression test.
- `tools/check_architecture.py` is currently a 0-byte stub. Running it as part of the "Required Verification" steps in `.claude/agents/generator.md`/`evaluator.md` will not perform any real check until it is implemented (out of scope for this contract). The evaluator must perform manual architecture review (AC-12) until that tool exists.

**Business risks**
- This is explicitly a best-effort, human-in-the-loop tool. Garbage or partial pastes produce partial/garbage data; the system will not catch semantic errors (e.g., a wrong domain that happens to be syntactically valid). The UI showing per-row skip reasons is the accepted mitigation, not a correctness guarantee.

**Performance risks**
- No input size limit is currently specified for `raw_text`, and the whole paste is parsed and inserted synchronously within a single request. A very large paste (thousands of rows) could cause a slow request or memory spike. Recommended follow-up (not in this contract's scope): a maximum request body size guard (e.g., reject `raw_text` above a byte threshold with 413).

**Security risks**
- No authentication or authorization exists anywhere in the repository yet; `POST /api/companies/import` is open to anyone who can reach the API. Acceptable for a local/single-tenant v1, must be treated as a hard blocker before any non-local deployment.
- Pasted HTML is only ever regex-parsed server-side, never rendered/executed — no server-side script-execution risk. The frontend must never use `dangerouslySetInnerHTML` when displaying parsed results (Task 13), to avoid a stored-XSS surface if raw fragments were ever echoed back to the browser.

**Data integrity risks**
- The "ignore, never update" dedupe policy (Task 19c) means a domain first imported via a sparse plain-domain-list paste can never later be enriched by a richer storeleads HTML paste for the same domain in v1. This is an explicit, documented limitation, not an oversight — an upsert/merge feature is a reasonable near-term follow-up but is out of scope here.
- Concurrent imports of the same new domain from two clients could both pass the service-layer "not already in DB" check before either persists. Mitigated by the MongoDB unique index + repository-level duplicate-key handling (AC-11), not by application-level locking.

---

# Dependencies

**External APIs:** None. This feature is the Ingestion stage only, upstream of Crawling/Interpretation — no OpenAI, no external HTTP calls.

**MongoDB:** Required. Accessed via Motor (async driver) from `CompanyRepository` only. `pymongo` is installed as a transitive dependency of Motor and reserved for future sync worker code — not used directly by this feature.

**Playwright:** Not used by this feature.

**OpenAI:** Not used by this feature.

**Environment variables:** `MONGODB_URI` (e.g. `mongodb://localhost:27017`), `MONGODB_DB_NAME` (e.g. `lead_intelligence`), `CORS_ALLOWED_ORIGINS` (e.g. `http://localhost:5173`), `VITE_API_BASE_URL` (e.g. `http://localhost:8000`).

---

# Out of Scope

- Crawling, AI interpretation, and scoring (later pipeline stages).
- Capturing `platform_version` (explicit decision — see Task 8/19).
- Any form of authentication or authorization.
- Upsert/merge of an existing `Company` with newer/richer data from a later paste (dedupe is strictly "ignore" in v1).
- Bulk file/CSV upload; only inline paste is supported.
- Any listing/browsing/search UI for previously imported companies (view-only endpoints are a separate future feature).
- Rate limiting, request size limits (flagged as a risk, not implemented here).
- Redis queue and background workers, and any related `docker-compose.yml` services — nothing in this feature is asynchronous or queued.
- Multi-currency support for `estimated_sales_yearly_usd` (currency is assumed fixed at USD per the source).
- `docs/product/vision.md` and `docs/product/scoring-model.md` — unrelated to this feature, left untouched.
- Automated architecture-compliance tooling (`tools/check_architecture.py` implementation).
- Full E2E/Playwright browser tests for the frontend.

---

# Suggested Implementation Order

1. Task 1 — root `pyproject.toml`
2. Task 2 — backend entrypoint skeleton (`main.py`, `config.py`, `db.py`, health route)
3. Task 3 — `docker-compose.yml` (MongoDB) + `.env.example`
4. Task 20 — `backend/tests/conftest.py` (test DB fixtures) — needed before any backend test can run
5. Task 5 — `companies` domain models
6. Task 6 — `CompanyRepository`
7. Task 23 — repository tests
8. Task 7 (+ Task 8 decision) — parsing functions
9. Task 21 — parsing unit tests (including the fixture-based storeleads test)
10. Task 9 — `CompanyImportService`
11. Task 22 — service unit tests
12. Task 10 — router, wired into `main.py`
13. Task 24 — API/integration tests
14. Task 4 — frontend scaffold (Vite + React + TS + Vitest/RTL)
15. Task 11–14 — `ImportPage`, API client, results rendering, wiring into `App.tsx`
16. Task 25 — frontend component test
17. Task 15–19 — documentation and ADRs (`ARCHITECTURE.md`, `CLAUDE.md`, `docs/architecture/*`, `docs/product/lead-definition.md`, ADR)

---

# Success Criteria

This feature is complete only when:

✓ All acceptance criteria AC-01 through AC-12 pass

✓ All required tests (Tasks 20–25) pass, including the storeleads-HTML fixture regression test

✓ `router.py` remains thin, `repository.py` contains only MongoDB access, `service.py` contains all dedupe/business rules, all request/response validation is Pydantic-based (AC-12)

✓ `ARCHITECTURE.md`, `CLAUDE.md`, `docs/architecture/dependency-rules.md`, `docs/architecture/mongodb-design.md`, `docs/product/lead-definition.md`, and an ADR in `docs/decisions/` are all populated per Tasks 15–19

✓ Evaluator reports PASS
