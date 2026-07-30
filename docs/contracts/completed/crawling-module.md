# Feature

## Business Goal

The product pipeline is Ingestion → Crawling → Interpretation → Scoring → MongoDB → API → Frontend. Ingestion (paste-in importer) and Discovery (Task 005 — turning a company's domain into a prioritized set of candidate URLs) already exist. Nothing yet turns those candidate URLs into actual page content. Without a Crawling stage, Discovery's output is a dead end: there is no HTML, no extracted text, no page metadata for any later Extraction/Analysis/Scoring stage to work from. This feature builds that stage — it fetches a bounded, prioritized, policy-respecting set of pages per company, safely and repeatably, and persists exactly what a future Extraction module will need (cleaned HTML, extracted text, metadata, technology signals) without itself interpreting any of that content into business facts.

## User Story

As the pipeline (and, later, an operator triggering it), I want a company's previously-discovered URLs to be fetched into stored, cleaned, deduplicated page records — respecting robots.txt, avoiding wasted refetches of unchanged pages, and safely refusing to fetch anything that could be an SSRF vector or clearly isn't a normal web page — so that downstream Extraction has real page content to work from without ever having to fetch anything itself.

## Business Value

Turns Discovery's URL list into the raw material every later stage depends on. Establishes the second HTTP-fetching module in the repository (after Discovery) and the first one that persists fetched content, so the storage/change-detection/safety patterns built here are reusable precedent for future modules that fetch external content (e.g. a future re-crawl/freshness job).

---

# Architecture Impact

## Affected domains

New: `backend/app/modules/crawling/`, following the exact hexagonal (`domain → application → infrastructure → api`) layering already established by `modules/companies`, `modules/imports`, and `modules/discovery` (see `ARCHITECTURE.md`'s "Module convention (hexagonal variant)"). No existing domain or module's files are modified — this is a pure addition, confirmed against the task's own allowed-paths restriction (`backend/app/modules/crawling/**`, `backend/tests/unit/crawling/**`, `backend/tests/integration/crawling/**`, `fixtures/crawling/**` only).

## Affected services

New: `WebsiteCrawlService` (`backend/app/modules/crawling/application/website_crawl_service.py`) — orchestrates one crawl run end-to-end (target selection → robots check → fetch → conditional/change-detection → validate/clean/extract → hash → browser-fallback detection → store → persist → summarize → advance company status), exactly mirroring `WebsiteDiscoveryService`'s shape and its "depend only on domain ports, never a concrete Mongo/HTTP/FastAPI type" discipline.

No existing service is modified. `CompanyService` and `WebsiteDiscoveryService` are consumed only through this module's own gateway ports (see "Cross-module dependencies" below) — never called or subclassed directly outside their own DI-provided instances.

## Affected repositories

New: `CrawlRepository` (ABC port, `domain/repository.py`) and its real implementation `MongoCrawlRepository` (`infrastructure/mongo_crawl_repository.py`), following the exact pattern of `MongoCompanyRepository`/`MongoDiscoveryRepository` (Motor-only, confined to this one file, `ensure_indexes()` idempotent). This is justified: Motor/Pydantic-repository is already an approved, three-times-repeated pattern in this repository, so per the task brief's own instruction ("Implement a MongoDB repository only if the repository already contains an approved MongoDB infrastructure pattern"), building it is in scope.

No existing repository (`CompanyRepository`, `DiscoveryRepository`, or the flat `app/domains/companies/repository.py`) is modified or imported concretely.

## Affected APIs

New, built but **not registered** in `backend/app/main.py` (per the task's own explicit instruction, mirroring `modules/imports` and `modules/discovery`'s already-unregistered routers):

- `POST /api/companies/{company_id}/crawl-runs`
- `GET /api/companies/{company_id}/crawl-runs/latest`
- `GET /api/crawl-runs/{crawl_run_id}`
- `GET /api/crawl-runs/{crawl_run_id}/targets`
- `GET /api/crawl-runs/{crawl_run_id}/pages`
- `GET /api/pages/{page_id}`
- `POST /api/crawl-runs/{crawl_run_id}/cancel`
- `POST /api/crawl-runs/{crawl_run_id}/retry-failed`

Registering these in `main.py` is a required, out-of-allowed-paths **integration step** (see Dependencies / Suggested Implementation Order), not part of this contract's deliverable.

## Affected database collections

New: `crawl_runs`, `crawl_targets`, `pages` — all owned exclusively by `MongoCrawlRepository`. No existing collection (`companies`, `companies_pipeline`, `discovery_runs`, `discoveries`) is written to directly by this module; `companies_pipeline` and `discovery_runs`/`discoveries` are reached only through this module's own gateway ports (`CompanyCrawlGateway`, `DiscoveryCrawlGateway`), never a concrete Mongo repository imported from another module.

Note: `companies_pipeline`'s document shape (`docs/architecture/mongodb-design.md`) already reserves a `processing.latest_crawl_run_id` field and the `Company` Pydantic model (`backend/app/modules/companies/domain/models.py`) already declares it — confirmed by direct inspection. What's missing is the *write path* to it (see "Required follow-up" below); this contract does not add that write path itself, since `modules/companies/**` is off-limits to this task.

## Affected frontend pages

None. No frontend work is in scope for this task (explicit constraint in the task brief).

---

# Cross-module dependency decisions (resolved now, not left for the generator to discover)

Three real gaps exist between what this task needs and what `modules/companies` and `modules/discovery` currently expose. All three are resolved below, concretely, so the generator has no open design questions when it starts.

### 1. `CompanyCrawlGateway.update_latest_crawl_run` — `CompanyService` has no such method yet

`CompanyRepository`/`CompanyService` (in `modules/companies`, off-limits to this task) has `update_latest_discovery_run` (added as a Task-005 follow-up) but no equivalent `update_latest_crawl_run`, even though the `CompanyProcessing.latest_crawl_run_id` field already exists in the domain model and is already persisted by `model_dump()` (it just has no dedicated setter method or MongoDB update path).

**Decision:** `infrastructure/company_service_gateway.py`'s `CompanyServiceCrawlGateway.update_latest_crawl_run` is implemented as a **documented, logged no-op** (log at `INFO`, include `company_id`/`crawl_run_id` in the log line, cite this exact gap in the docstring) — exactly the precedent `CompanyServiceImportGateway.exists_by_domain` already sets for an equivalent "the target module can't do this yet" situation. `update_processing_status`, by contrast, **is** fully real today (`CompanyService.change_processing_status` already exists) and must be wired for real, not stubbed.

**Required follow-up (report, do not build):** add `CompanyRepository.update_latest_crawl_run_id` (interface) + `MongoCompanyRepository.update_latest_crawl_run_id` (implementation) + `CompanyService.update_latest_crawl_run`, mirroring `update_latest_discovery_run` exactly, then swap the gateway's no-op for a real call.

### 2. `DiscoveryCrawlGateway` — no reusable read-accessor exists on `modules/discovery`

`modules/discovery/api/router.py` defines `get_discovery_repository(database=Depends(get_database)) -> DiscoveryRepository` as a plain, non-underscore-prefixed module-level function — but it was never designed as a cross-module accessor the way `modules/companies/api/router.py`'s `get_company_service` was (which `modules/imports` and `modules/discovery` already both import and reuse). The established gateway-adapter precedent (`ARCHITECTURE.md`'s "Cross-module dependencies" section) says an adapter should wrap "the *other* module's own public application service" — but `WebsiteDiscoveryService` has no read/query methods (`get_run`, `list_discovered_urls`) to wrap; only `DiscoveryRepository` (the persistence interface, one layer lower) has them.

**Decision:** `infrastructure/discovery_repository_gateway.py`'s `DiscoveryRepositoryCrawlGateway` wraps the **`DiscoveryRepository` interface** (never `MongoDiscoveryRepository` concretely), obtained by importing the *existing, already-public* `get_discovery_repository` function from `app.modules.discovery.api.router` — the same mechanical pattern already used for `get_company_service` (import a plain DI function from another module's `api/router.py`, wire it into this module's own FastAPI dependency chain). This requires **zero changes to `modules/discovery/**`**, so it is fully buildable within this task's allowed paths, and yields a real (non-fake) adapter — not merely a fake deferred to a future task. This is a deliberate, one-layer-lower exception to the "wrap a service" ideal, justified because discovery has no query-capable service to wrap and adding one would touch an off-limits path; it is documented in the adapter's own module docstring, not left implicit.

`DiscoveryCrawlGateway` therefore has exactly two methods — `get_discovery_run(discovery_run_id)` and `list_discovered_urls(discovery_run_id, priorities, page_types, include_excluded)` — **not** `get_robots_policy` (see #3). This is a deliberate, documented deviation from the task brief's literal section-13 method list, in the same spirit as `DiscoveryRepository.get_latest_run_for_company` being a documented addition beyond Task 005's own literal method list.

**Optional, non-blocking future cleanup (not required for this task's sign-off):** promote this into a proper `DiscoveryQueryService` in `modules/discovery/application/` for architectural symmetry with `CompanyService`. Recorded as a nicety, not a blocker — the adapter above is already correct and real.

### 3. Robots policy is **not** discovery data at all — it needs new logic, owned entirely by this module

`modules/discovery/domain/robots_parser.py` only ever splits `robots.txt` into raw rule groups and extracts `Sitemap:` lines — its own docstring says explicitly "this module does no matching/enforcement itself." Discovery never fetches robots.txt for the crawler's purposes and never stores a per-URL policy decision. So `RobotsPolicyGateway` (task brief section 3) cannot be backed by anything discovery already computed — it needs genuinely new matching logic (best-matching `User-agent` group, longest-prefix `Allow`/`Disallow` precedence, `Crawl-delay` extraction), which does not exist anywhere in this repository yet.

**Decision:** `RobotsPolicyGateway` is a port owned entirely by `modules/crawling` (`domain/gateway.py`, alongside `CompanyCrawlGateway`/`DiscoveryCrawlGateway` — see Implementation Tasks). Its real adapter (`infrastructure/http_robots_policy_gateway.py`) fetches `robots.txt` itself (via this module's own `PageFetcher`), and **reuses** `app.modules.discovery.domain.robots_parser.parse_robots_txt` and its `RobotsRuleGroup`/`RobotsPolicyResult` return types as a direct, pure-domain-type import (zero FastAPI/Mongo dependencies in that file — confirmed by inspection) rather than reimplementing line-splitting — satisfying the brief's own "do not reimplement discovery parsing logic inside the crawler" instruction literally, while building the genuinely-new matching/evaluation logic locally in `domain/robots_policy.py`. This mirrors the already-established precedent of importing a pure domain type across a module boundary directly (e.g. `CompanyDiscoveryGateway` importing `ProcessingStatus` from `modules/companies/domain/enums.py`).

---

# Implementation Tasks

## Domain foundations

**T1 — Enums** (`domain/enums.py`): `CrawlStatus`, `PageFetchStatus`, `FetchMode`, `ContentStorageMode`, `BrowserFallbackReason` exactly as enumerated in the task brief (StrEnum, matching the existing modules' convention). Plus `BrowserPolicy` (`never`, `detect_only`, `fetch_when_required`, `always_for_selected_page_types`) — a documented addition needed by section 10 but not listed among the brief's section-1 model names (it's a config/policy value, not a record model).

**T2 — Domain models** (`domain/models.py`): `RedirectHop` (local duplicate of discovery's, not imported — matches discovery's own precedent of duplicating small pure helpers/models rather than cross-importing), `HttpMetadata`, `PageMetadata` (plus two documented additions: `technology_signals: dict` — required by section 9's "collect technology signals... store as raw page-level signals in metadata" but with no field slot in the brief's literal list; and `cleaning_rules_version: str` / `text_extraction_rules_version: str` — required by section 7's "cleaning must be versioned", extended for consistency to text extraction too), `ContentHashes`, `ContentReference` (opaque: `reference_id: str`, plus internally-carried `company_id`/`crawl_run_id`/`page_id`/`kind: Literal["raw","cleaned","text"]` — never serialized as a filesystem path; see T18), `ContentStorageInfo` (documented reconciliation of the brief's single `content_storage: ContentStorageMode` field into a 3-artifact-aware structure: `raw_content_mode`, `cleaned_html_mode` + `cleaned_html_reference: ContentReference | None`, `extracted_text_mode` + `extracted_text_reference: ContentReference | None` — raw's own reference stays at `CrawledPage.raw_content_reference` exactly as the brief's literal field list already has it), `CrawlWarning` (documented fields: `code: str`, `message: str`, `url: str | None`, `page_id: str | None`, `created_at: datetime`), `CrawlSummary`, `CrawlTarget`, `CrawlRun`, `CrawledPage` — all fields exactly as the brief's section 1 lists, plus two documented additions needed for section 16 (idempotency) and section 20 (staleness rejection): `CrawlRun.idempotency_key: str` and `document_version: int = 1` on `CrawlRun`, `CrawlTarget`, and `CrawledPage` (mirrors `companies_pipeline`'s existing `document_version` convention). `CrawlTarget.page_type`/`CrawlTarget.priority` reuse `app.modules.discovery.domain.enums.PageType`/`DiscoveryPriority` directly (pure-type cross-module reuse, same precedent as `ProcessingStatus`) rather than redefining a second, redundant enum. UTC-coercing `field_validator`s on every datetime field, matching `_as_utc` in both existing modules (duplicated locally, not imported).

**T3 — Config** (`domain/config.py`): `CrawlConfig`, a plain injectable Pydantic model (never reads `os.environ` — that stays off-limits/out of scope, matching `DiscoveryConfig`'s own documented pattern) holding every tunable from brief section 21 (page/product/collection/unknown caps, concurrency, delays, timeouts, retry/redirect/size limits, extracted-text cap, inline-threshold bytes, browser policy default, user agent, response-header allowlist, retryable-status-code set, max Retry-After, challenge-page-handling policy default).

**T4 — Domain exceptions** (`domain/exceptions.py`): `CrawlDomainError` base; `CompanyNotFoundForCrawlError`, `DiscoveryRunNotFoundForCrawlError`, `CrawlRunNotFoundError`, `CrawlTargetNotFoundError`, `PageNotFoundError`, `DuplicateActiveCrawlRunError`; `CrawlFetchError` base + `TimeoutFetchError`, `OversizedResponseError`, `DisallowedHostError` (covers scheme/credentials/localhost/private-IP rejection with a `reason` string, mirroring `DiscoveryFetchError`'s exact style), `TooManyRedirectsError`, `InvalidContentTypeError`, `NonHtmlResponseError`; `StorageIntegrityError`, `UnsafeStoragePathError`.

## Target selection (pure domain logic)

**T5 — `domain/target_selector.py`**: `select_crawl_targets(candidates, *, config, manual_include_urls, manual_exclude_urls, include_page_types, exclude_page_types) -> list[SelectedTarget]`, pure and deterministic. `candidates` is a plain, minimal local shape (`page_type`, `normalized_url`, `priority`, `depth`, `discovery_sources`) — not `DiscoveredUrl` itself, so this function stays independently unit-testable without constructing a full discovery model. Implements: dedup by `normalized_url` (first occurrence wins, by the deterministic sort order below); priority-1 always included; priority-2 included by default; priority-3 included up to configured caps; `excluded` never included unless present in `manual_include_urls`; shallower `depth` preferred as a tiebreak; nav/footer/robots/sitemap-sourced URLs preferred as a tiebreak over body-link-only URLs; a total-page cap (`config.max_pages_per_company`), a separate product-page cap (`config.max_product_pages`), a separate collection/category cap (`config.max_collection_pages`), and a separate "unknown page type" cap (`config.max_unknown_pages`); `include_page_types`/`exclude_page_types` allow/deny lists (deny wins over allow when both list the same type); manual include/exclude always take precedence over every cap/list rule. Final deterministic sort key: the exact 23-item page-type order from brief section 2, mapping onto `PageType` (documented: the brief's "sampled product" bucket = `PageType.PRODUCT`; `PageType.ACCOUNT`/`CART`/`CHECKOUT`/`SEARCH` — present in discovery's enum but absent from the brief's 23-item list — sort after `unknown`, last, and are excluded by default unless explicitly allow-listed; this ordering-gap resolution is documented in the function's own docstring, not left implicit), then by `priority`, then by `normalized_url` for full determinism.

## Robots policy

**T6 — `domain/robots_policy.py`**: `evaluate_robots_policy(rule_groups: list[RobotsRuleGroup], *, path: str, user_agent: str, max_crawl_delay_s: float) -> RobotsPolicyEvaluation` — pure, independently testable (per the brief's own requirement), zero I/O. Selects the best-matching `User-agent` group (exact match preferred over `*`); applies longest-matching-path precedence between `Allow`/`Disallow` (standard robots.txt semantics); extracts `Crawl-delay` if present, capped at `max_crawl_delay_s`; returns `allowed`/`disallowed`/`unknown` (no matching group at all → `unknown`), `matched_rule` (the literal rule string that decided the outcome, or `None` for `unknown`), and `source` (`"robots_txt"` or `"unknown_default"`).

**T7 — `domain/gateway.py`'s `RobotsPolicyGateway`** (ABC): `get_policy(company_id, url, user_agent) -> RobotsPolicyEvaluation`.

**T8 — `infrastructure/http_robots_policy_gateway.py`**: `HttpRobotsPolicyGateway(RobotsPolicyGateway)` — fetches `robots.txt` via an injected `PageFetcher`, parses it with `app.modules.discovery.domain.robots_parser.parse_robots_txt` (direct pure-function reuse, see resolution #3 above), evaluates with T6, caches the parsed rule groups per host for the lifetime of one crawl run (avoid refetching `robots.txt` once per target). A missing/unreachable `robots.txt` (404, timeout, connection error) resolves to `unknown` with a warning appended to the run — never raises, never blocks the run.

## HTTP fetcher, conditional requests, retries, rate limiting

**T9 — `domain/page_fetcher.py`**: `PageFetchRequest` (url, previous_etag, previous_last_modified, expected_content_type, attempt), `PageFetchResult` (status_code, `http_metadata: HttpMetadata`, body bytes-or-`None` [`None` on a `304`], final_url, `outcome` — a small enum/literal distinguishing `fetched`/`not_modified`/`redirect_exhausted`, etc.), `PageFetcher` (ABC: `fetch_page`), `RenderedPageResult` (html, final_url, duration_ms, succeeded, error), `BrowserPageFetcher` (ABC: `fetch_rendered_page`).

**T10 — `domain/retry_policy.py`**: pure `is_transient_failure(status_code, exception) -> bool` (matches brief's exact list: connection reset, timeout, 408/425/429/500/502/503/504) and `compute_backoff_delay(attempt, *, base_delay_s, max_delay_s, jitter_source) -> float` (bounded exponential backoff; `jitter_source: Callable[[], float]` defaults to `random.random` but is injectable so tests are deterministic).

**T11 — `domain/rate_limiter.py`**: pure `RequestPacer` — given the last-request monotonic timestamp, the configured default/min delay, and an optional robots `crawl_delay` (capped at `config.max_honored_crawl_delay_s`), computes the next-allowed monotonic time. Uses an injectable clock (`Callable[[], float]`, defaults to `time.monotonic`) for deterministic tests. The actual `await asyncio.sleep(...)` (in small, cancellation-checked increments) lives in `application/website_crawl_service.py`, not here — this file only computes delays, it performs no I/O/concurrency itself, keeping it pure per the architecture's layering rule.

**T12 — `infrastructure/httpx_page_fetcher.py`**: `HttpxPageFetcher(PageFetcher)`, built directly on the already-established `HttpxDiscoveryClient` SSRF pattern (fresh `httpx.AsyncClient` per call with `follow_redirects=False`, manual redirect loop revalidating every hop, `client.cookies.clear()` after every hop, streamed+size-capped body reads, literal-IP-or-`getaddrinfo`-based address validation rejecting private/loopback/link-local/multicast/reserved/unspecified addresses, `localhost`/`*.localhost` rejected by name before DNS). Extended with: GET-only (enforced, never configurable); `Authorization`/cookie headers never set; **credentials-in-URL rejected** (`urlsplit(url).username`/`.password` present → `DisallowedHostError`); conditional headers (`If-None-Match`/`If-Modified-Since`) sent whenever `PageFetchRequest.previous_etag`/`previous_last_modified` is set, and a `304` is mapped straight to `PageFetchResult.outcome == "not_modified"` with `body=None`; `Accept-Encoding: gzip` only, deliberately **never** `br` — see Risks for why Brotli is out of scope; retryable failures (T10) retried with bounded backoff+jitter up to `config.max_attempts`, honoring a `Retry-After` header (capped at `config.max_retry_after_s`) on `429`/`503`; non-transient failures (e.g. `404`, `403`) are never retried; every response's headers are filtered through `config.response_headers_allowlist` before being stored in `HttpMetadata.response_headers_allowlist` (lowercased keys); response bodies are never logged, only host/status/byte-count metadata (matching `HttpxDiscoveryClient`'s existing discipline); non-HTML content types are rejected for normal page targets unless `expected_content_type` explicitly allows `text/plain`; magic-byte/binary-signature sniffing and blocked/challenge-page classification are delegated to `domain/html_validator.py` (T14) — this file stays a thin, safety-focused HTTP adapter, not a content-interpretation one. Same documented DNS-rebinding/TOCTOU residual-risk note as `HttpxDiscoveryClient`'s own module docstring (copy-adapted, not silently omitted).

## HTML validation, cleaning, extraction, metadata, hashing

**T13 — `domain/html_validator.py`**: `validate_and_decode(raw_bytes, content_type_header, config) -> DecodedHtmlResult` (encoding detection + safe decode with `errors="replace"` fallback, decoding warnings retained not discarded, decoded-size cap, truncation detection/flagging); raises typed errors for an empty response, a binary-signature match (checks magic bytes for PNG/JPEG/GIF/PDF/ZIP/common-executable signatures against the raw bytes) and rejects other obvious non-page content types (image/pdf/zip/executable/media) before ever attempting to decode as text; `classify_blocked_or_challenge(html) -> BlockedPageClassification | None` — deterministic detectors (each with its own rule id) for a Cloudflare challenge, a CAPTCHA page, an access-denied page, a generic bot challenge, a maintenance page, and a password-protected storefront. `CrawlConfig.challenge_page_policy` (default `browser_required` — chosen deliberately since these pages usually genuinely need rendering or a human, not a hard failure) decides whether a classified page becomes `failed`, `rejected`, or `browser_required`.

**T14 — `domain/html_cleaner.py`**: `clean_html(raw_html) -> CleanedHtmlResult`, stdlib-only (`html.parser.HTMLParser`, matching the existing discovery module's own choice — no new `lxml`/`bs4` dependency, since `pyproject.toml` is off-limits to this task). Removes/normalizes script contents, style contents, noscript boilerplate, non-useful SVG contents, tracking pixels, HTML comments, inline event-handler attributes, `nonce`/`integrity` attribute values, safely-strippable hydration-payload script blocks, duplicated whitespace, and known analytics script blocks (by src host or known snippet markers) — while preserving semantic structure, headings, paragraphs, lists, tables, forms/labels/buttons, links (`href` retained), image `alt` text, and structured-data (`<script type="application/ld+json">`) content separately (not discarded, kept available for a future extraction feature, never interpreted here). `CLEANING_RULES_VERSION = "v1"` module constant, surfaced on `PageMetadata.cleaning_rules_version`. Never executes/evaluates JavaScript.

**T15 — `domain/text_extractor.py`**: `extract_text(cleaned_html, *, max_length) -> ExtractedTextResult` — deterministic, order-preserving (headings, paragraphs, list items, table-cell text, meaningful `alt` text), script/style text excluded, whitespace normalized, near-duplicate boilerplate (repeated nav/footer blocks) reduced rather than repeated verbatim, capped at `config.max_extracted_text_length` (default 250,000) with truncation recorded on the result (never silently dropped). Never summarizes or paraphrases — this is extraction, not interpretation.

**T16 — `domain/metadata_extractor.py`**: `extract_page_metadata(cleaned_html, *, raw_html_size, cleaned_html_size, extracted_text_length) -> PageMetadata` — title, meta description, canonical URL, `html lang`, robots meta, OG site name/title, generator, link/script/stylesheet counts, plus the technology-signal collection required by section 9 (script source hosts, generator values, known framework/commerce-platform/analytics/support-widget markers) stored only in `PageMetadata.technology_signals` — never written to any company-facing field, satisfying the explicit constraint "do not update the company technology profile in this task."

**T17 — `domain/hashing.py`**: `compute_content_hashes(raw_bytes, cleaned_html, extracted_text) -> ContentHashes` (raw/cleaned/text SHA-256, plus `structural_hash` — a normalized-then-hashed structural fingerprint reducing sensitivity to whitespace, dynamic timestamps, random element IDs, tracking attributes, and script ordering, without normalizing away meaningful text changes); `is_materially_unchanged(previous, current) -> bool` — **decision, made explicit so the generator doesn't have to guess**: content is "materially identical" (→ `unchanged`) when `raw_content_sha256` matches exactly, **or** `structural_hash` matches even if `raw_content_sha256` differs (covers pure noise like a changed timestamp/nonce); any other case is a real change.

## Content storage

**T18 — `domain/gateway.py`'s (or a dedicated `domain/content_storage.py`) `ContentStorage`** (ABC): `store_raw_content`, `store_cleaned_content`, `load_content`, `delete_content` — exactly the brief's method list, operating on `ContentReference` (T2), never a raw path string, in either direction.

**T19 — `infrastructure/local_filesystem_content_storage.py`**: `LocalFilesystemContentStorage(ContentStorage)`. Path layout exactly as the brief's suggested `data/crawl-content/{company_id}/{crawl_run_id}/{page_id}/{raw.html|cleaned.html|text.txt}`; base directory configurable via `CrawlConfig` (default `./data/crawl-content`, not committed to the repo — see Risks re: `.gitignore`). Safe path construction: every path segment (`company_id`, `crawl_run_id`, `page_id`) is validated against a strict allowlist pattern (`^[A-Za-z0-9_-]+$`) and rejected outright if it contains a path separator, `..`, or a null byte — defense-in-depth even though these IDs are always server-generated UUIDs, never user input, matching the brief's explicit "no user-controlled path traversal" requirement and its own required test ("path traversal rejected"). Atomic writes (write to a same-directory temp file, `os.replace()` into place) — never a partial file visible under the final name. UTF-8 throughout. After writing, re-reads and verifies the SHA-256 against the hash the caller computed (T17), raising `StorageIntegrityError` on mismatch rather than silently trusting the write succeeded correctly. Returns an opaque `ContentReference` — `load_content`/`delete_content` re-derive and re-validate the path from the reference's fields on every call (never trust a cached path). Never returns or logs a raw filesystem path to any caller outside this file.

## Persistence

**T20 — `domain/repository.py`'s `CrawlRepository`** (ABC): the brief's exact method list (`create_run`, `update_run`, `save_target`, `update_target`, `save_page`, `get_run`, `list_runs_by_company`, `get_page`, `list_pages_by_run`, `get_latest_page_by_normalized_url`, `find_target_by_url`, `mark_run_cancelled`) **plus one documented addition**, `find_active_run(company_id, idempotency_key) -> CrawlRun | None` — required to serve section 16's "duplicate active run requests return the existing run or a typed conflict," which nothing in the brief's literal method list can otherwise answer (same style of justified addition as `DiscoveryRepository.get_latest_run_for_company`). Also needs paginated variants (`CrawlTargetPage`/`CrawledPagePage` `NamedTuple`s, matching `DiscoveredUrlPage`'s shape) for the `GET .../targets` and `GET .../pages` list endpoints' `page`/`pageSize` query params.

**T21 — `infrastructure/mongo_crawl_repository.py`**: `MongoCrawlRepository(CrawlRepository)`, three collections (`crawl_runs`, `crawl_targets`, `pages`), `ensure_indexes()` creating exactly the brief's listed indexes **plus one documented addition**: a unique compound index on `pages` over `(crawl_run_id, normalized_url)` — needed to make `save_page` an **upsert** keyed on that pair, which is how section 16's "retrying a failed page does not duplicate page records" is concretely satisfied (mirrors the brief's own explicit requirement that `crawl_targets` have exactly one row per `(crawl_run_id, normalized_url)`, extended here to `pages` for the same reason). `update_run`/`update_target` use an optimistic-concurrency filter on `document_version` (match-and-increment; a stale caller's write is rejected — `find_one_and_update` returns no match — rather than silently overwriting a newer state), satisfying section 16's "stale worker updates must be rejected using `document_version` or equivalent." Large raw HTML is never stored here — only `ContentReference`s and inline cleaned-HTML/text under the configured size threshold, exactly as `content_storage`/`raw_content_reference` already imply.

## Cross-module integration ports and adapters

**T22 — `domain/gateway.py`**: `CompanyCrawlGateway` (ABC: `update_latest_crawl_run`, `update_processing_status` — the latter typed against `app.modules.companies.domain.enums.ProcessingStatus`, reused directly as a pure value type, same precedent as discovery's gateway); `DiscoveryCrawlGateway` (ABC: `get_discovery_run`, `list_discovered_urls` — see resolution #2, `get_robots_policy` deliberately excluded); `RobotsPolicyGateway` (T7, listed here for completeness — all three ports live in the same file, matching how discovery keeps its one gateway in one file).

**T23 — `infrastructure/company_service_gateway.py`**: `CompanyServiceCrawlGateway(CompanyCrawlGateway)` — wraps `CompanyService` via `app.modules.companies.api.router.get_company_service` (imported DI function, never `MongoCompanyRepository` directly). `update_processing_status` calls `company_service.change_processing_status` for real. `update_latest_crawl_run` is the documented no-op from resolution #1.

**T24 — `infrastructure/discovery_repository_gateway.py`**: `DiscoveryRepositoryCrawlGateway(DiscoveryCrawlGateway)` — wraps `DiscoveryRepository` via `app.modules.discovery.api.router.get_discovery_repository` (imported DI function, never `MongoDiscoveryRepository` directly), per resolution #2. `list_discovered_urls` pages through the wrapped repository's own paginated method internally (documented: a large internal page size, or a loop until exhausted) to return one flat, filtered list to the crawl service, since target selection needs the full candidate set at once.

**T25 — `infrastructure/http_robots_policy_gateway.py`**: per T8.

## Browser fallback

**T26 — `domain/browser_fallback.py`**: `detect_browser_fallback(cleaned_html, extracted_text, challenge_classification, *, manual_override, config) -> BrowserFallbackDecision` (`browser_required: bool`, `reason: BrowserFallbackReason | None`, `confidence: int`, `rule_ids: list[str]`). Deterministic rule set, each with a stable rule id (e.g. `browser:empty-shell`, `browser:react-shell`, `browser:vue-shell`, `browser:nextjs-shell`, `browser:script-heavy`, `browser:explicit-js-required`, `browser:challenge-page`, `browser:manual`); when multiple rules match, the highest-confidence match wins, ties broken by a fixed rule-priority order (documented in the function's own docstring) — never non-deterministic.

**T27 — `WebsiteCrawlService`'s browser-policy handling**: `never` — browser fallback is never consulted, pages needing it stay `browser_required`/skipped; `detect_only` (**default**, per section 10) — detection runs and is recorded, but `fetch_rendered_page` is **never called**, even if a `BrowserPageFetcher` happens to be supplied; `fetch_when_required` — calls the supplied `BrowserPageFetcher` only for pages `detect_browser_fallback` flagged, and only if one was supplied (otherwise behaves like `detect_only` for those pages, never raising); `always_for_selected_page_types` — additionally forces a browser fetch for a configured list of page types regardless of detection. Confirmed by repo-wide grep: **no Playwright or browser-automation dependency exists anywhere in this repository** — `BrowserPageFetcher` therefore ships with no real adapter in this task; a fake is used in tests, and a real adapter (e.g. Playwright) is a reported, out-of-scope integration step, exactly as the brief allows explicitly. A browser-fetch failure must never discard the already-successful HTTP result for that page (failure isolation, section 14).

## Application service

**T28 — `application/website_crawl_service.py`**: `WebsiteCrawlService`, constructed from every port above plus `CrawlConfig`. `start_crawl_run(company_id, discovery_run_id, options) -> CrawlRun` orchestrates exactly the section-14 responsibility list: validates the company (via `CompanyCrawlGateway`) and the discovery run (via `DiscoveryCrawlGateway`) exist; computes the idempotency key (company_id + discovery_run_id + a hash of `options` — see "Idempotency" below) and returns the already-active run (or raises `DuplicateActiveCrawlRunError`, decision below) if one is `queued`/`running` for that same key; creates the run (`queued` → `running`); advances company `processing.status` to `CRAWLING` (best-effort — catches `InvalidStatusTransitionError` and logs+swallows, exact same pattern as `WebsiteDiscoveryService._advance_processing_status`); selects targets (T5) and persists them (`CrawlRepository.save_target`, one document per `(crawl_run_id, normalized_url)`); for each target in deterministic order, sequentially (concurrency-per-company = 1 by default, per section 14 — no distributed/parallel fetching in this task): checks cancellation; evaluates robots policy (`RobotsPolicyGateway`) — `disallowed` → `blocked_by_robots` status, never fetched; `unknown` → proceeds with a `CrawlWarning`; paces the request (T11's computed delay, actually awaited here via a short, cancellation-checked sleep loop); fetches via `PageFetcher`, applying retry policy (T10) inside the fetcher, not re-implemented here; on a `304`/hash-unchanged outcome, marks `unchanged`, points `unchanged_from_page_id` at the previous page, and still records the latest fetch's `HttpMetadata`; on a fresh `200`, validates/decodes (T13), cleans (T14), extracts text (T15) and metadata (T16), computes hashes (T17) and compares to the previous page's hashes for that `normalized_url` (`CrawlRepository.get_latest_page_by_normalized_url`); runs browser-fallback detection (T26) and applies the configured policy (T27); stores content (T19) — one page's storage failure is caught and recorded as a page-level warning, never aborts the run or other pages; persists the page (upsert per T21) and updates the target's status; accumulates the run's `CrawlSummary`. Homepage-target failure is configurable (`config.homepage_failure_marks_run` — documented default: `partial`, not `failed`, since other pages may still have useful content) rather than unconditionally failing the whole run. On completion, sets `CrawlStatus` (`completed`/`completed_with_warnings`/`partial`/`failed`), advances company status to `CRAWLED` or `FAILED` (best-effort, same swallow pattern), and calls `update_latest_crawl_run` (currently a no-op per resolution #1, called anyway so the wiring is correct once the follow-up lands). `cancel_run(crawl_run_id)` stops scheduling new targets (checked via `mark_run_cancelled` + a cancellation flag consulted between targets) but preserves already-completed pages — never deletes them. `retry_failed(crawl_run_id)` re-runs only targets currently in a failure-shaped status (`failed`, `blocked_by_robots` if configured to retry those, `rejected`) within the *same* run, never creating a second `CrawlRun`, and relies on the upsert-by-`(crawl_run_id, normalized_url)` persistence (T21) to avoid duplicate page records. A repository failure (not a page/site failure) is allowed to fail the whole run, per section 14's explicit "repository failure may fail the run because state cannot be trusted."

**Idempotency (section 16), made concrete:** `idempotency_key = sha256(company_id | discovery_run_id | sha256(json(config_snapshot)) | sha256(json(sorted(manualUrls), sorted(includePageTypes), sorted(excludePageTypes), maxPages, browserPolicy, forceRefresh)))`. This is computed from the **request**, before target selection runs — deliberately, so a duplicate-request short-circuit doesn't require doing any selection/fetch work first. `forceRefresh=true` only changes in-run fetch behavior (skip conditional headers, force a fresh `200` fetch for every selected target) — it does **not** bypass the active-run conflict check; two concurrent requests for the same key, one of which is still `queued`/`running`, always conflict regardless of `forceRefresh`.

**Duplicate-active-run decision:** the service raises `DuplicateActiveCrawlRunError` (never silently returns the old run under a 200) — the router (T30) translates this to **HTTP 409 Conflict** with the existing run's `crawlRunId`/`status` in the error body, mirroring `DuplicateCompanyError`'s and `InvalidStatusTransitionError`'s existing 409 precedent in `modules/companies`.

## API schemas and router

**T29 — `api/schemas.py`**: camelCase DTOs (local `CamelCaseModel` base with `alias_generator=to_camel`, matching `modules/discovery/api/schemas.py` exactly — not imported cross-module, duplicated per existing precedent) for every response shape in the brief's section 17 example, plus `CrawlTargetResponse`/`PageResponse`/pagination envelopes for the four list/detail GETs. `PageResponse` never includes raw HTML or the full (untruncated) `extracted_text` by default — only a capped preview (`extractedTextPreview: str`, `extractedTextTruncated: bool`, a fixed preview cap distinct from and smaller than the storage-layer 250,000-char cap) plus an opaque `contentReference: { referenceId: string } | null` per artifact where applicable, never a filesystem path. `HttpMetadata`'s `response_headers_allowlist` passes through only the allowlisted headers already filtered at fetch time (T12) — the API layer does not re-filter, it trusts the domain model already only ever contains allowlisted keys.

**T30 — `api/router.py`** (not registered in `main.py` — required follow-up, see Dependencies): the eight endpoints listed under "Affected APIs," each thin (validates via Pydantic, calls exactly one service/repository method, translates domain exceptions to HTTP status: `CompanyNotFoundForCrawlError`/`DiscoveryRunNotFoundForCrawlError`/`CrawlRunNotFoundError`/`CrawlTargetNotFoundError`/`PageNotFoundError` → 404, `DuplicateActiveCrawlRunError` → 409). Query params on the two list endpoints exactly as the brief specifies (`page`, `pageSize`, `status`, `pageType`, `priority`, `fetchMode`, `browserRequired`, `includeFailed`). The `POST .../crawl-runs` endpoint runs `WebsiteCrawlService.start_crawl_run` synchronously inline (no `BackgroundTasks`, per the brief's explicit instruction) — the service itself takes no FastAPI types, so a future worker can call it identically, exactly matching `modules/discovery`'s own precedent.

## Fixtures

**T31 — `fixtures/crawling/`**: every file the brief's section 20 lists (`page-homepage.html`, `page-about.html`, `page-wholesale.html`, `page-contact.html`, `page-malformed.html`, `page-empty-shell.html`, `page-react-shell.html`, `page-vue-shell.html`, `page-next-shell.html`, `page-cloudflare-challenge.html`, `page-access-denied.html`, `page-password-storefront.html`, `page-heavy-scripts.html`, `page-dynamic-content-v1.html`, `page-dynamic-content-v2.html` and `page-meaningful-change.html` as a matched pair/triple for change-detection tests, `page-non-utf8.html`, `page-large.html`) — all hand-authored/sanitized fixtures, no real third-party content, mirroring `fixtures/discovery/`'s own sanitized-fixture convention.

## Tests (see also "Required Tests" and per-task references above)

**T32 — Unit tests** (`backend/tests/unit/crawling/`): one test file per pure domain module built above (`test_target_selector.py`, `test_robots_policy.py`, `test_retry_policy.py`, `test_rate_limiter.py`, `test_html_validator.py`, `test_html_cleaner.py`, `test_text_extractor.py`, `test_metadata_extractor.py`, `test_hashing.py`, `test_browser_fallback.py`, `test_local_filesystem_content_storage.py`, `test_httpx_page_fetcher.py` [using `httpx.MockTransport` + monkeypatched DNS, exactly matching `test_httpx_discovery_client.py`'s established pattern], `test_api_schemas.py`), each covering every case the brief's section 18 lists for that area.

**T33 — Integration tests** (`backend/tests/integration/crawling/`): a local `conftest.py` (own `FakeCompanyCrawlGateway`/`FakeDiscoveryCrawlGateway`/`FakeRobotsPolicyGateway`/`FakeCrawlRepository`/`FakePageFetcher`/`FakeBrowserPageFetcher`/`FakeContentStorage`, matching `backend/tests/integration/discovery/conftest.py`'s exact style — no real MongoDB, no real network, a locally-scoped `FastAPI()` app with only this module's router, not the shared `app.main.app`), covering every service-level scenario in section 18's "Application service with fakes" list plus every scenario in section 19 ("local fake HTTP servers", implemented via `httpx.MockTransport` the same way discovery's unit tests already do — this repository's established substitute for "a local fake HTTP server," not a literal socket-listening server). **Additionally**, a real-MongoDB test file, `backend/tests/integration/crawling/test_mongo_crawl_repository.py`, using the *inherited* root `backend/tests/conftest.py` fixtures (`test_database`/`motor_client` — available automatically to any test under `backend/tests/`, no edit to the shared root file required) plus a small **local** autouse fixture (defined in this module's own `conftest.py`, not the root one) dropping `crawl_runs`/`crawl_targets`/`pages` before/after each test — covering CRUD, index creation, the `pages` upsert-by-`(crawl_run_id, normalized_url)` behavior, and `document_version`-based stale-write rejection, directly answering the brief's conditional "Mongo repository behavior if Mongo test infrastructure already exists" (it does — confirmed by `modules/companies`'s own real-Mongo integration tests).

---

# Acceptance Criteria

**AC-01 — Priority-1 always included**
Given a candidate set containing a priority-1 URL and an unrelated set of lower-priority URLs exceeding every cap
When `select_crawl_targets` runs
Then the priority-1 URL is always present in the result, regardless of caps
Verification: `pytest backend/tests/unit/crawling/test_target_selector.py::test_priority_one_always_included`

**AC-02 — Product/collection/unknown caps enforced independently**
Given 10 product-typed candidates, 12 collection-typed candidates, and 6 unknown-typed candidates, all priority 2
When selection runs with default config (`max_product_pages=5`, `max_collection_pages=8`, `max_unknown_pages=3`)
Then exactly 5 product, 8 collection, and 3 unknown candidates are selected, and the total selected count never exceeds `max_pages_per_company`
Verification: `pytest backend/tests/unit/crawling/test_target_selector.py::test_per_category_caps`

**AC-03 — Deduplication by normalized URL**
Given the same normalized URL appearing twice in the candidate list with different raw URLs
When selection runs
Then exactly one target is selected for that normalized URL
Verification: `pytest backend/tests/unit/crawling/test_target_selector.py::test_deduplicates_by_normalized_url`

**AC-04 — Manual include overrides exclusion**
Given a URL classified `excluded` by priority
When it is present in `manual_include_urls`
Then it is selected despite its priority
Verification: `pytest backend/tests/unit/crawling/test_target_selector.py::test_manual_include_overrides_exclusion`

**AC-05 — Manual exclude overrides everything else**
Given a priority-1 URL present in `manual_exclude_urls`
When selection runs
Then it is not selected
Verification: `pytest backend/tests/unit/crawling/test_target_selector.py::test_manual_exclude_wins`

**AC-06 — Deterministic, repeatable output**
Given the same candidate list and config
When `select_crawl_targets` is called twice
Then both calls return targets in the exact same order
Verification: `pytest backend/tests/unit/crawling/test_target_selector.py::test_deterministic_output`

**AC-07 — Robots disallow blocks the fetch**
Given a robots rule group disallowing `/checkout`
When `evaluate_robots_policy` is called for `/checkout` under the matching user agent
Then it returns `disallowed`, and the crawl service marks that target's `PageFetchStatus` as `blocked_by_robots` without ever calling the fetcher for it
Verification: `pytest backend/tests/unit/crawling/test_robots_policy.py::test_disallow_blocks` and `pytest backend/tests/integration/crawling/test_website_crawl_service.py::test_robots_blocked_page_never_fetched`

**AC-08 — Unknown robots policy proceeds with a warning**
Given no matching `robots.txt` (fetch fails/404)
When a crawl run processes its targets
Then every affected page is still fetched, and the run's `CrawlSummary.warnings` count and `CrawlRun.warnings` list both reflect at least one "robots policy unknown" warning
Verification: `pytest backend/tests/integration/crawling/test_website_crawl_service.py::test_missing_robots_proceeds_with_warning`

**AC-09 — Extreme crawl-delay capped**
Given a robots `Crawl-delay: 300` and `max_honored_crawl_delay_s=10`
When `evaluate_robots_policy` is called
Then the returned `crawl_delay` is `10`, not `300`
Verification: `pytest backend/tests/unit/crawling/test_robots_policy.py::test_extreme_crawl_delay_capped`

**AC-10 — Unsupported scheme, credentials, localhost, and private IPs are all rejected before any request is attempted**
Given URLs using `ftp://`, containing `user:pass@`, resolving to `127.0.0.1`, `169.254.169.254`, `10.0.0.5`, and an IPv6 ULA (`fd00::1`)
When `HttpxPageFetcher.fetch_page` is called for each
Then each raises `DisallowedHostError` with a distinct, descriptive `reason`, and no network call is made for any of them
Verification: `pytest backend/tests/unit/crawling/test_httpx_page_fetcher.py::test_unsafe_targets_rejected`

**AC-11 — Redirect to a private host is rejected mid-chain**
Given a `MockTransport` handler where the first hop is a public URL that 302-redirects to `http://169.254.169.254/`
When `fetch_page` is called
Then `DisallowedHostError` is raised before the second hop's response body is ever read
Verification: `pytest backend/tests/unit/crawling/test_httpx_page_fetcher.py::test_redirect_to_private_host_rejected`

**AC-12 — Redirect and size limits enforced**
Given a handler that redirects 6 times (limit is 5) and, separately, a handler streaming a body 1 byte over `max_response_size_bytes`
When `fetch_page` is called for each
Then `TooManyRedirectsError` and `OversizedResponseError` are raised respectively, and the oversized case is aborted mid-stream (the handler is proven not to have sent its full configured body before the fetcher raised, via a chunk-count assertion)
Verification: `pytest backend/tests/unit/crawling/test_httpx_page_fetcher.py::test_redirect_limit` and `::test_oversized_response_aborted_mid_stream`

**AC-13 — Transient failures are retried; non-transient failures are not**
Given a handler returning `503` twice then `200`, and, separately, a handler always returning `404`
When `fetch_page` is called for each (with `max_attempts=3`)
Then the first succeeds on the third attempt with two recorded backoff delays, and the second returns/raises after exactly one attempt with no retry
Verification: `pytest backend/tests/unit/crawling/test_httpx_page_fetcher.py::test_transient_503_then_success` and `::test_non_transient_404_not_retried`

**AC-14 — `Retry-After` is honored and capped**
Given a `429` response with `Retry-After: 120` and `max_retry_after_s=60`
When `fetch_page` retries
Then the observed wait before the retry is capped at 60 seconds, not 120
Verification: `pytest backend/tests/unit/crawling/test_httpx_page_fetcher.py::test_retry_after_capped`

**AC-15 — Conditional request returns 304 → `unchanged`**
Given a previous page's `etag`/`last_modified` and a handler returning `304` when those headers are present
When the same target is fetched again
Then `PageFetchStatus` is `unchanged`, `unchanged_from_page_id` points at the previous page, and no new content is stored
Verification: `pytest backend/tests/integration/crawling/test_website_crawl_service.py::test_conditional_etag_returns_unchanged` and a matching `test_conditional_last_modified` case

**AC-16 — 200 with identical structural hash is also marked unchanged**
Given a server that ignores conditional headers and always returns 200, but the new response's cleaned HTML differs only by a changed timestamp/nonce attribute from the previous page
When the page is reprocessed
Then `raw_content_sha256` differs but `structural_hash` matches, and the page is still marked `unchanged` with `unchanged_from_page_id` set
Verification: `pytest backend/tests/unit/crawling/test_hashing.py::test_dynamic_noise_marked_unchanged` and `pytest backend/tests/integration/crawling/test_website_crawl_service.py::test_conditional_unchanged_via_structural_hash`

**AC-17 — Meaningfully different content is never hidden by structural normalization**
Given `page-dynamic-content-v1.html`/`page-dynamic-content-v2.html` (noise-only diff) and `page-meaningful-change.html` (real content diff) fixtures
When hashed and compared
Then the first pair's `structural_hash` matches, the second pair's does not
Verification: `pytest backend/tests/unit/crawling/test_hashing.py::test_meaningful_change_detected`

**AC-18 — HTML validation rejects binary/empty/wrong-content-type responses**
Given `page-large.html` truncated mid-byte, an empty body, a PNG magic-byte payload served with `content-type: text/html`, and a real image content-type
When `validate_and_decode` runs on each
Then each raises the correct typed error (`TruncatedContentDetected`-equivalent warning retained not raised, `EmptyResponseError`, a binary-signature rejection, and content-type rejection respectively) and none crashes on malformed input
Verification: `pytest backend/tests/unit/crawling/test_html_validator.py` (one test per case)

**AC-19 — Challenge/blocked pages are classified deterministically**
Given `page-cloudflare-challenge.html`, `page-access-denied.html`, `page-password-storefront.html`
When `classify_blocked_or_challenge` runs on each
Then each returns the correct classification with a stable rule id, and the configured `challenge_page_policy` produces the corresponding `PageFetchStatus`
Verification: `pytest backend/tests/unit/crawling/test_html_validator.py::test_challenge_page_classification`

**AC-20 — Cleaning removes unsafe/noisy content and preserves meaningful content**
Given `page-heavy-scripts.html` (scripts, inline event handlers, tracking pixels, analytics blocks) and `page-homepage.html`/`page-wholesale.html` (headings, forms, tables, links)
When `clean_html` runs
Then the output contains no `<script>` bodies, no `on*=` attributes, no tracking-pixel markers, and still contains the original headings/form fields/table rows/link `href`s, and running `clean_html` twice on the same input produces byte-identical output
Verification: `pytest backend/tests/unit/crawling/test_html_cleaner.py` (one test per removal/preservation/determinism case)

**AC-21 — Text extraction preserves order, caps length, and records truncation**
Given cleaned HTML longer than `max_extracted_text_length` and, separately, HTML with headings/lists/tables/alt text
When `extract_text` runs
Then the long case is truncated at exactly the configured cap with `truncated=True`, and the short case preserves heading/list/table/alt-text content in document order with normalized whitespace
Verification: `pytest backend/tests/unit/crawling/test_text_extractor.py`

**AC-22 — Metadata and technology signals extracted correctly**
Given `page-homepage.html` (title/description/canonical/lang/OG tags/generator) and `page-react-shell.html`/`page-next-shell.html` (framework markers)
When `extract_page_metadata` runs
Then every literal field matches the fixture's known values, framework/commerce/analytics markers are captured in `technology_signals`, and no company-facing model anywhere is touched by this function
Verification: `pytest backend/tests/unit/crawling/test_metadata_extractor.py`

**AC-23 — Browser fallback is detected deterministically for every fixture shell type**
Given `page-empty-shell.html`, `page-react-shell.html`, `page-vue-shell.html`, `page-next-shell.html`, `page-heavy-scripts.html` (high script-to-text ratio), and `page-homepage.html` (normal server-rendered)
When `detect_browser_fallback` runs on each
Then the five shell/heavy-script fixtures return `browser_required=True` with the correct `reason` and a non-empty `rule_ids`, the normal page returns `browser_required=False`, and re-running any case yields identical `rule_ids` (deterministic)
Verification: `pytest backend/tests/unit/crawling/test_browser_fallback.py`

**AC-24 — `detect_only` never invokes the browser fetcher**
Given a run with `browserPolicy=detect_only` and a `FakeBrowserPageFetcher` that would raise if ever called, over a target that trips `browser_required`
When the run completes
Then the target's `PageFetchStatus` is `browser_required` (not `browser_fetched`), `CrawlSummary.pages_requiring_browser >= 1`, `CrawlSummary.pages_browser_fetched == 0`, and the fake fetcher was never invoked
Verification: `pytest backend/tests/integration/crawling/test_website_crawl_service.py::test_detect_only_never_fetches`

**AC-25 — `fetch_when_required` invokes the browser fetcher and preserves the HTTP result on browser-fetch failure**
Given `browserPolicy=fetch_when_required` and a `FakeBrowserPageFetcher` configured to fail
When a browser-required page is processed
Then the page record retains its original HTTP-fetched `cleaned_html`/`extracted_text` (not discarded), a warning is recorded, and the run does not fail because of the browser-fetch failure
Verification: `pytest backend/tests/integration/crawling/test_website_crawl_service.py::test_browser_fetch_failure_preserves_http_result`

**AC-26 — Safe path construction and path-traversal rejection**
Given attempted `company_id`/`crawl_run_id`/`page_id` values containing `../`, an absolute path, and a null byte
When `LocalFilesystemContentStorage.store_raw_content` is called with each
Then each raises `UnsafeStoragePathError` and no file is written outside the configured base directory
Verification: `pytest backend/tests/unit/crawling/test_local_filesystem_content_storage.py::test_path_traversal_rejected`

**AC-27 — Atomic writes and hash verification**
Given valid IDs and content
When `store_raw_content` is called
Then the final file is only ever visible in its complete form (no partial-write window observable via a separate reader thread/process) and `load_content` returns bytes whose SHA-256 matches what was stored
Verification: `pytest backend/tests/unit/crawling/test_local_filesystem_content_storage.py::test_atomic_write_and_hash_verification`

**AC-28 — Inline vs. external storage thresholds respected**
Given cleaned HTML/extracted text below and above `config.inline_cleaned_html_limit_bytes`/`inline_extracted_text_limit_bytes`
When the crawl service stores a page's content
Then content below the threshold is stored inline on `CrawledPage.cleaned_html`/`extracted_text` with `ContentStorageInfo.*_mode == "inline"`, and content above it is written externally with `*_mode == "external"` and a populated `ContentReference`
Verification: `pytest backend/tests/integration/crawling/test_website_crawl_service.py::test_inline_and_external_storage_thresholds`

**AC-29 — One page's failure does not fail the run; the homepage's failure marks it partial**
Given a run with 5 targets where target 3 (not the homepage) fails unconditionally, and, separately, a run where the homepage target fails
When each run completes
Then the first run reaches `completed_with_warnings` (or `partial`, per config) with 4 pages successfully recorded and 1 `failed`, and the second reaches `partial` (per the documented default), never `failed` outright, and never aborts before processing the remaining targets
Verification: `pytest backend/tests/integration/crawling/test_website_crawl_service.py::test_one_page_failure_isolated` and `::test_homepage_failure_marks_partial`

**AC-30 — Cancellation stops new scheduling but preserves completed pages**
Given a run cancelled after 2 of 5 targets have completed
When `cancel_run` is called and processing checks cancellation before the next target
Then no further targets are fetched, the 2 already-completed pages remain in MongoDB/the fake repository untouched, and the run's status reflects cancellation
Verification: `pytest backend/tests/integration/crawling/test_website_crawl_service.py::test_cancellation_preserves_completed_pages`

**AC-31 — Duplicate active-run requests conflict; retry-failed does not duplicate page records**
Given a `queued`/`running` run for a given `(company_id, discoveryRunId, options)` combination
When `start_crawl_run` is called again with the identical combination
Then `DuplicateActiveCrawlRunError` is raised (translated to HTTP 409 by the router) referencing the existing run's id; separately, given a completed run with 2 failed targets, calling `retry_failed` twice in a row results in exactly 2 page documents for those targets in `pages` (not 4), each reflecting the latest attempt
Verification: `pytest backend/tests/integration/crawling/test_website_crawl_service.py::test_duplicate_active_run_conflicts` and `::test_retry_failed_does_not_duplicate_pages`

**AC-32 — Company processing status is advanced correctly**
Given a successful run and, separately, a failed run
When each completes
Then `CompanyCrawlGateway.update_processing_status` was called with `CRAWLING` at start and `CRAWLED`/`FAILED` at the end respectively (asserted against a `FakeCompanyCrawlGateway`'s recorded calls)
Verification: `pytest backend/tests/integration/crawling/test_website_crawl_service.py::test_company_status_advances`

**AC-33 — `CrawlSummary` is accurate**
Given a run with a known, fixed mix of outcomes (some fetched, one unchanged, one blocked-by-robots, one failed, two requiring browser)
When the run completes
Then every `CrawlSummary` counter (`targets_selected`, `pages_fetched`, `pages_unchanged`, `pages_skipped`, `pages_blocked_by_robots`, `pages_failed`, `pages_requiring_browser`, `pages_browser_fetched`, `bytes_downloaded`, `warnings`, `duration_ms`) exactly matches the constructed scenario
Verification: `pytest backend/tests/integration/crawling/test_website_crawl_service.py::test_summary_accuracy`

**AC-34 — API responses are camelCase, paginated, and never leak raw HTML or filesystem paths**
Given a completed run
When `GET /api/crawl-runs/{id}/pages` and `GET /api/pages/{id}` are called
Then every JSON key is camelCase, `pagination.total`/`page`/`pageSize` are present and correct, no response body contains a full filesystem path (asserted by searching the serialized JSON for the configured storage base directory string) or the full untruncated `extracted_text`, and enum fields serialize as their string values
Verification: `pytest backend/tests/integration/crawling/test_api_schema_serialization.py`

**AC-35 — `includeFailed`/`status`/`pageType`/`priority`/`fetchMode`/`browserRequired` filters work on the list endpoints**
Given a run with a mix of statuses/page types/fetch modes
When `GET /api/crawl-runs/{id}/pages` is called with each filter individually
Then only matching pages are returned; when `includeFailed=false` (default), failed pages are excluded; when `true`, they are included
Verification: `pytest backend/tests/integration/crawling/test_api_schema_serialization.py::test_page_list_filters`

**AC-36 — Real MongoDB repository behavior**
Given a real (test-database) `MongoCrawlRepository`
When a run/target/page is created, then updated with a stale `document_version`
Then the stale update is rejected (no document mutated), `ensure_indexes()` produces every specified index including the unique `(crawl_run_id, normalized_url)` index on both `crawl_targets` and `pages`, and a repeated `save_page` for the same `(crawl_run_id, normalized_url)` upserts rather than inserting a second document
Verification: `pytest backend/tests/integration/crawling/test_mongo_crawl_repository.py`

---

# Required Tests

**Unit tests** (`backend/tests/unit/crawling/`, no MongoDB, no real network — `httpx.MockTransport` for the one file that needs HTTP semantics): target selection, robots policy, retry policy, rate limiting, HTTP safety (`test_httpx_page_fetcher.py`), HTML validation, HTML cleaning, text extraction, metadata extraction, hashing/change-detection, browser-fallback detection, local filesystem storage, API schema shape — one file per domain module, covering every case enumerated in the task brief's section 18 and formalized as AC-01 through AC-28 above.

**Integration tests** (`backend/tests/integration/crawling/`): `WebsiteCrawlService` against fakes for every port (company gateway, discovery gateway, robots gateway, repository, page fetcher, browser page fetcher, content storage) — covering every scenario in the brief's section 18 "Application service with fakes" list and section 19's fake-HTTP-server-equivalent scenarios (redirect chain, gzip HTML, conditional ETag/Last-Modified, 304, 429+Retry-After, transient-503-then-success, oversized streamed response, malformed content-type, robots delay, local content-storage round trip — all via `httpx.MockTransport`, this repository's established substitute for a literal local fake HTTP server), formalized as AC-29 through AC-35. Plus a real-MongoDB `test_mongo_crawl_repository.py` (AC-36), built without any edit to the shared root `backend/tests/conftest.py` (its fixtures are inherited automatically; only a new local, module-scoped `conftest.py` under `backend/tests/integration/crawling/` is needed).

**API tests**: covered within `backend/tests/integration/crawling/test_api_schema_serialization.py` — camelCase, pagination, enum serialization, no-raw-HTML/no-filesystem-path leakage, filter correctness (AC-34, AC-35).

**Browser tests**: not applicable — no frontend work is in scope for this task.

**Manual verification**: not required to complete this task (no real MongoDB/network dependency is load-bearing for any automated test — the real-MongoDB repository test uses the existing dedicated test database, and everything HTTP-shaped uses `httpx.MockTransport`). Recommended once the "Required follow-up" integration steps land (router registered, real `update_latest_crawl_run`, real `DiscoveryCrawlGateway` wiring confirmed end-to-end): a real smoke test against a real company/discovery run, mirroring exactly how Task 005's completion report describes its own manual verification.

---

# Risks

**Technical risks**
- Brotli (`br`) decompression is explicitly required by the task brief's section 4, but no Brotli-capable package (`brotli`/`brotlicffi`) is a dependency of this repository, and `pyproject.toml` is off-limits to this task. **Resolution applied in this contract**: the fetcher never advertises `br` in `Accept-Encoding` (only `gzip`), so compliant servers never send Brotli-encoded responses in the first place; if a server sends `Content-Encoding: br` unprompted anyway, it is treated as an unsupported/rejected response rather than silently mishandled. Flagged as a residual gap (documented in `HttpxPageFetcher`'s own module docstring) rather than silently ignored — promoting an optional Brotli dependency is a future, out-of-allowed-paths integration step if full parity is ever required.
- The DNS-rebinding/TOCTOU gap already documented in `HttpxDiscoveryClient` applies identically here (the safety check happens immediately before each request, but `httpx`'s own connection can re-resolve a very-short-TTL hostname at socket-open time). Copied forward as a documented, not silently repeated, residual risk — full closure needs a custom transport pinning the validated IP, out of scope.
- Structural-hash normalization is a genuine judgment call between "too strict" (never detects unchanged pages, defeating conditional-fetch savings) and "too aggressive" (hides real content changes). AC-16/AC-17 and their fixtures are the concrete guardrail, but any real site's actual noise patterns may need future tuning beyond what two fixture pairs can prove.
- No public-suffix-list/registrable-domain library exists in this repository (same gap discovery already documented) — not needed by this module directly, noted only because target selection's "prefer same-domain" heuristics, if ever added, would inherit the same limitation.

**Business risks**
- `detect_only` (the mandated default) means a company whose site is entirely client-rendered gets pages marked `browser_required` with little or no usable extracted text until a real browser adapter exists — Extraction/Analysis will see thin/empty content for such companies until the flagged Playwright follow-up lands. This is an accepted, explicit limitation of this task, not an oversight.
- `CompanyServiceCrawlGateway.update_latest_crawl_run` being a no-op means `GET /api/companies/{id}` (once wired) will not reflect a company's latest crawl run id until the required follow-up lands — a real but bounded, documented gap.

**Performance risks**
- Sequential, concurrency-1-per-company crawling (mandated default) means a company with 30 targets at a 1-second default delay takes at least ~30 seconds per run — acceptable for this task's explicit "no distributed concurrency" constraint, but a real operational consideration once this is used at any scale beyond local development.
- Local filesystem content storage has no cleanup/retention policy in this task — repeated runs accumulate raw HTML on disk indefinitely. Explicitly out of scope (see below).

**Security risks**
- No authentication exists anywhere in this repository yet (consistent with every prior module) — this module's router, once registered, is open to anyone who can reach the API. Acceptable for local/single-tenant v1, same accepted risk already recorded for every prior contract/module.
- All external HTML is treated as untrusted: never executed, only parsed via stdlib `html.parser`/regex-style detectors — no `eval`, no template rendering of fetched content anywhere in this module.

**Data integrity risks**
- `document_version`-based optimistic concurrency (T21/AC-36) protects against stale concurrent writes to the *same* document, but this task's sequential, single-worker design means this is defense-in-depth for a future multi-worker scenario, not something exercised by normal single-worker operation today.
- The `data/crawl-content/` runtime directory is not added to `.gitignore` (root `.gitignore` is off-limits to this task) — running the module locally will leave an untracked directory `git status` will show. Noted as a minor, non-blocking follow-up (see Dependencies), not a data-integrity issue.

---

# Dependencies

**External APIs:** None (no OpenAI/AI calls in this task).

**MongoDB:** Required for `MongoCrawlRepository` (three new collections: `crawl_runs`, `crawl_targets`, `pages`). Uses the existing Motor client factory (`app.db.get_database`) via the same DI pattern as every prior module — no new MongoDB connectivity code.

**Playwright:** Not used. Confirmed absent from the repository by grep. `BrowserPageFetcher` ships as a port + fake only in this task; a real adapter is an explicit, reported, out-of-scope integration step.

**httpx:** Already promoted to `[project.dependencies]` in `pyproject.toml` (a Task-005 follow-up) — no `pyproject.toml` change needed for this task's HTTP fetching.

**Brotli:** Not added. See Risks — sidestepped by never requesting `br` encoding.

**Environment variables:** None new — `CrawlConfig` is a plain, injectable Pydantic model per the hexagonal convention (matching `DiscoveryConfig`), never reading `os.environ` directly; wiring real values from `backend/app/config.py`'s `Settings` is a future integration step, not part of this task (`config.py` is off-limits to this task's allowed paths).

**Required follow-up outside this task's allowed paths (report, do not build):**
1. Register `crawling_router` in `backend/app/main.py`, and wire `MongoCrawlRepository.ensure_indexes()` into the app's startup `lifespan` handler, alongside the three existing `ensure_indexes()` calls.
2. Add `CompanyRepository.update_latest_crawl_run_id` (interface + `MongoCompanyRepository` implementation) and `CompanyService.update_latest_crawl_run` in `modules/companies/`, mirroring `update_latest_discovery_run` exactly; then switch `CompanyServiceCrawlGateway.update_latest_crawl_run` from its documented no-op to a real call.
3. (Optional, non-blocking, recorded for completeness) Promote `DiscoveryRepositoryCrawlGateway`'s current "import `get_discovery_repository` directly from `modules/discovery/api/router.py`" approach into a proper `DiscoveryQueryService` in `modules/discovery/application/`, for symmetry with `CompanyService`. Not required for this task to be considered complete — the direct-import adapter is already a real, correct, working implementation.
4. A real `BrowserPageFetcher` adapter (e.g. Playwright), if/when browser-rendered crawling is actually needed — currently `detect_only` by mandated default, and no browser-automation dependency exists in this repository at all.
5. (Optional, minor) Add `data/` (or whatever base directory name is chosen for local content storage) to root `.gitignore`.

---

# Out of Scope

Exactly the task brief's own section 22 list, carried forward verbatim: website discovery (already built, Task 005); StoreLeads import (already built, Task 004); structured business extraction; company facts; evidence records; AI analysis; scoring; ranking; frontend pages; production deployment; CI/CD; authentication; distributed crawling; proxy rotation; CAPTCHA solving; anti-bot bypass; stealth browser techniques. Additionally, explicitly out of scope for this contract specifically: registering the router in `main.py`; any change to `modules/companies/**`, `modules/discovery/**`, `pyproject.toml`, `backend/app/config.py`, or root `.gitignore` (all reported as required follow-ups above, not built here); a real Playwright/browser adapter; any content-download/raw-HTML API endpoint beyond the eight listed (no dedicated "fetch raw HTML" route exists in the brief's endpoint list, so none is added); storage retention/cleanup policy for `data/crawl-content/`.

---

# Suggested Implementation Order

1. T1–T4 — enums, domain models, config, exceptions (nothing else compiles without these)
2. T5 — target selection + its unit tests (T32 subset) — fully independent of everything else
3. T6, T7 — robots policy evaluation (pure) + its unit tests
4. T9, T10, T11 — fetch/retry/rate-limit domain contracts and pure logic + their unit tests
5. T12 — `HttpxPageFetcher` + its unit tests (the highest-risk, safety-critical file — get it right and tested before anything depends on it)
6. T8 — `HttpRobotsPolicyGateway` (depends on T12's fetcher + discovery's `parse_robots_txt` reuse)
7. T13–T17 — HTML validation, cleaning, text extraction, metadata, hashing + their unit tests, using the T31 fixtures (build fixtures alongside these, not after)
8. T18, T19 — content storage abstraction + local filesystem implementation + its unit tests
9. T20, T21 — `CrawlRepository` + `MongoCrawlRepository` + the real-Mongo integration test
10. T22–T25 — gateway ports + adapters (`CompanyServiceCrawlGateway`, `DiscoveryRepositoryCrawlGateway`, `HttpRobotsPolicyGateway` wiring)
11. T26, T27 — browser-fallback detection + policy handling + its unit tests
12. T28 — `WebsiteCrawlService`, assembling every port above, with its fakes-based integration test suite (T33)
13. T29, T30 — API schemas + router (unregistered) + API schema serialization tests
14. Full local verification: `pytest backend/tests/unit/crawling backend/tests/integration/crawling`, `ruff check`, `pyright` on all new/changed paths
15. Final report: files created, HTTP-safety controls implemented, robots behavior, retry policy, change-detection behavior, storage behavior, browser-fallback detection, known limitations, and the required-follow-up list above — exactly per the task brief's own section 24 "After implementation" reporting requirement

---

# Success Criteria

This feature is complete only when:

✓ AC-01 through AC-36 all pass

✓ Every test file listed under "Required Tests" exists and passes, including the fixture-backed unit tests and the real-MongoDB `test_mongo_crawl_repository.py`

✓ `domain/` and `application/` contain zero imports of FastAPI, Motor/pymongo, Playwright, or `httpx` (confirmed by inspection, matching the discipline already enforced in `modules/companies`/`modules/discovery`)

✓ No file outside `backend/app/modules/crawling/**`, `backend/tests/unit/crawling/**`, `backend/tests/integration/crawling/**`, `fixtures/crawling/**` was modified — confirmed via `git diff --stat`

✓ The three cross-module resolutions above (`update_latest_crawl_run` no-op, `DiscoveryRepositoryCrawlGateway`'s direct-import adapter, `RobotsPolicyGateway` owned entirely by this module) are implemented exactly as decided, each with the documentation this contract specifies — not left as silent or differently-resolved gaps

✓ `ruff check` and `pyright` are clean on every new/changed path

✓ The "Required follow-up outside this task's allowed paths" list is reported, not silently built or silently omitted

✓ Evaluator reports PASS