# MongoDB Design

## Database

One MongoDB database per environment, named by `MONGODB_DB_NAME` (see
`.env.example`). Tests use a separate, dedicated database
(`<MONGODB_DB_NAME>_test`) so automated tests never touch development
data (see `backend/tests/conftest.py`).

## Collections

### `companies`

The first collection in the system, created by the paste-in importer
feature. Holds one document per imported store/domain. Fields are
limited to exactly what this feature populates — no speculative
scoring/status/qualification fields are added ahead of the feature that
actually needs them.

```
{
  _id: ObjectId,
  domain: string,                             # normalized, unique, indexed
  source: "paste_domain_list" | "paste_storeleads_html",
  url: string | null,                          # store's own URL; storeleads mode only
  estimated_sales_yearly_usd: float | null,     # storeleads mode only; currency fixed at USD (source-fixed)
  source_created_at: datetime | null,           # UTC midnight; the "created" date reported by storeleads.app (date-only, no time-of-day)
  emails: string[],                             # default []
  phones: string[],                             # default []
  imported_at: datetime,                        # UTC, set once at insert time
}
```

Notes:

- `source_created_at` is a date-only concept at the application layer
  (Python `datetime.date`, per `Company.source_created_at` in
  `backend/app/domains/companies/models.py`), but BSON has no native
  date-only type, so `CompanyRepository` stores it as a UTC-midnight
  `datetime` — the standard MongoDB representation for date-only
  values. This conversion is confined to `repository.py`.
- Records are **immutable once created** in v1: there is no
  update/upsert path. See `docs/decisions/0001-paste-in-importer-foundational-decisions.md`
  for the rationale ("ignore, never update" dedupe policy).

## Indexes

`companies.domain` — **unique index**, created at application startup
via `CompanyRepository.ensure_indexes()` (called from `main.py`'s
lifespan handler). This is defense-in-depth against race conditions: the
service layer already checks `get_existing_domains()` before inserting,
but two concurrent imports of the same brand-new domain could both pass
that check before either persists. The unique index guarantees MongoDB
itself rejects the second insert; `CompanyRepository.insert_many()`
catches that `DuplicateKeyError` per-document and treats it as a skipped
insert rather than letting it raise an unhandled 500.

## Access pattern

All access to `companies` goes through `CompanyRepository`
(`backend/app/domains/companies/repository.py`):

- `ensure_indexes()` — idempotent; creates the unique index on `domain`.
- `get_existing_domains(domains: list[str]) -> set[str]` — single
  batched `$in` query, not one query per domain.
- `insert_many(companies: list[Company]) -> list[Company]` — inserts
  one document at a time (not a single bulk call) so a duplicate-key
  conflict on one document doesn't abort the rest of the batch, and
  returns only the documents that were actually persisted.

No other module queries or writes to the `companies` collection
directly — but see `companies_pipeline` below, a **separate**
collection for a separate module.

### `companies_pipeline`

Created by `backend/app/modules/companies/` (the hexagonal-convention
module — see `ARCHITECTURE.md`'s "Module convention" section). Deliberately
a different collection from `companies` above, not an extension of it:
this module's `Company` tracks pipeline/review state for a company being
worked through Discovery→Scoring, which is a different concept from the
flat convention's immutable, freshly-imported `Company` record. Sharing
one collection between the two would have meant two incompatible unique
indexes and document shapes fighting over the same namespace.

```
{
  _id: ObjectId,
  company_id: string,                  # app-generated (uuid4), not `_id`
  domain: string,                      # as originally provided
  normalized_domain: string,           # normalized, unique, indexed
  identity: {
    company_name: string | null,
    platform: string | null,
    country: string | null,
    city: string | null,
  },
  processing: {
    status: string,                    # ProcessingStatus enum value, indexed
    latest_discovery_run_id: string | null,
    latest_crawl_run_id: string | null,
    latest_extraction_run_id: string | null,
    latest_analysis_run_id: string | null,
    latest_scoring_run_id: string | null,
  },
  workflow: {
    manual_status: string,             # WorkflowStatus enum value, indexed
    shortlisted: bool,
    notes_count: int,
  },
  created_at: datetime,                # UTC
  updated_at: datetime,                # UTC
  document_version: int,               # schema-version marker, currently always 1
}
```

Notes:

- The `latest_*_run_id` fields are opaque identifiers owned by each
  pipeline stage's own future module (discovery/crawl/extraction/
  analysis/scoring) — this module only stores the id, never interprets
  it. They replaced an earlier version of this schema that stored
  per-stage *timestamps* directly.
