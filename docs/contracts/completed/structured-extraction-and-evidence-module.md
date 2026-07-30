# Feature Contract: Task 007 — Structured Extraction and Evidence Modules

**Source task brief (preserved verbatim, read-only input to this contract):**
`docs/execution-plans/tasks/007—Structured-Extraction-and-Evidence-Module.md`

**Primary style/structure reference (same build pattern, same repo, most recent):**
`docs/contracts/completed/crawling-module.md` (Task 006)

This contract does not redesign the brief — every model name, enum value, field-path list, extractor requirement, endpoint, and constraint the brief specifies is treated as authoritative. What follows resolves the ambiguities the brief deliberately leaves open (cross-module gateway shape, module-internal boundary between `extraction` and `evidence`, unregistered-router status) the same way `crawling-module.md` resolved Task 006's equivalent gaps — decided now, not left for the generator to discover.

---

# Feature

## Business Goal

The pipeline is **Ingestion → Crawling → Interpretation → Scoring → MongoDB → API → Frontend**. Ingestion, Discovery, and Crawling now exist (Tasks 004/005/006) and produce stored, cleaned page content per company. Nothing yet turns that page content into structured, trustworthy business facts. Without an Extraction stage, Crawling's output is inert HTML/text with no way for a future Analysis/Scoring stage to answer "does this company do wholesale," "what platform do they run," "how many retail stores do they have." This feature builds that stage: deterministic (non-AI), pattern-based extractors that read crawled page content and produce **evidence-backed** facts — every accepted value traceable to the exact page, location, and excerpt that produced it, with conflicts preserved rather than silently resolved and unknowns never converted into false negatives.

## User Story

As the pipeline (and, later, an operator or a future Analysis/Scoring stage), I want a company's crawled pages turned into structured, versioned, confidence-scored facts — each backed by concise, reproducible evidence and reconciled deterministically across pages — so that downstream Analysis/Scoring has trustworthy, auditable business facts to work from, without any of this stage silently inventing information the pages didn't actually say.

## Business Value

Turns Crawling's raw page content into the structured data every later stage depends on, and establishes the first evidence-backed, audit-trail persistence pattern in the repository — every future analysis/scoring decision can be traced back to source. Establishes reusable precedent (deterministic pattern-matching, versioned confidence/reconciliation policy, evidence factory with redaction/immutability rules) for whatever future AI-assisted extraction stage is eventually layered on top, without this task depending on one.

---

# Architecture Impact

## Affected domains