- Records are mutable: `update_processing_status`/`update_workflow_status`
  change `processing.status`/`workflow.manual_status` (and
  `updated_at`) in place. Unlike `companies`, there is no "immutable,
  no update path" rule here — status transitions are the whole point of
  this module, though only *valid* transitions are accepted (see
  `backend/app/modules/companies/domain/transitions.py`); an invalid one
  is rejected with a typed `InvalidStatusTransitionError` (HTTP 409).
- Motor's client isn't configured with `tz_aware=True` (`app/db.py`), so
  reads return naive datetimes; `Company.created_at`/`updated_at` have a
  Pydantic validator that stamps a naive value with UTC on load, so
  "all timestamps are timezone-aware UTC" holds at the domain boundary
  regardless of what the driver returns.

Indexes, all created at startup via `MongoCompanyRepository.ensure_indexes()`:

- `normalized_domain` — **unique**.
- `processing.status`, `workflow.manual_status`, `identity.platform`,
  `identity.country` — non-unique, supporting `GET /api/companies`'s
  filters.

Access pattern: all reads/writes go through `MongoCompanyRepository`
(`backend/app/modules/companies/infrastructure/mongo_repository.py`);
`list_companies()` returns both the paginated page and a `count_documents()`
total in one call, backing the `GET /api/companies` `{data, pagination}`
envelope. **No other module writes to this collection directly** —
`backend/app/modules/imports/` (the StoreLeads HTML importer) creates
`companies_pipeline` documents only by calling `CompanyService.create_company()`
through a narrow gateway interface it defines itself
(`imports/domain/gateway.py`'s `CompanyImportGateway`), never by
importing `MongoCompanyRepository` or holding its own Motor handle to
this collection. See `ARCHITECTURE.md`'s "Cross-module dependencies:
the gateway/port pattern" section.

### `discovery_runs` and `discoveries`

Created by `backend/app/modules/discovery/` (Task 005). Two collections,
not one: `discovery_runs` holds one document per discovery run (status,
summary, timing); `discoveries` holds one document per `DiscoveredUrl`
reconciled during a run — the same one-collection-per-record-shape split
`companies`/`companies_pipeline` already established, generalized to a
run/its-child-records relationship.

```
# discovery_runs
{
  _id: ObjectId,
  discovery_run_id: string,            # app-generated (uuid4), unique, indexed
  company_id: string,                  # indexed
  root_domain: string,
  homepage_url: string | null,

  status: string,                      # DiscoveryStatus enum value, indexed
  started_at: datetime | null,         # UTC, indexed
  completed_at: datetime | null,       # UTC

  summary: {
    urls_found: int, urls_accepted: int, urls_excluded: int,
    sitemap_urls_found: int, robots_urls_found: int,
    duplicate_urls_merged: int, warnings: int, duration_ms: int,
  },
  error: string | null,

  created_at: datetime,                # UTC
  updated_at: datetime,                # UTC
}

# discoveries
{
  _id: ObjectId,
  discovered_url_id: string,            # app-generated (uuid4), unique, indexed
  discovery_run_id: string,             # part of the compound unique index below
  company_id: string,                   # indexed

  url: string,
  normalized_url: string,               # indexed; part of the compound unique index below

  page_type: string,                    # PageType enum value, indexed
  page_type_confidence: int,            # 0-100
  priority: string,                     # DiscoveryPriority enum value ("1"/"2"/"3"/"excluded"), indexed

  discovery_sources: string[],          # DiscoverySource enum values (nav/footer/sitemap/robots/...)
  source_urls: string[],
  anchor_texts: string[],

  depth: int,
  is_same_domain: bool,
  is_allowed: bool,                     # default true; robots enforcement is a future crawler's job

  first_discovered_at: datetime,        # UTC
  last_discovered_at: datetime,         # UTC

  metadata: object,                     # alternate classifications, rule ids (see reconciliation)
}
```

Indexes, all created at startup via `MongoDiscoveryRepository.ensure_indexes()`:

- `discovery_runs`: `discovery_run_id` (unique), `company_id`, `status`,
  `started_at`.
- `discoveries`: `discovered_url_id` (unique); compound
  `(discovery_run_id, normalized_url)` (**unique** — one `DiscoveredUrl`
  per URL per run, which is what makes reconciliation's "merge, don't
  duplicate" behavior enforceable at the database level, not just in
  application code); `company_id`; `page_type`; `priority`;
  `normalized_url`.

Notes:

- Raw homepage HTML is **never** stored in `discoveries` — only the
  reconciled URL records themselves. There is no equivalent of a content
  blob for this module (that's the crawling module's job, below).
- Records in both collections are mutable in the narrow sense that a run
  document transitions through `DiscoveryStatus` values as it progresses
  (`update_run`); `discoveries` documents themselves are written once
  per run via `save_discovered_urls` and not subsequently edited.

Access pattern: all reads/writes go through `MongoDiscoveryRepository`
(`backend/app/modules/discovery/infrastructure/mongo_discovery_repository.py`).
**No other module writes to either collection** — `modules/crawling`
(below) only ever *reads* discovery's results, and does so through
`DiscoveryRepositoryCrawlGateway`, an adapter wrapping the
`DiscoveryRepository` interface (obtained via discovery's own
`get_discovery_repository` DI function), never `MongoDiscoveryRepository`
or a Motor handle of its own.

### `crawl_runs`, `crawl_targets`, and `pages`

Created by `backend/app/modules/crawling/` (Task 006). Three
collections, following the same run/its-child-records split as
`discovery_runs`/`discoveries`, with one addition: `crawl_targets` (the
selected-URL-to-fetch queue for a run) is a separate collection from
`pages` (the actual fetch outcome/content record for a target), because
a target can be retried — `retry_failed` re-processes a `crawl_target`
without creating a second `CrawlRun`, upserting the same `pages`
document rather than duplicating it.

```
# crawl_runs
{
  _id: ObjectId,
  crawl_run_id: string,                 # app-generated (uuid4), unique, indexed
  company_id: string,                   # indexed
  discovery_run_id: string,             # indexed; the discovery run this crawl selected targets from

  status: string,                       # CrawlStatus enum value, indexed
  started_at: datetime | null,          # UTC, indexed
  completed_at: datetime | null,        # UTC

  configuration_snapshot: object,        # the CrawlConfig/options this run was created with
  summary: {
    targets_selected: int, pages_fetched: int, pages_unchanged: int,
    pages_skipped: int, pages_blocked_by_robots: int, pages_failed: int,
    pages_requiring_browser: int, pages_browser_fetched: int,
    bytes_downloaded: int, warnings: int, duration_ms: int,
  },
  warnings: [{ code: string, message: string, url: string | null,
               page_id: string | null, created_at: datetime }],
  error: string | null,

  created_at: datetime,                 # UTC
  updated_at: datetime,                 # UTC

  idempotency_key: string,              # sha256 of company_id/discovery_run_id/options
                                         # (see the module's `domain/idempotency.py`) — used to
                                         # detect a duplicate active-run request
  document_version: int,                # optimistic-concurrency marker; starts at 1
}

# crawl_targets
{
  _id: ObjectId,
  crawl_target_id: string,              # app-generated (uuid4), unique, indexed
  crawl_run_id: string,                 # part of the compound unique index below; indexed
  company_id: string,                   # indexed
  discovery_run_id: string,
  discovered_url_id: string | null,     # the DiscoveredUrl this target was selected from

  url: string,
  normalized_url: string,               # part of the compound unique index below
  page_type: string,                    # discovery's PageType enum value, reused directly
  priority: string,                     # discovery's DiscoveryPriority enum value, reused directly
  fetch_mode: string,                   # FetchMode enum value ("http" | "browser")
  depth: int,
  expected_content_type: string | null,

  previous_page_id: string | null,      # for conditional-fetch/change-detection
  previous_content_hash: string | null,

  status: string,                       # PageFetchStatus enum value, indexed
  attempt_count: int,

  created_at: datetime,                 # UTC
  updated_at: datetime,                 # UTC
  document_version: int,                # optimistic-concurrency marker; starts at 1
}

# pages
{
  _id: ObjectId,
  page_id: string,                      # app-generated (uuid4), unique, indexed
  crawl_run_id: string,                 # part of the compound unique index below; indexed
  company_id: string,                   # indexed
  discovery_run_id: string,
  discovered_url_id: string | null,

  original_url: string,
  final_url: string | null,             # after following redirects
  normalized_url: string,               # part of the compound unique index below; indexed
  page_type: string,                    # indexed
  priority: string,
  fetch_mode: string,
  fetch_status: string,                 # PageFetchStatus enum value, indexed

  http_metadata: {
    status_code: int | null, content_type: string | null, content_length: int | null,
    etag: string | null, last_modified: string | null,
    redirect_history: [{ url: string, status_code: int }],
    response_headers_allowlist: object,  # only allowlisted response headers, never the full set
    duration_ms: int, remote_ip_validation_result: string | null,
  },
  page_metadata: {                       # null until a fresh 200 is actually processed
    title: string | null, meta_description: string | null, canonical_url: string | null,
    language: string | null, robots_meta: string | null,
    og_site_name: string | null, og_title: string | null, generator: string | null,
    html_size_bytes: int, cleaned_html_size_bytes: int, extracted_text_length: int,
    link_count: int, script_count: int, stylesheet_count: int,
    technology_signals: object,          # raw, page-level only — never written to `companies_pipeline`
    cleaning_rules_version: string, text_extraction_rules_version: string,
  } | null,
  content_storage: {
    raw_content_mode: string, cleaned_html_mode: string, cleaned_html_reference: object | null,
    extracted_text_mode: string, extracted_text_reference: object | null,
  },
  content_hashes: {
    raw_content_sha256: string | null, cleaned_html_sha256: string | null,
    extracted_text_sha256: string | null, structural_hash: string | null,
  },

  cleaned_html: string | null,           # inline only below CrawlConfig's size threshold
  extracted_text: string | null,         # inline only below CrawlConfig's size threshold
  raw_content_reference: object | null,  # always external — raw HTML is never inlined

  previous_page_id: string | null,
  unchanged_from_page_id: string | null,
  browser_fallback_reason: string | null,

  warnings: [{ code: string, message: string, url: string | null,
               page_id: string | null, created_at: datetime }],

  fetched_at: datetime | null,           # UTC
  created_at: datetime,                  # UTC
  updated_at: datetime,                  # UTC
  document_version: int,                 # optimistic-concurrency marker; starts at 1
}
```

Indexes, all created at startup via `MongoCrawlRepository.ensure_indexes()`:

- `crawl_runs`: `crawl_run_id` (unique), `company_id`, `discovery_run_id`,
  `status`, `started_at`.
- `crawl_targets`: `crawl_target_id` (unique); compound
  `(crawl_run_id, normalized_url)` (**unique** — one target per URL per
  run); `company_id`; `status`; `priority`.
- `pages`: `page_id` (unique); `company_id`; `crawl_run_id`;
  `normalized_url`; `fetched_at`; `page_type`; `fetch_status`; compound
  `(company_id, normalized_url, fetched_at desc)` (supports
  `get_latest_page_by_normalized_url` — finding the most recent page for
  a URL across runs, for conditional-fetch/change-detection); compound
  `(crawl_run_id, normalized_url)` (**unique** — a **documented addition**
  beyond the feature contract's literal index list, needed to make
  `save_page` an upsert keyed on this pair so `retry_failed` never
  duplicates a page document).

Notes:

- **Raw HTML is never stored in MongoDB** — only `ContentReference`
  handles (`raw_content_reference`, and `cleaned_html_reference`/
  `extracted_text_reference` once external) pointing at
  `LocalFilesystemContentStorage`'s on-disk files. Cleaned HTML and
  extracted text are inlined directly in the `pages` document only when
  they're below `CrawlConfig`'s configured size thresholds.
- `crawl_runs`, `crawl_targets`, and `pages` all use **optimistic
  concurrency** via `document_version` — an update's filter includes the
  caller's current `document_version` and the write is rejected (no
  document mutated) if another writer already advanced it. This is
  defense-in-depth for a future multi-worker scenario; today's
  single-worker, sequential-per-company crawling doesn't exercise
  concurrent writers in normal operation.
- `technology_signals` (inside `page_metadata`) is collected but
  **never** written back to `companies_pipeline` — this module
  deliberately does not update any company-facing technology profile
  field (that's a future Extraction/Analysis-stage concern).

Access pattern: all reads/writes go through `MongoCrawlRepository`
(`backend/app/modules/crawling/infrastructure/mongo_crawl_repository.py`).
**No other module writes to any of these three collections.** The
crawling module itself reaches `modules/companies` and `modules/discovery`
only through its own gateway ports (`CompanyCrawlGateway`,
`DiscoveryCrawlGateway`) — never a concrete Mongo repository imported
from another module. See `ARCHITECTURE.md`'s "Cross-module dependencies:
the gateway/port pattern" section.