Two new hexagonal modules, `backend/app/modules/extraction/` and `backend/app/modules/evidence/`, following the exact `domain → application → infrastructure → api` layering already established by `modules/companies`, `modules/imports`, `modules/discovery`, `modules/crawling` (`ARCHITECTURE.md`'s "Module convention (hexagonal variant)"). No existing module or domain's files are modified — confirmed against this task's own allowed-paths restriction (`backend/app/modules/extraction/**`, `backend/app/modules/evidence/**`, `backend/tests/unit/{extraction,evidence}/**`, `backend/tests/integration/{extraction,evidence}/**`, `fixtures/extraction/**` only). Confirmed by inspection: neither `backend/app/modules/extraction/` nor `backend/app/modules/evidence/` nor `fixtures/extraction/` currently exist — this is a from-scratch build, not an extension.

## Affected services

New: `StructuredExtractionService` (`backend/app/modules/extraction/application/structured_extraction_service.py`) — orchestrates one extraction run end-to-end (validate company/crawl run → select eligible pages → build `PageContext`s → run extractors → create candidates → create evidence → reconcile → persist facts/conflicts → mark stale prior facts → project → advance company status), mirroring `WebsiteCrawlService`'s and `WebsiteDiscoveryService`'s shape and their "depend only on domain ports, never a concrete Mongo/HTTP/FastAPI type" discipline.

New: `EvidenceService` (`backend/app/modules/evidence/application/evidence_service.py`) — thin orchestration over `EvidenceRepository` (create/get/list/update-status), independently queryable per the brief's explicit requirement ("evidence must be first-class and independently queryable" — brief line 52), not merely a helper class embedded inside extraction.

No existing service is modified. `CompanyService`, `CrawlRepository`, and `ContentStorage` are consumed only through this task's own gateway ports — never called or constructed directly outside their own DI-provided instances (see "Cross-module dependency decisions" below).

## Affected repositories

New: `ExtractionRepository` (ABC port, `domain/repository.py`) + `MongoExtractionRepository` (`infrastructure/mongo_extraction_repository.py`), and `EvidenceRepository` (ABC port) + `MongoEvidenceRepository` (`infrastructure/mongo_evidence_repository.py`) — both following the exact pattern of `MongoCrawlRepository`/`MongoCompanyRepository`/`MongoDiscoveryRepository` (Motor-only, confined to one file each, `ensure_indexes()` idempotent). Justified per the brief's own instruction (section 22, "Implement MongoDB repositories only if an approved MongoDB infrastructure pattern already exists in the worktree") — confirmed present (four prior real Mongo repositories exist), so building these is in scope, exactly as Task 006 built `MongoCrawlRepository` under the identical instruction.

No existing repository (`CompanyRepository`, `DiscoveryRepository`, `CrawlRepository`, or the flat `app/domains/companies/repository.py`) is modified or imported concretely.

## Affected APIs

New, built but **not registered** in `backend/app/main.py` (per the brief's explicit "Create but do not centrally register extraction and evidence routers" — section 23, and per `backend/app/main.py` and `backend/app/api/**` both being on this task's own "Do not modify" list), mirroring `modules/imports`, `modules/discovery`, and `modules/crawling`'s already-unregistered routers:

- `POST /api/companies/{company_id}/extraction-runs`
- `GET /api/companies/{company_id}/extraction-runs/latest`
- `GET /api/extraction-runs/{extraction_run_id}`
- `GET /api/extraction-runs/{extraction_run_id}/facts`
- `GET /api/extraction-runs/{extraction_run_id}/candidates`
- `GET /api/companies/{company_id}/facts`
- `GET /api/facts/{fact_id}`
- `GET /api/facts/{fact_id}/evidence`
- `GET /api/evidence/{evidence_id}`

Registering these in `main.py` is a required, out-of-allowed-paths **integration step** (see Dependencies / Suggested Implementation Order), not part of this contract's deliverable — same pattern as every prior module's contract.

## Affected database collections

New: `extraction_runs`, `extractor_executions`, `fact_candidates`, `facts`, `fact_conflicts` (all owned exclusively by `MongoExtractionRepository`) and `evidence` (owned exclusively by `MongoEvidenceRepository`). No existing collection (`companies`, `companies_pipeline`, `discovery_runs`, `discoveries`, `crawl_runs`, `crawl_targets`, `pages`) is written to directly by either new module — reached only through this task's own gateway ports, never a concrete Mongo repository imported from another module.

Note: `companies_pipeline`'s `CompanyProcessing` model (`backend/app/modules/companies/domain/models.py`) already declares `latest_extraction_run_id: str | None = None` — confirmed present, mirroring the field slot Task 006 found for `latest_crawl_run_id`. What is **not** present, confirmed by inspection: (a) any setter method (`CompanyRepository`/`CompanyService` has `update_latest_discovery_run_id`/`update_latest_discovery_run` but no `update_latest_extraction_run_id`/`update_latest_extraction_run` equivalent), and (b) any field at all — not even an unset one — for a facts/latest-facts projection (`CompanyProcessing` has no `latest_facts` field, `Company` has no such field, `CompanyRepository` has no such method). See resolution #2 and #3 below.

## Affected frontend pages

None. No frontend work is in scope for this task (explicit constraint, brief section 29, and `frontend/**` is on the task's own "Do not modify" list).

---

# Cross-module dependency decisions (resolved now, not left for the generator to discover)

Five real design questions exist between what this task needs and what `modules/companies` and `modules/crawling` currently expose, plus one internal question (how `extraction` and `evidence` relate to each other, since both are built in this same task). All five are resolved below, concretely.

### 1. `CrawlExtractionGateway` — buildable as a **real** adapter today, not a no-op

Unlike Task 006's `DiscoveryCrawlGateway` (which had to reach one layer below `WebsiteDiscoveryService` because that service had no query methods), `modules/crawling` already exposes exactly what's needed, confirmed by inspection of `backend/app/modules/crawling/api/router.py`:

- `get_crawl_repository(database=Depends(get_database)) -> CrawlRepository` — a plain, public, non-underscore-prefixed module-level function (line 66), same shape as `get_discovery_repository`/`get_company_service`.
- `get_content_storage() -> ContentStorage` — same shape (line 94).

**Decision:** `infrastructure/crawl_repository_gateway.py`'s `CrawlRepositoryExtractionGateway(CrawlExtractionGateway)` wraps `CrawlRepository` and `ContentStorage` — both **interfaces** (never `MongoCrawlRepository`/`LocalFilesystemContentStorage` concretely) — obtained by importing the already-public `get_crawl_repository` and `get_content_storage` functions from `app.modules.crawling.api.router`. This requires **zero changes to `modules/crawling/**`**, so it is fully buildable within this task's allowed paths and yields a real (non-fake) adapter, not a fake deferred to a future task — the same "wrap one layer below the service, because that's what the target module actually publicly exposes" precedent `DiscoveryRepositoryCrawlGateway` set in Task 006, just landing on "yes, real" instead of "documented no-op" this time.

Concrete method mapping (all three `CrawlExtractionGateway` methods the brief names, section 20):

- **`get_crawl_run(crawl_run_id) -> CrawlRun`** — `CrawlRepository.get_run(crawl_run_id)`; raises `CrawlRunNotFoundForExtractionError` if `None`. Returns crawling's own `CrawlRun` Pydantic model directly (a pure value type with zero FastAPI/Motor imports of its own — confirmed by inspection of `domain/models.py` — reused across the module boundary exactly like `DiscoveryCrawlGateway.get_discovery_run` reuses `DiscoveryRun`).
- **`list_pages(crawl_run_id, statuses, page_types) -> list[CrawledPage]`** — `CrawlRepository.list_pages_by_run` only accepts a **single** `status`/`page_type` filter plus pagination, not the plural `statuses`/`page_types` lists the brief's literal signature implies. **Decision:** the adapter pages through `list_pages_by_run(crawl_run_id, page=N, page_size=200)` exhaustively (loop until a short page is returned — the same "loop until exhausted" precedent `DiscoveryRepositoryCrawlGateway.list_discovered_urls` already established for an identical singular-filter/plural-request mismatch) and filters the accumulated results in-memory against `statuses`/`page_types` before returning. Documented in the adapter's own docstring, not left implicit.
- **`load_page_content(page_id, content_kind) -> bytes | None`** — `content_kind: Literal["raw", "cleaned", "text"]`, matching `PageContext`'s needs (brief section 4). Implementation: `CrawlRepository.get_page(page_id)`, then per `content_kind`:
  - `"raw"`: `page.raw_content_reference` if set → `ContentStorage.load_content(reference)` (bytes); `None` if unset (e.g. an `unchanged` page never re-stores raw content).
  - `"cleaned"`: `page.cleaned_html` if inline (`content_storage.cleaned_html_mode == "inline"`) → `.encode("utf-8")`; else `content_storage.cleaned_html_reference` → `ContentStorage.load_content(...)`; else `None`.
  - `"text"`: same pattern against `page.extracted_text`/`content_storage.extracted_text_reference`.

  **New decision this contract makes explicit (not covered by the brief, and not encountered by any prior task):** when a page's `fetch_status == PageFetchStatus.UNCHANGED`, its own `cleaned_html`/`extracted_text`/`raw_content_reference` are **not** re-populated (confirmed by inspection of `WebsiteCrawlService`'s change-detection path and `CrawledPage.unchanged_from_page_id`) — the actual content lives on the page `unchanged_from_page_id` points to. `CrawlRepositoryExtractionGateway.load_page_content` therefore **transparently follows `unchanged_from_page_id`** (via one additional `CrawlRepository.get_page` call) when the requested page's own content for that `content_kind` is empty and `unchanged_from_page_id` is set, rather than returning `None` for a page that in fact has content — one level of indirection only (crawling's own change-detection never chains more than one hop, confirmed by `WebsiteCrawlService`'s `get_latest_page_by_normalized_url` usage always pointing at the immediately-preceding page). This resolution is required for AC-30/AC-31 below to be satisfiable at all with a real (non-fake) adapter.

**Page eligibility, made concrete:** `StructuredExtractionService` selects pages with `fetch_status in {PageFetchStatus.FETCHED, PageFetchStatus.UNCHANGED, PageFetchStatus.BROWSER_FETCHED}` as extraction-eligible; `QUEUED`/`FETCHING`/`SKIPPED`/`BLOCKED_BY_ROBOTS`/`REJECTED`/`FAILED`/`BROWSER_REQUIRED` (without a fetch) are skipped per brief section 19's "skip failed or unavailable pages," each producing an `ExtractionWarning`, never an error.

### 2. `CompanyExtractionGateway.update_latest_extraction_run` — documented, logged no-op (same shape as Task 006's own gap)

`CompanyRepository`/`CompanyService` (confirmed by inspection of `backend/app/modules/companies/{domain/repository.py,application/service.py}`) has `update_latest_discovery_run_id`/`update_latest_discovery_run` but **no** `update_latest_extraction_run_id`/`update_latest_extraction_run`, even though `CompanyProcessing.latest_extraction_run_id` already exists as a field (confirmed present in `domain/models.py`) and is already persisted by `model_dump()` — it just has no dedicated setter method or MongoDB update path. This is the exact same shape of gap `CompanyServiceCrawlGateway.update_latest_crawl_run` already documented as a no-op in Task 006, still unresolved as of this task (confirmed: no `update_latest_crawl_run` exists either, today).

**Decision:** `infrastructure/company_service_gateway.py`'s `CompanyServiceExtractionGateway.update_latest_extraction_run` is a **documented, logged no-op** (log at `INFO`, include `company_id`/`extraction_run_id`, cite this exact gap in the docstring) — following `CompanyServiceCrawlGateway.update_latest_crawl_run`'s exact precedent (confirmed by direct inspection of that file's docstring and implementation).

**Required follow-up (report, do not build):** add `CompanyRepository.update_latest_extraction_run_id` + `MongoCompanyRepository` implementation + `CompanyService.update_latest_extraction_run`, mirroring `update_latest_discovery_run` exactly.

### 3. `CompanyExtractionGateway.project_latest_facts` — documented no-op, but a **larger** gap than #2

Confirmed by inspection: `Company`/`CompanyProcessing` (`backend/app/modules/companies/domain/models.py`) has **no field at all** — not `latest_facts`, not any placeholder — for a facts projection, and `CompanyRepository` has no corresponding method. This differs materially from `latest_extraction_run_id` (#2 above) and from Task 006's `latest_crawl_run_id` gap, both of which were "the field slot already exists, only the setter is missing." Here, closing the gap for real requires (a) a new field on the `Company` domain model, (b) a new `CompanyRepository` method, (c) a MongoDB migration/backfill consideration for existing `companies_pipeline` documents, and (d) a decision about whether the projection is stored flattened or nested — none of which this task can do, since `modules/companies/**` is off-limits.

**Decision:** `CompanyServiceExtractionGateway.project_latest_facts` is also a documented, logged no-op — logging the `company_id` and the number of projected fields, with a docstring explicitly distinguishing this from resolution #2 as "a larger follow-up: no field exists yet to write into, not merely a missing setter." The extraction module still **builds** the projection value in full (per brief section 21 — `domain/company_projection.py`'s `CompanyFactsProjection` model, covering identity/business/catalogue/operations/technology/organisation/growth/extraction-quality, each field carrying `value`/`verification_state`/`confidence`/`evidence_ids`/`last_verified_at`) and calls the gateway with it — the no-op only affects whether that value is ever durably written to the Company module; the projection itself is still fully constructed, tested, and available to any caller that queries the extraction module's own API/repository directly (`GET /api/companies/{company_id}/facts` already serves the same underlying data, evidence-linked, without needing the Company-side projection at all).

**Required follow-up (report, do not build — larger scope than a mirrored setter):** design and add a `latest_facts`-shaped field (or equivalent) to `Company`/`CompanyProcessing`, a `CompanyRepository.update_latest_facts` method, and a `CompanyService.update_latest_facts` method, then switch this gateway method from a no-op to a real call — likely warrants its own task brief given the schema-design decision involved (flattened by field-path vs. nested by domain-group), not a one-line mirror of #2.

### 4. `CompanyExtractionGateway.update_processing_status` — fully real today

Confirmed by inspection: `ProcessingStatus.EXTRACTING`/`ProcessingStatus.EXTRACTED` already exist (`backend/app/modules/companies/domain/enums.py`), and the transition graph (`backend/app/modules/companies/domain/transitions.py`) already wires `CRAWLED → {EXTRACTING, FAILED}` and `EXTRACTING → {EXTRACTED, FAILED}` — both present, unmodified, ready to use. **Decision:** `update_processing_status` calls `CompanyService.change_processing_status` for real (exactly `CompanyServiceCrawlGateway.update_processing_status`'s already-established pattern), translating `CompanyNotFoundError` → `CompanyNotFoundForExtractionError` at the adapter boundary (matching the exact translation `CompanyServiceCrawlGateway` performs — confirmed present in that file, and confirmed as something Task 006's evaluator specifically caught as missing before merge, so this contract calls it out explicitly rather than risk the same omission).

### 5. `extraction` ↔ `evidence` module boundary — a port, not a direct cross-module import, even though both are built in this task

The brief describes "Extraction" and "Evidence" as two modules (`backend/app/modules/extraction/**` and `backend/app/modules/evidence/**` are two separate allowed-path entries) with a tight coupling: every accepted `FactCandidate`/`FactRecord` must reference `evidence_ids`, and `EvidenceRecord.fact_field_path` links back. The brief never states whether extraction may import evidence's repository directly.

**Decision:** treat this exactly like every other cross-module dependency in the repository, even though both modules ship in the same task. `modules/extraction/domain/gateway.py` defines a narrow `EvidenceGateway` port (`create_evidence(draft: EvidenceDraft) -> EvidenceRecord`, `get_evidence(evidence_id) -> EvidenceRecord | None`, `list_evidence_for_fact(fact_id) -> list[EvidenceRecord]`). The real adapter, `modules/extraction/infrastructure/evidence_service_gateway.py`'s `EvidenceServiceExtractionGateway`, wraps `modules/evidence`'s own `EvidenceService` (never `EvidenceRepository`/`MongoEvidenceRepository` directly), obtained via `modules/evidence/api/router.py`'s own public `get_evidence_service` DI function — the identical "import the other module's own public application service + its DI function" shape `CompanyServiceCrawlGateway`/`CompanyServiceImportGateway` already established. This keeps `evidence` genuinely independent and independently queryable (its own API, its own repository, its own tests, buildable and testable in complete isolation from `extraction`), matches the brief's explicit "evidence must be first-class and independently queryable" (line 52) literally, and keeps the module boundary consistent with every other pair of modules in this repository rather than introducing the only direct cross-module-repository import in the codebase.

---

# Implementation Tasks

Grouped by area; task IDs are referenced by the Acceptance Criteria and Suggested Implementation Order below.

## Field-path catalogue (build first — nothing else can validate against it otherwise)

**T1 — `modules/extraction/domain/field_catalogue.py`**: `FieldPath` (a `StrEnum` with exactly the 52 dot-path values enumerated in brief section 3 — identity: 6, business: 8, catalogue: 7, operations: 7, technology: 12, organisation: 5, growth: 7 — never an arbitrary string field path anywhere else in the codebase, per the brief's explicit "do not use arbitrary string field paths throughout the code"); `FieldValueType` (`string`, `boolean`, `integer`, `float`, `enum`, `string_list`, `structured_entity`, `structured_entity_list`); `FieldCardinality` (`scalar`, `array`); `FieldDefinition` (field_path, value_type, cardinality, allowed_verification_states, merge_strategy, freshness_policy_days, minimum_accepted_confidence, sensitive: bool, description); `FIELD_CATALOGUE: dict[FieldPath, FieldDefinition]` — one entry per `FieldPath` member (validated at import time: every `FieldPath` member has exactly one `FieldDefinition`, no orphans in either direction); `FIELD_CATALOGUE_VERSION = "v1"`.

## Domain models

**T2 — `modules/extraction/domain/enums.py`**: `ExtractionStatus`, `FactStatus`, `FactSourceType`, `VerificationState` exactly as brief section 1 enumerates.

**T3 — `modules/extraction/domain/models.py`**: `ConfidenceScore` (a validated `int` type, 0–100 inclusive, via a Pydantic `Annotated`/`field_validator`, never a bare `int`), `FactValue` (typed wrapper: `value_type: FieldValueType`, `value: Any` — validated against the declared `value_type` at construction), `ExtractionSummary`, `ExtractionWarning`, `ExtractorDefinition`, `ExtractorExecution`, `FactCandidate`, `FactRecord`, `FactConflict`, `ExtractionRun` — every field exactly as brief section 1 lists, **plus** one documented addition mirroring Task 006's own T2 precedent: `ExtractionRun.idempotency_key: str` and `document_version: int = 1` on `ExtractionRun`/`ExtractorExecution`/`FactCandidate`/`FactRecord`/`FactConflict` (needed for T24's idempotent-retry requirement and optimistic-concurrency updates — nothing in the brief's literal field list otherwise supports either). `ExtractionRun.configuration_snapshot` explicitly documented to hold every version tag from brief section 27 (field catalogue, extractor implementations per-extractor, pattern rules, technology signatures, evidence format, confidence policy, reconciliation rules, freshness policy, projection schema). UTC-coercing `field_validator`s on every datetime field (duplicated locally, matching every prior module's own `_as_utc` precedent, not imported).

**T4 — `modules/evidence/domain/enums.py`**: `EvidenceType`, `EvidenceStatus`, `EvidenceStrength` exactly as brief section 2.

**T5 — `modules/evidence/domain/models.py`**: `EvidenceLocation`, `EvidenceExcerpt`, `EvidenceRecord` exactly as brief section 2's field lists; `EvidenceReference` (a small `{evidence_id, field_path}` cross-reference shape, used by `FactRecord.evidence_ids`/`FactCandidate.evidence_ids` conceptually — the brief lists it among evidence models without a literal field list, so this contract defines it minimally as `{evidence_id: str}` unless a caller needs more, since `evidence_ids` on facts/candidates are already plain `list[str]` per the brief's own `FactRecord`/`FactCandidate` field lists).

**T6 — Domain exceptions**: `modules/extraction/domain/exceptions.py` (`ExtractionDomainError` base; `CompanyNotFoundForExtractionError`, `CrawlRunNotFoundForExtractionError`, `ExtractionRunNotFoundError`, `FactNotFoundError`, `DuplicateActiveExtractionRunError`, `ExtractorExecutionError` [caught internally per-extractor, never propagated raw]); `modules/evidence/domain/exceptions.py` (`EvidenceDomainError` base; `EvidenceNotFoundError`, `EvidenceCreationFailedError` — the type `EvidenceGateway.create_evidence` raising causes fact acceptance to be blocked, per brief section 19's failure-isolation rule).

## Extractor protocol and ports

**T7 — `modules/extraction/domain/extractor.py`**: `PageContext` (exactly the brief's field list — `page_id`, `company_id`, `source_url`, `normalized_url`, `page_type: app.modules.discovery.domain.enums.PageType` [reused directly, pure-type precedent], `cleaned_html: str`, `extracted_text: str`, `page_metadata: dict` [a narrow, extraction-owned shape — deliberately **not** importing crawling's `PageMetadata` Pydantic model concretely, since that would pull a whole other module's record model into this module's domain layer; the `CrawlExtractionGateway`/application-service conversion step, not `domain/extractor.py`, is where crawling's `PageMetadata` is read and flattened into this plain `dict`], `raw_technology_signals: dict` [sourced from `CrawledPage.page_metadata.technology_signals`, confirmed present by inspection of `modules/crawling/domain/models.py`], `fetched_at: datetime`, `content_hashes: dict`); `FactCandidateDraft` (an extractor's raw output before IDs/evidence are assigned — field_path, value, normalized_value, value_type, source_type, confidence, verification_state, qualifiers, evidence draft(s)); `Extractor` (a `Protocol`, per the brief's explicit "pure extractor protocol": `definition -> ExtractorDefinition`, `supports(page_context) -> bool`, `extract(page_context) -> list[FactCandidateDraft]`). Documented discipline (enforced by every concrete extractor's own unit tests, T14–T20 below): never performs network I/O, never imports Motor/FastAPI, never mutates `page_context`, deterministic for identical input.

**T8 — `modules/extraction/domain/repository.py`**: `ExtractionRepository` (ABC) — the brief's exact method list (`create_run`, `update_run`, `save_extractor_execution`, `save_candidates`, `save_facts`, `save_conflicts`, `get_run`, `list_facts_by_company`, `list_candidates_by_run`, `get_latest_fact`, `mark_previous_facts_stale`) **plus one documented addition**, `find_active_or_completed_run(company_id, idempotency_key) -> ExtractionRun | None` — required to serve brief section 19's "idempotent retry: same crawl run and configuration does not duplicate accepted facts" (T3's test list, section 24), mirroring `CrawlRepository.find_active_run`'s exact justification from Task 006. Paginated variants (`FactPage`/`CandidatePage` `NamedTuple`s) for the two facts/candidates list endpoints' `page`/`pageSize` params.

**T9 — `modules/evidence/domain/repository.py`**: `EvidenceRepository` (ABC) — the brief's exact method list (`save_evidence`, `get_evidence`, `list_evidence_for_fact`, `list_evidence_for_page`, `update_evidence_status`), plus a paginated `list_evidence` variant (filters: `evidence_type`, `strength`, `status`, `page_id`, `fact_field_path`) for the `GET /api/evidence` list surface implied by the evidence-list query parameters in brief section 23 (the brief lists query params for an evidence list endpoint but the literal endpoint list in section 23 doesn't include a bare `GET /api/evidence` — documented as a **reported ambiguity**, resolved here: the evidence-list query parameters apply to `GET /api/facts/{fact_id}/evidence`, scoped to one fact, not a global evidence list; no unscoped `GET /api/evidence` route is built, matching the endpoint list literally).

**T10 — `modules/extraction/domain/gateway.py`**: `CompanyExtractionGateway` (ABC: `update_latest_extraction_run`, `update_processing_status`, `project_latest_facts` — see resolutions #2–#4), `CrawlExtractionGateway` (ABC: `get_crawl_run`, `list_pages`, `load_page_content` — see resolution #1), `EvidenceGateway` (ABC: `create_evidence`, `get_evidence`, `list_evidence_for_fact` — see resolution #5). All three ports in one file, matching `modules/crawling/domain/gateway.py`'s own "all ports live in one file" precedent.

## Evidence factory

**T11 — `modules/evidence/domain/evidence_factory.py`**: `EvidenceDraft` (pre-ID shape an extractor/candidate produces) → `create_evidence_record(draft, *, clock) -> EvidenceRecord`, pure and deterministic (an injectable `clock: Callable[[], datetime]`, defaulting to `datetime.now(UTC)`, matching every prior module's determinism-via-injection precedent). Responsibilities exactly per brief section 13: stable evidence IDs (deterministic hash of `page_id + field_path + selector/json_path + content_hash`, not a random UUID — "deterministic" is an explicit unit-test requirement, brief section 24), capture page reference, capture selector/JSON path when available, produce a concise excerpt capped at 300/120/120 chars (primary/prefix/suffix, brief section 13's "Recommended excerpt limits"), hash the relevant source fragment (reuses SHA-256, matching `modules/crawling/domain/hashing.py`'s existing choice — no new hash algorithm), mark evidence strength, preserve raw and normalized values, never store full page HTML, redact obvious email-tracking tokens and URL query parameters likely to contain personal data (a documented, versioned redaction pattern list — `EVIDENCE_FORMAT_VERSION = "v1"`), while explicitly preserving business contact details (email/phone) when *those* are the extracted fact (the brief's own explicit carve-out, section 13).

## Confidence policy

**T12 — `modules/extraction/domain/confidence_policy.py`**: `compute_confidence(inputs: ConfidenceInputs) -> ConfidenceScore` — pure, deterministic, versioned (`CONFIDENCE_POLICY_VERSION = "v1"`). `ConfidenceInputs` (source_authority, extractor_reliability, page_type_relevance, directness, agreeing_source_count, freshness_days, has_active_conflict, is_inference). Implements exactly the brief's suggested behavior (section 14): integer 0–100, clamped; a single authoritative source may exceed 85; two independent agreeing strong sources may exceed 90; inferred values capped below 75; active conflicts cap confidence; never accepts a model-generated confidence value (there is no model in this task at all — confirmed, no AI dependency anywhere in scope).

## Reconciliation engine

**T13 — `modules/extraction/domain/reconciliation.py`** + **`domain/reconciliation_rules.py`**: `MergeStrategy` enum (`scalar_preferred`, `scalar_conflict_preserving`, `boolean_positive_only`, `boolean_explicit`, `set_union`, `structured_entity_merge`, `numeric_exact_or_estimate`, `time_series` — exactly brief section 16's list, each `FieldDefinition` in T1 declares which strategy it uses); `reconcile_candidates(candidates: list[FactCandidate], *, field_definition, existing_fact, config) -> ReconciliationOutcome` (`accepted_fact: FactRecord | None`, `conflict: FactConflict | None`, `superseded_candidate_ids: list[str]`, `rule_ids: list[str]`) — pure, deterministic, versioned (`RECONCILIATION_RULES_VERSION = "v1"`), implementing exactly the rules in brief sections 16/17 per merge strategy (manual overrides automated; JSON-LD may override weak title inference; store-locator structured data may override footer counts; recent explicit evidence may override stale; conflicting strong sources remain conflicting — never resolved by first-seen order; array fields merge deduplicated; scalar fields select one or remain conflicting; boolean `false` requires explicit negative evidence; `unknown` emitted when nothing passes threshold). Acceptance thresholds per brief section 15 (authoritative exact: 70, contact info: 70, boolean capability: 65, technology: 70, catalogue estimates: 55, growth: 65, deterministic inferences: 50) live as `FieldDefinition.minimum_accepted_confidence` defaults in T1, configurable per-field, not hardcoded in the engine.

## Freshness policy

**T14 — `modules/extraction/domain/freshness_policy.py`**: `FreshnessPolicy` (a plain injectable Pydantic config, matching `CrawlConfig`'s own "never reads `os.environ`" pattern — brief section 18's suggested defaults as the model's own field defaults: identity 365d, platform 180d, contact 180d, business capabilities 180d, physical locations 180d, technology 90d, catalogue estimates 30d, growth 90d, careers 30d); `is_stale(field_path, last_verified_at, *, now) -> bool`; `apply_staleness_penalty(confidence, field_path, last_verified_at, *, now) -> ConfidenceScore` — pure, deterministic, `FRESHNESS_POLICY_VERSION = "v1"`. Stale facts/evidence are never deleted (status transitions to `stale`, still queryable) — enforced by `ExtractionRepository.mark_previous_facts_stale` (T8) at run-start, not by any delete path anywhere in either module.

## Extractors (built one family at a time, per the brief's own explicit "do not begin with every extractor at once" — section 28)

Each extractor family is a `domain/extractors/<family>/` package inside `modules/extraction`, one file per extractor (e.g. `domain/extractors/identity/company_name_extractor.py`), each declaring its own `EXTRACTOR_ID`/`EXTRACTOR_VERSION` constant and implementing the `Extractor` protocol (T7). Pattern definitions (brief section 12: `rule_id`, `version`, `field_path`, positive/negative patterns, context requirements, supported page types, base confidence, evidence strength, notes) are centralized per family in a `patterns.py` module, `PATTERN_RULES_VERSION` per family, avoiding broad substring matching / unbounded regex / unqualified navigation-label matches, per the brief's explicit "Avoid" list.

**T15 — Identity extractors** (`domain/extractors/identity/`): company name (7-step priority chain exactly as brief section 5 — Organisation JSON-LD → WebSite JSON-LD → OG `site_name` → title pattern → logo alt → about-page heading → domain fallback as low-confidence inference), trading name (`alternateName`, "trading as" patterns, footer legal text), country/city (PostalAddress JSON-LD → contact-page address blocks → store-location structured data → footer address → TLD/locale as low-confidence support only, never verified), language (`html lang` → content-language meta → no third-party language-detection library, "deterministic text-language marker only if already available locally" per the brief — i.e. never invents a new language-detection dependency). Conflicts preserved (never silently picks one), TLD never treated as verified country, city never inferred from phone area code, legal name and trading name kept as distinct `FactRecord`s (distinct `FieldPath`s).

**T16 — Business-model extractors** (`domain/extractors/business/`): wholesale, trade_accounts, click_and_collect, subscription, booking, online_only, custom_products, brands — each with its own positive-signal pattern list exactly per brief section 6. Boolean fields support `true`/`unknown` only from pattern matches; `false` requires explicit negative evidence or manual confirmation (never emitted from absence). `online_only` accepted **only** from explicit statements, never inferred from "no store page found." Source wording preserved on every candidate. Ambiguous keywords (e.g. bare "trade") require surrounding context per the pattern's `context_requirements`, not matched as a bare substring.

**T17 — Catalogue extractors** (`domain/extractors/catalogue/`): product_count (5-step priority exactly as brief section 7 — exact sitemap count → exact platform-provided total → pagination-derived estimate → sampled-collection estimate → unknown), collection_count, sku_count_estimate (exact local data, or product-count × observed median variants **only with sufficient sample size** — configurable minimum sample threshold, otherwise `unknown`), variant_evidence, bundle_evidence, customization_evidence. Every estimate records its estimation method and sample size on the `FactCandidate.qualifiers`; never extrapolates from one product without an explicit low-confidence marker; collection URLs never counted as products (page-type-scoped extraction, not URL-pattern guessing).

**T18 — Physical-operations extractors** (`domain/extractors/operations/`): retail_store_count, showroom_count, warehouse_count, office_count, pickup_available, returns_location_count, locations (structured `LocationCandidate`: location_type, name, address_line, suburb, city, region, postal_code, country, phone, latitude, longitude [never geocoded — only if already present in source data], source wording). Sources: `LocalBusiness`/`Store` JSON-LD, store-locator/contact/footer/shipping-returns pages, explicit warehouse/showroom wording. Deduplication by normalized address+name (never counts the same address twice across footer and contact page); stockists distinguished from company-owned stores; warehouse distinguished from retail store; uncertain ownership preserved, not resolved to a guess.

**T19 — Technology-signal extractors** (`domain/extractors/technology/`, consuming `PageContext.raw_technology_signals` + pattern-matching over `cleaned_html` for markers not already surfaced by crawling — e.g. specific script-src hosts, generator meta, cookie names, known widget element IDs/classes): every product family exactly as brief section 9 (commerce/payments/CRM-marketing/ERP-accounting/reviews/support/analytics/loyalty/frameworks), each technology backed by one or more versioned rule IDs (`TECHNOLOGY_SIGNATURES_VERSION`), confidence dependent on signal quality, agreement across pages raising confidence (handled in reconciliation, T13, not per-page), generic CDN usage never proving a product, framework detection never treated as an internal-technology capability signal, absence of a signature never converted into a negative fact (`unknown`, never `false`).

**T20 — Organisation/contact extractors** (`domain/extractors/organisation/`): emails (mailto, visible text, structured data, contact/footer pages — normalized with original preserved), phones (tel links, structured data, visible text — same normalize-preserve-original rule), people (`PersonCandidate`: name, role_title, role_category [`owner`/`founder`/`executive`/`operations`/`ecommerce`/`marketing`/`technology`/`customer_service`/`sales`/`unknown` — exactly brief section 10's list], email, phone, source_url, confidence — explicitly-named people with role context only, from team/about/contact/structured-data/careers-leadership sources), internal_it_status (`detected`/`not_detected`/`unknown` — `detected` requires explicit technical-staff/leadership/engineering-careers/internal-dev wording; `not_detected` never inferred from absence; `unknown` is the default; agency credits support external-maintenance evidence but never prove `not_detected`), recommended_contact_candidates (priority-ordered candidates only — ecommerce leadership → operations leadership → owner/founder [small business] → technology leadership → marketing leadership → general contact — never a single final recommendation, per the brief's explicit "candidates only" + "Do not use AI to choose the final contact").

**T21 — Growth-signal extractors** (`domain/extractors/growth/`): `GrowthSignal` (signal_type, statement, event_date, publication_date, effective_date, status, source_url, confidence), the 10 signal types from brief section 11 (hiring, new store, warehouse move, expansion, platform migration, subscription launch, new category, international expansion, acquisition/merger, rebrand). Publication date explicitly distinguished from event date; old announcements marked `stale` per T14's freshness policy (careers/growth-specific windows); routine job vacancies never treated as major expansion without explicit supporting context (a documented, pattern-tested false-positive-prevention rule); original statement preserved verbatim as the evidence excerpt (T11).

## Application service

**T22 — `modules/extraction/application/structured_extraction_service.py`**: `StructuredExtractionService`, constructed from `CompanyExtractionGateway`, `CrawlExtractionGateway`, `EvidenceGateway`, `ExtractionRepository`, a registered list of `Extractor` instances (T15–T21), `ConfidenceScore`/reconciliation/freshness policy objects (T12–T14), and `FIELD_CATALOGUE` (T1). `start_extraction_run(company_id, crawl_run_id, options) -> ExtractionRun` implements exactly brief section 19's responsibility list: validates company (`CompanyExtractionGateway` — realized via `get_company`, per resolution #4's real adapter) and crawl run (`CrawlExtractionGateway.get_crawl_run`) exist; computes an idempotency key (`company_id | crawl_run_id | sha256(sorted(extractorIds, pageTypes), forceRefresh)`, mirroring Task 006's own idempotency-key construction exactly, including its documented `frozenset`-ordering-determinism fix) and returns/conflicts on an already-active run (`DuplicateActiveExtractionRunError`, matching `DuplicateActiveCrawlRunError`'s established 409 precedent); creates the run (`queued → running`); advances company status to `EXTRACTING` (best-effort — catches and logs `InvalidStatusTransitionError`, same swallow pattern `WebsiteCrawlService`/`WebsiteDiscoveryService` already use); retrieves eligible pages (`CrawlExtractionGateway.list_pages`, filtered to the eligibility set in resolution #1); for each page, builds `PageContext` (T7) via `load_page_content` for `"cleaned"`/`"text"`/`"raw"` as each registered extractor's `supports(page_context)` requires; runs each applicable extractor, **catching and isolating per-extractor failures** (one extractor's exception → `ExtractorExecution.status = failed` + a structured warning, other extractors for that page still run — brief section 19's explicit failure-isolation rule); persists `ExtractorExecution` records (`ExtractionRepository.save_extractor_execution`); creates `FactCandidate`s from each successful extractor's `FactCandidateDraft`s and, for each, creates evidence (`EvidenceGateway.create_evidence`) — **evidence-creation failure for a would-be-accepted candidate prevents that candidate from being accepted** (brief's explicit rule, tested at AC-32); reconciles candidates per field_path/company (T13), applying T14's freshness penalty; persists accepted `FactRecord`s and `FactConflict`s; marks previous facts for this company+field_path stale where superseded (`ExtractionRepository.mark_previous_facts_stale`); builds the `CompanyFactsProjection` (T23) and calls `CompanyExtractionGateway.project_latest_facts` (no-op per resolution #3, called anyway so the wiring is correct once the follow-up lands — same "call the no-op anyway" discipline Task 006 established); accumulates `ExtractionSummary`; on completion sets `ExtractionStatus` (`completed`/`completed_with_warnings`/`partial`/`failed`) and advances company status to `EXTRACTED`/`FAILED` (best-effort); calls `update_latest_extraction_run` (no-op per resolution #2, called anyway). `cancel_run(extraction_run_id)` stops scheduling new page/extractor work but preserves already-persisted facts/candidates/evidence — never deletes them (mirrors `WebsiteCrawlService.cancel_run` exactly). A repository failure (not a page/extractor failure) is allowed to fail the whole run, per the brief's explicit "repository failure may fail the run" (section 19) — same as Task 006's identical rule for `WebsiteCrawlService`.

**Idempotent retry, made concrete (brief section 19 + test list, section 24):** re-running `start_extraction_run` with the identical `(company_id, crawl_run_id, options)` combination while a prior run for that key is already `completed`/`completed_with_warnings`/`partial` does **not** duplicate accepted `FactRecord`s — `ExtractionRepository.save_facts` upserts by `(company_id, field_path)` (documented persistence decision, T25), and the reconciliation engine, given identical input candidates, is required to be deterministic (T13) so re-running produces the same accepted values, not new duplicate rows.

## Company projection

**T23 — `modules/extraction/domain/company_projection.py`**: `ProjectedField` (`value`, `verification_state`, `confidence`, `evidence_ids`, `last_verified_at` — exactly brief section 21's per-field shape), `CompanyFactsProjection` (identity/business/catalogue/operations/technology/organisation/growth groups + an `extraction_quality` summary group — brief section 21's category list), `build_projection(facts: list[FactRecord]) -> CompanyFactsProjection` — pure, built entirely inside this module, never writing to any Company-owned collection directly (per the brief's explicit "do not modify the Company module in this worktree" and "do not flatten evidence away" — every `ProjectedField` retains its `evidence_ids`, never collapses to a bare value). `PROJECTION_SCHEMA_VERSION = "v1"`.

## Persistence

**T24 — `modules/extraction/infrastructure/mongo_extraction_repository.py`**: `MongoExtractionRepository(ExtractionRepository)`, five collections (`extraction_runs`, `extractor_executions`, `fact_candidates`, `facts`, `fact_conflicts`), `ensure_indexes()` creating exactly brief section 22's listed indexes **plus one documented addition**: a unique compound index on `facts` over `(company_id, field_path)` for accepted (non-superseded) facts — needed to make `save_facts` an upsert-per-field-path, which is how the idempotent-retry requirement (T22) is concretely satisfied, mirroring `MongoCrawlRepository`'s own documented `(crawl_run_id, normalized_url)` addition on `pages` in Task 006. `update_run` uses optimistic-concurrency on `document_version` (match-and-increment; stale write rejected), same as `MongoCrawlRepository.update_run`. No raw page HTML is ever stored in any of these five collections (brief's explicit prohibition, section 22) — only `FactValue`/candidate metadata/`evidence_ids` references.

**T25 — `modules/evidence/infrastructure/mongo_evidence_repository.py`**: `MongoEvidenceRepository(EvidenceRepository)`, one collection (`evidence`), `ensure_indexes()` creating exactly brief section 22's listed indexes. Evidence records are immutable except `status`/verification metadata (brief section 2's explicit requirement) — enforced by `update_evidence_status` being the *only* mutating method on the repository interface; every other change creates a new evidence record rather than rewriting history (brief: "changes should create new evidence rather than rewriting historical evidence").

## Cross-module integration ports and adapters

**T26 — `modules/extraction/infrastructure/company_service_gateway.py`**: `CompanyServiceExtractionGateway(CompanyExtractionGateway)` — per resolutions #2–#4.

**T27 — `modules/extraction/infrastructure/crawl_repository_gateway.py`**: `CrawlRepositoryExtractionGateway(CrawlExtractionGateway)` — per resolution #1.

**T28 — `modules/extraction/infrastructure/evidence_service_gateway.py`**: `EvidenceServiceExtractionGateway(EvidenceGateway)` — per resolution #5, wrapping `modules/evidence`'s `EvidenceService` via that module's own public `get_evidence_service` DI function.

## API schemas and routers

**T29 — `modules/extraction/api/schemas.py`** + **`modules/evidence/api/schemas.py`**: camelCase DTOs (local `CamelCaseModel` base with `alias_generator=to_camel`, matching `modules/crawling/api/schemas.py`'s exact precedent — duplicated per existing convention, not cross-imported) for every response shape in brief section 23, including the exact `POST .../extraction-runs` request/response example given verbatim in the brief. Fact/evidence responses distinguish `unknown` from `false` (never coalesce a missing boolean to `false`), distinguish exact values from estimates (surfacing estimation method/sample size where present), preserve conflicts (a `FactRecord` with `status="conflicting"` surfaces its `conflicting_candidate_ids`, not a silently-picked value), expose extractor/rule/policy version fields, and never include full page HTML (evidence responses only ever carry the capped excerpt from T11, never a raw HTML blob).

**T30 — `modules/extraction/api/router.py`** + **`modules/evidence/api/router.py`** (neither registered in `main.py` — required follow-up): the nine endpoints listed under "Affected APIs," each thin (validates via Pydantic, calls exactly one service/repository method, translates domain exceptions to HTTP status: `*NotFoundFor*Error`/`FactNotFoundError`/`EvidenceNotFoundError` → 404, `DuplicateActiveExtractionRunError` → 409). Fact-list and evidence-list query parameters exactly as brief section 23 specifies. `POST .../extraction-runs` runs `StructuredExtractionService.start_extraction_run` synchronously inline — **no `BackgroundTasks`**, per the brief's explicit instruction (section 23) and matching every prior module's identical constraint.

## Fixtures

**T31 — `fixtures/extraction/`**: every file brief section 26 lists (28 files — homepage variants for Shopify/WooCommerce/Magento/custom/JSON-LD-organisation/conflicting-name; about-company, about-team; contact-address, contact-multiple-locations; wholesale-explicit, wholesale-false-positive, trade-account, click-and-collect, subscription, online-only-explicit; store-locator-owned, store-locator-stockists, warehouse-and-showroom; collection-pagination, product-variants, product-customization; careers-technology, careers-general, news-new-store, news-old-expansion; technology-signatures, technology-conflicting-platforms; structured-data-malformed) — all hand-authored/sanitized, no real third-party content, mirroring `fixtures/crawling/`'s and `fixtures/discovery/`'s own sanitized-fixture convention.

---

# Acceptance Criteria

**AC-01 — Field catalogue is complete and internally consistent**
Given the brief's section-3 field list (52 field paths across 7 groups)
When `FIELD_CATALOGUE` is loaded
Then every listed `FieldPath` has exactly one `FieldDefinition`, every `FieldDefinition` declares a value type, cardinality, merge strategy, freshness policy, minimum accepted confidence, and description, and no two `FieldDefinition`s share a field path
Verification: `pytest backend/tests/unit/extraction/test_field_catalogue.py::test_catalogue_completeness`

**AC-02 — Field paths are never arbitrary strings**
Given the codebase's extractors, reconciliation engine, and API schemas
When searched for any hardcoded field-path string not sourced from `FieldPath`
Then none exists (`FactCandidate.field_path`/`FactRecord.field_path` are typed as `FieldPath`, not `str`, everywhere)
Verification: `pytest backend/tests/unit/extraction/test_field_catalogue.py::test_field_path_is_typed_everywhere` (a static-shape assertion over model field annotations)

**AC-03 — Extractors are deterministic and side-effect-free**
Given any single extractor and a fixed `PageContext`
When `extract(page_context)` is called twice
Then both calls return identical `FactCandidateDraft` lists (byte-for-byte, including ordering), and `page_context` is unchanged after each call
Verification: one `test_deterministic_output`/`test_input_not_mutated` case per extractor test file under `backend/tests/unit/extraction/extractors/`

**AC-04 — Company name priority chain resolves correctly**
Given `homepage-jsonld-organisation.html` (Organisation JSON-LD present) and, separately, `homepage-custom.html` (no JSON-LD, only a `<title>` pattern)
When the company-name extractor runs on each
Then the first returns a high-confidence candidate sourced from Organisation JSON-LD, the second returns a lower-confidence candidate sourced from the title pattern, and each candidate's `source_type` correctly identifies which signal was used
Verification: `pytest backend/tests/unit/extraction/extractors/test_identity_extractors.py::test_company_name_priority_chain`

**AC-05 — TLD is never treated as verified country; conflicting cities are preserved**
Given `contact-multiple-locations.html` with two different cities implied by structured data vs. footer text
When the country/city extractor runs
Then both candidates are produced (not silently deduplicated to one), and a TLD-only signal never produces `verification_state="verified"` (at most `inferred`, per brief section 5)
Verification: `pytest backend/tests/unit/extraction/extractors/test_identity_extractors.py::test_conflicting_city_preserved` and `::test_tld_never_verified`

**AC-06 — Wholesale/trade positive signals require context; generic word occurrence is rejected**
Given `wholesale-explicit.html` (an explicit wholesale application page) and `wholesale-false-positive.html` (the bare word "trade" in an unrelated navigation label)
When the business-model extractors run on each
Then the first produces a `business.wholesale` candidate with `verification_state` above the acceptance threshold, and the second produces **no** candidate for `business.wholesale`/`business.trade_accounts`
Verification: `pytest backend/tests/unit/extraction/extractors/test_business_extractors.py::test_wholesale_positive` and `::test_wholesale_false_positive_rejected`

**AC-07 — `online_only` is never inferred from absence**
Given a fixture with no store-locator page present anywhere in the crawl, and no explicit online-only statement
When the business-model extractor runs
Then **no** `business.online_only` candidate is produced (remains `unknown` at reconciliation, not `false`, not `true`)
Verification: `pytest backend/tests/unit/extraction/extractors/test_business_extractors.py::test_no_online_only_inference_from_absence`

**AC-08 — Catalogue product-count priority and insufficient-sample handling**
Given a discovery sitemap summary classifying an exact product-URL count, and, separately, only a single sampled product page with no other supporting data
When the catalogue extractor runs on each
Then the first produces an exact-value candidate (`qualifiers` marks it `exact`, not `estimate`), and the second produces **no** `catalogue.sku_count_estimate` candidate (remains `unknown` — insufficient sample, per brief section 7's explicit rule)
Verification: `pytest backend/tests/unit/extraction/extractors/test_catalogue_extractors.py::test_exact_sitemap_count_priority` and `::test_insufficient_sample_remains_unknown`

**AC-09 — Physical locations are deduplicated and stockists distinguished from owned stores**
Given `store-locator-owned.html` and `store-locator-stockists.html`, and a fixture where the same address appears in both `footer` and a `contact` page
When the operations extractor runs
Then owned stores and stockists are tagged with distinguishable `location_type`/ownership qualifiers (never merged into one undifferentiated count), and the duplicate footer/contact address produces exactly one `LocationCandidate`, not two
Verification: `pytest backend/tests/unit/extraction/extractors/test_operations_extractors.py::test_stockist_not_counted_as_owned` and `::test_duplicate_address_deduplicated`

**AC-10 — Technology signature detection is rule-ID-backed and absence-safe**
Given `technology-signatures.html` (multiple known platform/payment/analytics markers) and a page with only generic CDN usage (no product-specific signature)
When the technology extractor runs
Then every detected technology candidate carries one or more `rule_ids` and the versioned `TECHNOLOGY_SIGNATURES_VERSION`, the generic-CDN-only page produces no false-positive commerce-platform candidate, and a page with **no** signature for a given technology produces no candidate for it at all (never a `false`/negative fact)
Verification: `pytest backend/tests/unit/extraction/extractors/test_technology_extractors.py::test_signature_detection_rule_ids` and `::test_generic_cdn_no_false_positive` and `::test_absence_remains_unknown`

**AC-11 — Internal IT status is never inferred from absence**
Given a fixture with no explicit technical-staff/engineering wording anywhere
When the organisation extractor runs
Then `organisation.internal_it_status` is not asserted as `not_detected` by any candidate — either no candidate is produced, or a candidate explicitly carrying `unknown` is produced, per brief section 10's explicit rule
Verification: `pytest backend/tests/unit/extraction/extractors/test_organisation_extractors.py::test_no_internal_it_inference_from_absence`

**AC-12 — Recommended contact candidates are ordered, never a single final choice**
Given `about-team.html` with an ecommerce-leadership person and an owner/founder both present
When the organisation extractor runs
Then `recommended_contact_candidates` returns an ordered list (ecommerce leadership ranked ahead of owner/founder, per brief section 10's priority list) with **more than one** candidate, never a single resolved "the contact"
Verification: `pytest backend/tests/unit/extraction/extractors/test_organisation_extractors.py::test_recommended_contact_ordering`

**AC-13 — Growth signals distinguish publication date from event date and mark stale announcements**
Given `news-new-store.html` (recent) and `news-old-expansion.html` (an announcement older than the growth freshness window)
When the growth extractor + freshness policy run on each
Then both candidates carry distinct `publication_date`/`event_date` fields where the fixture provides both, and the old announcement's resulting fact is marked `stale` (`verification_state="stale"`), not treated as current
Verification: `pytest backend/tests/unit/extraction/extractors/test_growth_extractors.py::test_publication_vs_event_date` and `pytest backend/tests/unit/extraction/test_freshness_policy.py::test_old_announcement_marked_stale`

**AC-14 — Routine job vacancies are not treated as major expansion**
Given `careers-general.html` (a single generic job posting, no expansion context)
When the growth extractor runs
Then no `growth.hiring`-as-expansion-signal candidate above the acceptance threshold is produced without supporting context, per brief section 11's explicit false-positive-prevention requirement
Verification: `pytest backend/tests/unit/extraction/extractors/test_growth_extractors.py::test_routine_vacancy_not_treated_as_expansion`

**AC-15 — Pattern rules have false-positive test coverage**
Given every centralized pattern list (T15–T21's `patterns.py` files)
When each pattern's test suite is inspected
Then every `rule_id` has at least one positive-match test and at least one false-positive-prevention test, per the brief's explicit "All patterns require tests for false positives" (section 12)
Verification: a coverage assertion in `backend/tests/unit/extraction/test_pattern_coverage.py` cross-checking every `rule_id` defined against the test files that reference it

**AC-16 — Evidence IDs are deterministic, not random**
Given the same `EvidenceDraft` (identical page_id, field_path, selector, content) supplied twice
When `create_evidence_record` is called twice
Then both calls produce the identical `evidence_id`
Verification: `pytest backend/tests/unit/evidence/test_evidence_factory.py::test_deterministic_evidence_id`

**AC-17 — Excerpt caps and prefix/suffix context are enforced**
Given source text exceeding 300/120/120 characters (primary/prefix/suffix)
When `create_evidence_record` builds the excerpt
Then the primary excerpt is capped at exactly 300 characters with `truncated=True` recorded, and prefix/suffix are each capped at 120 characters
Verification: `pytest backend/tests/unit/evidence/test_evidence_factory.py::test_excerpt_length_caps`

**AC-18 — No full HTML ever appears in evidence**
Given any evidence record produced by any extractor's evidence drafts across every fixture
When `EvidenceRecord.excerpt`/`raw_value` are inspected
Then neither ever contains a full `<html>`/`<body>` document or an unbounded HTML fragment — only the capped excerpt
Verification: `pytest backend/tests/unit/evidence/test_evidence_factory.py::test_no_full_html_stored` (asserts excerpt length ≤ cap for every fixture-derived evidence record)

**AC-19 — URL query parameters likely to contain personal data are redacted; business contact details are preserved**
Given a source URL containing an email-tracking token in its query string, and, separately, a fact whose extracted value *is* a business email/phone (the contact itself)
When evidence is created for each
Then the first redacts the tracking-token query parameter from any stored URL, and the second preserves the business email/phone verbatim (brief section 13's explicit carve-out)
Verification: `pytest backend/tests/unit/evidence/test_evidence_factory.py::test_url_query_redaction` and `::test_business_contact_preserved`

**AC-20 — Evidence is immutable except status**
Given a persisted `EvidenceRecord`
When any field other than `status`/verification metadata is attempted to change
Then no repository method exists to perform that mutation (`EvidenceRepository`'s only mutating method is `update_evidence_status`) — a genuine content change creates a **new** evidence record instead
Verification: `pytest backend/tests/unit/evidence/test_evidence_factory.py::test_immutability_by_construction` (interface-shape assertion) and `pytest backend/tests/integration/evidence/test_evidence_service.py::test_content_change_creates_new_evidence_not_rewrite`

**AC-21 — Confidence is clamped, deterministic, and penalized correctly**
Given confidence inputs producing a raw score above 100 or below 0, and, separately, identical inputs supplied twice, and, separately, inputs with `has_active_conflict=True` vs `False`
When `compute_confidence` runs on each
Then the result is always clamped to [0, 100], identical inputs always produce identical output, and the conflicting-input case yields a strictly lower score than the otherwise-identical non-conflicting case
Verification: `pytest backend/tests/unit/extraction/test_confidence_policy.py` (one test per case: clamping, determinism, conflict penalty, freshness penalty, inference cap, agreement boost)

**AC-22 — Agreeing scalar candidates merge; conflicting strong scalars remain conflicting**
Given two independent, strong-source candidates agreeing on the same `identity.company_name` value, and, separately, two independent strong-source candidates with materially different values for the same field
When `reconcile_candidates` runs on each
Then the first produces a single accepted `FactRecord` with `source_count >= 2`, and the second produces a `FactRecord` with `status="conflicting"` plus a `FactConflict` referencing both candidate IDs — never silently resolved to whichever candidate appeared first
Verification: `pytest backend/tests/unit/extraction/test_reconciliation.py::test_agreeing_scalars_merge` and `::test_conflicting_strong_scalars_preserved`

**AC-23 — Manual and JSON-LD overrides behave correctly**
Given a manual-verified candidate and a weak automated candidate for the same field, and, separately, a JSON-LD candidate and a weak title-inference candidate for `identity.company_name`
When reconciliation runs on each
Then the manual value is selected regardless of the automated candidate's confidence, and the JSON-LD candidate is preferred over the title inference
Verification: `pytest backend/tests/unit/extraction/test_reconciliation.py::test_manual_override` and `::test_jsonld_beats_title`

**AC-24 — Exact counts beat estimates; competing exact counts conflict**
Given an exact sitemap-derived product count and a pagination-derived estimate for the same company, and, separately, two exact-but-materially-different counts from two independent sources
When reconciliation runs on each
Then the exact value is selected over the estimate, and the two competing exact counts remain `conflicting` (not averaged, not first-wins)
Verification: `pytest backend/tests/unit/extraction/test_reconciliation.py::test_exact_beats_estimate` and `::test_competing_exact_counts_conflict`

**AC-25 — Technology arrays set-union with per-item confidence and evidence preserved**
Given candidates for `technology.commerce_platform` from three different pages, two agreeing on Shopify and one detecting HubSpot
When reconciliation runs
Then the resulting `FactRecord.normalized_value` contains both technologies (set union, deduplicated by normalized product name), each retaining its own per-item confidence and its own `evidence_ids` — not a single flattened confidence for the whole array
Verification: `pytest backend/tests/unit/extraction/test_reconciliation.py::test_technology_set_union_per_item_confidence`

**AC-26 — Unknown is emitted below threshold; boolean false requires explicit negative evidence**
Given only below-threshold candidates for a field, and, separately, no candidate at all suggesting `business.wholesale=false`
When reconciliation runs
Then no `FactRecord` with an accepted value is produced for the first case (the field remains absent/`unknown`, never defaulted to a guessed value), and no reconciliation path ever produces `false` for `business.wholesale` without an explicit negative-evidence candidate present
Verification: `pytest backend/tests/unit/extraction/test_reconciliation.py::test_unknown_when_below_threshold` and `::test_boolean_false_requires_explicit_evidence`

**AC-27 — Extraction rule IDs and evidence references are preserved on every accepted fact**
Given any accepted `FactRecord` produced by reconciliation across the fixture set
When inspected
Then `reconciliation_rule_ids` is non-empty and every ID in `evidence_ids` corresponds to a real, persisted `EvidenceRecord`
Verification: `pytest backend/tests/integration/extraction/test_structured_extraction_service.py::test_every_accepted_fact_has_evidence_and_rule_ids`

**AC-28 — One extractor's failure does not fail other extractors on the same page or the run**
Given a page where one registered extractor raises an unexpected exception
When the extraction run processes that page
Then the failing extractor's `ExtractorExecution.status="failed"` with a structured warning, every other applicable extractor for that page still runs and produces candidates, and the run does not fail outright because of it
Verification: `pytest backend/tests/integration/extraction/test_structured_extraction_service.py::test_one_extractor_failure_isolated`

**AC-29 — One unavailable/failed page does not fail the run**
Given a crawl run containing a mix of `fetched` and `failed`/`blocked_by_robots` pages
When extraction runs
Then only the eligible pages are processed, the ineligible ones produce a warning (not an error), and the run still completes (`completed`/`completed_with_warnings`)
Verification: `pytest backend/tests/integration/extraction/test_structured_extraction_service.py::test_unavailable_page_skipped_with_warning`

**AC-30 — Evidence-persistence failure blocks fact acceptance**
Given a `FakeEvidenceGateway` configured to fail `create_evidence` for one specific candidate
When that candidate would otherwise be accepted
Then no `FactRecord` is produced for that candidate (it is not silently accepted without evidence), and the run continues processing other candidates/pages
Verification: `pytest backend/tests/integration/extraction/test_structured_extraction_service.py::test_evidence_failure_blocks_fact_acceptance`

**AC-31 — `unchanged` pages still yield extractable content via the previous page's stored content**
Given a crawl run with a page whose `fetch_status="unchanged"` and `unchanged_from_page_id` pointing at an earlier, fully-content-populated page
When `CrawlRepositoryExtractionGateway.load_page_content` is called for the unchanged page's `page_id`
Then it returns the referenced predecessor page's content (not `None`), and the extraction run produces candidates for that page as if it had been freshly fetched
Verification: `pytest backend/tests/unit/extraction/test_crawl_repository_gateway.py::test_unchanged_page_resolves_via_predecessor` and `pytest backend/tests/integration/extraction/test_structured_extraction_service.py::test_unchanged_page_still_extracted`

**AC-32 — `CompanyExtractionGateway.update_processing_status` is real; the two no-ops are documented and still invoked**
Given a successful extraction run and, separately, a failed one
When each completes
Then `CompanyExtractionGateway.update_processing_status` was called with `EXTRACTING` at start and `EXTRACTED`/`FAILED` at the end respectively (asserted against a `FakeCompanyExtractionGateway`'s recorded calls), and `update_latest_extraction_run`/`project_latest_facts` were also called (even though the real adapter's implementation is a no-op) so the wiring is provably correct once the two required follow-ups land
Verification: `pytest backend/tests/integration/extraction/test_structured_extraction_service.py::test_company_status_advances` and `::test_noop_gateways_still_invoked`

**AC-33 — Cancellation preserves completed work**
Given a run cancelled after some pages have completed
When `cancel_run` is called
Then no further pages are processed, and already-persisted facts/candidates/evidence for the completed pages remain untouched
Verification: `pytest backend/tests/integration/extraction/test_structured_extraction_service.py::test_cancellation_preserves_completed_work`

**AC-34 — Idempotent retry does not duplicate accepted facts**
Given a completed extraction run for `(company_id, crawl_run_id, options)`
When `start_extraction_run` is called again with the identical combination against unchanged crawl content
Then the same accepted `FactRecord`s result (no duplicate rows for the same `(company_id, field_path)` — verified via `ExtractionRepository.list_facts_by_company` returning the same count before and after)
Verification: `pytest backend/tests/integration/extraction/test_structured_extraction_service.py::test_idempotent_retry_no_duplicate_facts`

**AC-35 — Re-extraction marks previous facts stale when superseded**
Given an existing accepted fact for a field, and a new extraction run producing a materially different, higher-confidence candidate for the same field
When the new run completes
Then the previous `FactRecord`'s `status` becomes `superseded`/`stale` (not deleted — still queryable), and the new value becomes the current accepted fact
Verification: `pytest backend/tests/integration/extraction/test_structured_extraction_service.py::test_supersession_marks_previous_fact_stale`

**AC-36 — Company projection preserves evidence, never flattens it away**
Given a set of accepted facts spanning multiple field-path groups
When `build_projection` runs
Then every `ProjectedField` in the resulting `CompanyFactsProjection` carries its own `value`, `verification_state`, `confidence`, non-empty `evidence_ids`, and `last_verified_at` — never a bare value with evidence discarded
Verification: `pytest backend/tests/unit/extraction/test_company_projection.py::test_projection_preserves_evidence`

**AC-37 — Real MongoDB repository behavior**
Given real (test-database) `MongoExtractionRepository` and `MongoEvidenceRepository` instances
When runs/candidates/facts/conflicts/evidence are created, then a fact is updated with a stale `document_version`
Then the stale update is rejected, `ensure_indexes()` produces every specified index including the unique `(company_id, field_path)` addition on `facts`, and a repeated `save_facts` call for the same `(company_id, field_path)` upserts rather than inserting a duplicate
Verification: `pytest backend/tests/integration/extraction/test_mongo_extraction_repository.py` and `pytest backend/tests/integration/evidence/test_mongo_evidence_repository.py`

**AC-38 — API responses are camelCase, unregistered, and never leak full HTML**
Given a completed extraction run
When `GET /api/companies/{id}/facts` and `GET /api/facts/{id}/evidence` are called against a locally-scoped `FastAPI()` app containing only this task's routers (never `app.main.app`, since these routers are not registered there)
Then every JSON key is camelCase, no response body contains a full HTML document, evidence excerpts are capped, `unknown` and `false` are never conflated for boolean fields, and estimate metadata (method/sample size) is present where applicable
Verification: `pytest backend/tests/integration/extraction/test_api_schema_serialization.py` and `pytest backend/tests/integration/evidence/test_api_schema_serialization.py`

**AC-39 — Fact-list and evidence-list filters work**
Given a company with facts/evidence spanning multiple statuses, verification states, and confidence levels
When `GET /api/companies/{id}/facts` is called with `fieldPath`/`status`/`verificationState`/`minimumConfidence`/`includeStale`/`includeConflicting`, and `GET /api/facts/{id}/evidence` with `evidenceType`/`strength`/`status`/`pageId`/`fieldPath`
Then only matching records are returned for each filter, individually and combined
Verification: `pytest backend/tests/integration/extraction/test_api_schema_serialization.py::test_fact_list_filters` and `::test_evidence_list_filters`

**AC-40 — Extraction and evidence module versions are all recorded on every run**
Given a completed `ExtractionRun`
When `configuration_snapshot` is inspected
Then it includes the field-catalogue version, every executed extractor's own version, the pattern-rules version(s), technology-signatures version, evidence-format version, confidence-policy version, reconciliation-rules version, freshness-policy version, and projection-schema version — per brief section 27's "every extraction run must store all relevant versions"
Verification: `pytest backend/tests/integration/extraction/test_structured_extraction_service.py::test_run_records_all_versions`

---

# Required Tests

**Unit tests** (`backend/tests/unit/extraction/`, `backend/tests/unit/evidence/`, no MongoDB, no network): field catalogue (AC-01, AC-02); one test file per extractor family under `extractors/` covering every case brief section 24 lists for that family (identity, business, catalogue, operations, technology, organisation, growth — AC-04 through AC-15); evidence factory (AC-16 through AC-20); confidence policy (AC-21); reconciliation engine (AC-22 through AC-27); freshness policy; company projection (AC-36); the `CrawlRepositoryExtractionGateway`'s unchanged-page-resolution logic tested in isolation against a fake `CrawlRepository`/`ContentStorage` pair (AC-31's unit half); API schema shape tests.

**Integration tests** (`backend/tests/integration/extraction/`, `backend/tests/integration/evidence/`): `StructuredExtractionService` against fakes for every port (`FakeCompanyExtractionGateway`, `FakeCrawlExtractionGateway`, `FakeEvidenceGateway`, `FakeExtractionRepository`) — covering every scenario in brief section 24's "Application tests with fakes" list, formalized as AC-28 through AC-35, AC-40. `EvidenceService` against a `FakeEvidenceRepository` (AC-20's integration half). Full-pipeline integration tests using the `fixtures/extraction/` fixtures (homepage/about/contact/wholesale/store-locator/product pages) exercising real extractors end-to-end through a fake-gateway-backed service, per brief section 25 ("full extraction from homepage, about, contact, wholesale, store locator, and product pages," "evidence linked to facts," "conflicts persisted," "stale prior facts," "company projection generated," "retry without duplicate facts," "changed page content creates new evidence and supersedes old fact," "unchanged page content does not duplicate evidence unnecessarily") — no live websites, matching the brief's explicit constraint. Real-MongoDB repository tests (AC-37), built without any edit to the shared root `backend/tests/conftest.py` (inherited fixtures only, a new local `conftest.py` per module).

**API tests**: covered within each module's `test_api_schema_serialization.py` (AC-38, AC-39).

**Browser tests**: not applicable — no frontend work is in scope (explicit brief constraint).

**Manual verification**: not required to complete this task — no real MongoDB/network dependency is load-bearing for any automated test (the real-MongoDB tests use the existing dedicated test database; extractors and the application service operate entirely on fixture-derived `PageContext`s and fakes, never live HTTP). Recommended once the required follow-ups land (routers registered, real `update_latest_extraction_run`/`project_latest_facts`, Crawling module actually populated by real runs): an end-to-end smoke test from a real crawl run through to a real company projection, mirroring how Task 006's completion report describes its own deferred manual verification.

---

# Risks

**Technical risks**
- This is the largest single-task functional surface built so far in this repository (10+ extractor families, evidence factory, confidence policy, reconciliation engine, freshness policy, two full hexagonal modules) — proportionally higher risk of an individual extractor/pattern being under-tested relative to its own stated requirements than any prior task. Mitigated by AC-15's explicit pattern-coverage requirement and the brief's own "one family at a time" implementation order (T15–T21), but flagged as a real risk, not assumed away.
- `CrawlRepositoryExtractionGateway`'s `unchanged_from_page_id`-following behavior (resolution #1) is a genuinely new decision this contract makes, not validated by any prior task — if crawling's own change-detection ever chains more than one hop in a future change, this adapter's single-hop-follow assumption would silently under-resolve content. Documented in the adapter's own docstring as a residual assumption, not silently made.
- Deterministic, pattern-based extraction inherently trades recall for precision — a real site's actual wording will diverge from any fixed pattern list in ways 28 fixtures cannot fully anticipate. This is an accepted, explicit design choice (no AI in this task, per the brief), not an oversight; real-world tuning is expected to be a future task.
- `list_pages`'s in-memory-filter-after-full-pagination-loop approach (resolution #1) means one crawl run's full page set is always loaded into memory for target selection — acceptable at this task's documented page-count caps (crawling's own `max_pages_per_company` default of 30), but not distributed-scale-safe; the same accepted tradeoff `DiscoveryRepositoryCrawlGateway.list_discovered_urls` already made in Task 006.

**Business risks**
- `CompanyExtractionGateway.project_latest_facts`/`update_latest_extraction_run` being no-ops (resolutions #2/#3) means `GET /api/companies/{id}` (once wired) will not reflect a company's latest extraction run or its projected facts until both follow-ups land — the underlying data is fully available via this module's own API (`GET /api/companies/{id}/facts`), but not yet through the Company module's own surface. A real but bounded, documented gap, matching Task 006's own precedent exactly.
- Reconciliation and confidence-threshold defaults (brief sections 14/15) are the brief's own *suggested* starting points, not empirically validated against real company data — expect these to need tuning once real crawl data flows through this pipeline.

**Performance risks**
- Extraction is CPU-bound (pattern matching over potentially many pages × many extractors per company) with no batching/parallelism specified by the brief and none added here — acceptable for this task's scope, a future concern if used at scale.

**Security risks**
- All crawled page content is treated as untrusted input throughout (brief's explicit instruction, section "Architecture") — extractors only ever parse text/HTML via stdlib patterns, never `eval`/execute anything from page content. Evidence redaction (AC-19) is a deliberate, if necessarily incomplete, PII-reduction measure — not a substitute for a real data-handling policy review before this data is ever exposed beyond internal use.
- No authentication exists anywhere in this repository yet (consistent with every prior module) — these routers, once registered, are open to anyone who can reach the API. Same accepted risk already recorded for every prior contract.

**Data integrity risks**
- `document_version`-based optimistic concurrency (T24) protects against stale concurrent writes, but this task's application service is single-worker/sequential by design (matching every prior module) — defense-in-depth for a future multi-worker scenario, not exercised by normal operation today.
- Evidence immutability (T25/AC-20) is enforced only by the repository interface's method surface (no `update_evidence` beyond status exists) — a future direct-MongoDB write outside this module's repository could still violate it; this is an accepted, documented boundary of "enforced by interface discipline," not by a database-level constraint.

---

# Dependencies

**External APIs:** None. No AI/OpenAI calls anywhere in this task — explicitly forbidden by the brief ("Do not use AI in this task," "Do not implement: AI-assisted extraction").

**MongoDB:** Required for `MongoExtractionRepository` (five new collections) and `MongoEvidenceRepository` (one new collection). Uses the existing Motor client factory (`app.db.get_database`) via the same DI pattern as every prior module — no new MongoDB connectivity code.

**Playwright / browser rendering:** Not used, not needed — this task consumes already-crawled content, it never fetches anything itself (brief's explicit "extractors must not perform network requests").

**OpenAI:** Not used — confirmed absent from scope by the brief itself.

**Environment variables:** None new — `FreshnessPolicy` and any other tunables are plain, injectable Pydantic models (matching `CrawlConfig`/`DiscoveryConfig`'s established pattern), never reading `os.environ` directly; wiring real values from `backend/app/config.py`'s `Settings` is a future integration step, not part of this task (`config.py` is off-limits to this task's allowed paths, per its own "Do not modify" list covering "root configuration files").

**Required follow-up outside this task's allowed paths (report, do not build):**
1. Register `extraction_router` and `evidence_router` in `backend/app/main.py`, and wire `MongoExtractionRepository.ensure_indexes()`/`MongoEvidenceRepository.ensure_indexes()` into the app's startup `lifespan` handler, alongside the four existing `ensure_indexes()` calls.
2. Add `CompanyRepository.update_latest_extraction_run_id` (interface + `MongoCompanyRepository` implementation) and `CompanyService.update_latest_extraction_run` in `modules/companies/`, mirroring `update_latest_discovery_run` exactly; then switch `CompanyServiceExtractionGateway.update_latest_extraction_run` from its documented no-op to a real call. (Same shape as Task 006's still-outstanding `update_latest_crawl_run` follow-up — consider batching both into one `modules/companies/` change.)
3. Design and add a facts-projection field (or equivalent) to `Company`/`CompanyProcessing`, a `CompanyRepository.update_latest_facts` method, and `CompanyService.update_latest_facts`, in `modules/companies/` — a larger design task than #2 (schema-shape decision, not a mechanical mirror), per resolution #3. Then switch `CompanyServiceExtractionGateway.project_latest_facts` from its no-op to a real call.
4. (Still outstanding from Task 006, re-flagged here for visibility since this task depends on the same module) Task 006's own required follow-up — `update_latest_crawl_run` — remains unresolved as of this task's start (confirmed by inspection: `CompanyService` still has no such method). Not this task's responsibility to fix, but worth batching with #2 above if the same follow-up PR touches `modules/companies/`.
5. A real, tuned confidence/reconciliation/freshness-policy calibration pass against actual crawled company data, once available — the defaults shipped here are the brief's own suggested starting points (see Risks).

---

# Out of Scope

Exactly the task brief's own section 29 list, carried forward verbatim: AI-assisted extraction; AI analysis; opportunity scoring; ranking; outreach; frontend pages; website discovery (already built, Task 005); page crawling (already built, Task 006); browser rendering; external enrichment; geocoding; third-party contact lookup; authentication; deployment; CI/CD. Additionally, explicitly out of scope for this contract specifically: registering either router in `main.py`; any change to `modules/companies/**`, `modules/imports/**`, `modules/discovery/**`, `modules/crawling/**`, `backend/app/main.py`, `backend/app/api/**`, `pyproject.toml`, or `tools/**` (all reported as required follow-ups above, not built here); StoreLeads import (already built, Task 004); any content-download/raw-HTML API endpoint beyond the nine listed; storing chain-of-thought or any AI-model output anywhere (there is none, by construction); a `latest_facts` write path on the Company module (design flagged, not built, per resolution #3).

---

# Suggested Implementation Order

1. T1 — field-path catalogue (nothing else can validate against it otherwise)
2. T2–T6 — extraction + evidence domain models, enums, exceptions
3. T7 — extractor protocol + `PageContext` + `FactCandidateDraft`
4. T8–T10 — `ExtractionRepository`/`EvidenceRepository` ports + `CompanyExtractionGateway`/`CrawlExtractionGateway`/`EvidenceGateway` ports
5. T11 — evidence factory + its unit tests
6. T12 — confidence policy + its unit tests
7. T13 — reconciliation engine + its unit tests
8. T15 — identity extractors (first family, per the brief's own explicit order) + fixtures + unit tests
9. T16 — business-model extractors + fixtures + unit tests
10. T20 — organisation/contact extractors + fixtures + unit tests
11. T18 — operations extractors + fixtures + unit tests
12. T19 — technology extractors + fixtures + unit tests
13. T17 — catalogue extractors + fixtures + unit tests
14. T21 — growth extractors + fixtures + unit tests
15. T14 — freshness policy (can land any time after T2, placed here since T13/T21 exercise it most directly)
16. T26–T28 — gateway adapters (`CompanyServiceExtractionGateway`, `CrawlRepositoryExtractionGateway`, `EvidenceServiceExtractionGateway`)
17. T22 — `StructuredExtractionService`, assembling every port above, with its fakes-based integration test suite
18. T23 — company projection + its unit tests
19. T24, T25 — `MongoExtractionRepository`, `MongoEvidenceRepository` + real-Mongo integration tests
20. T29, T30 — API schemas + routers (unregistered) for both modules + API schema serialization tests
21. Full-pipeline integration tests (brief section 25) over the complete `fixtures/extraction/` set
22. Full local verification: `pytest backend/tests/unit/{extraction,evidence} backend/tests/integration/{extraction,evidence}`, `ruff check`, `pyright` on all new/changed paths
23. Final report: files created, extractors implemented, supported field paths, confidence policy, reconciliation behavior, evidence behavior, freshness rules, known limitations, required integration steps — exactly per the brief's own section 31 "After implementation" reporting requirement

---

# Success Criteria

This feature is complete only when:

✓ AC-01 through AC-40 all pass

✓ Every test file listed under "Required Tests" exists and passes, including the fixture-backed unit tests and the real-MongoDB repository tests

✓ `domain/` and `application/` in both `modules/extraction` and `modules/evidence` contain zero imports of FastAPI, Motor/pymongo, or any AI SDK (confirmed by inspection, matching the discipline already enforced in every prior hexagonal module)

✓ No extractor performs a network request or accesses MongoDB (confirmed by inspection of every file under `domain/extractors/`)

✓ No file outside `backend/app/modules/extraction/**`, `backend/app/modules/evidence/**`, `backend/tests/unit/{extraction,evidence}/**`, `backend/tests/integration/{extraction,evidence}/**`, `fixtures/extraction/**` was modified — confirmed via `git diff --stat`

✓ The five cross-module resolutions above (`CrawlExtractionGateway` real adapter with unchanged-page resolution; `update_latest_extraction_run` no-op; `project_latest_facts` no-op with the larger-scope follow-up documented; `update_processing_status` real; the `EvidenceGateway` port between `extraction` and `evidence`) are implemented exactly as decided, each with the documentation this contract specifies — not left as silent or differently-resolved gaps

✓ `ruff check` and `pyright` are clean on every new/changed path

✓ The "Required follow-up outside this task's allowed paths" list is reported, not silently built or silently omitted

✓ Evaluator reports PASS

---

## Files read during this planning pass (for traceability)

- `/srv/lead-intelligence/CLAUDE.md`, `/srv/lead-intelligence/ARCHITECTURE.md`
- `/srv/lead-intelligence/docs/execution-plans/tasks/007—Structured-Extraction-and-Evidence-Module.md`
- `/srv/lead-intelligence/docs/contracts/completed/crawling-module.md`, `/srv/lead-intelligence/docs/execution-plans/completed/crawling-module.md`
- `/srv/lead-intelligence/backend/app/modules/crawling/{api/router.py,api/schemas.py,domain/repository.py,domain/models.py,domain/enums.py,domain/config.py,domain/content_storage.py,domain/gateway.py,domain/html_cleaner.py,infrastructure/company_service_gateway.py}`
- `/srv/lead-intelligence/backend/app/modules/companies/{application/service.py,domain/models.py,domain/repository.py,domain/enums.py,domain/transitions.py,api/router.py}`
- `/srv/lead-intelligence/backend/app/modules/discovery/{domain/enums.py,domain/gateway.py}`
- `Glob` confirmation that `backend/app/modules/extraction/`, `backend/app/modules/evidence/`, and `fixtures/extraction/` do not yet exist, and that `backend/tests/integration/crawling/` / `fixtures/crawling/` follow the naming conventions cited above.

No source files were modified — this was a read-only planning pass.