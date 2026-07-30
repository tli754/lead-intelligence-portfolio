Task 006 — Implement Website Crawling Module

You are implementing the Website Crawling module for the
eCommerce Opportunity Intelligence project.

Other worktrees may be implementing:

- frontend mock pages
- Company module
- StoreLeads import
- Website Discovery

Keep this task isolated to the crawling module.

Allowed paths:

- backend/app/modules/crawling/**
- backend/tests/unit/crawling/**
- backend/tests/integration/crawling/**
- fixtures/crawling/**

Do not modify:

- frontend/**
- backend/app/modules/companies/**
- backend/app/modules/imports/**
- backend/app/modules/discovery/**
- backend/app/main.py
- backend/app/api/**
- tools/**
- extraction, evidence, AI, scoring, or ranking modules
- shared root configuration files

If a central dependency, router registration, worker registration, shared
configuration, or package change is required outside the allowed paths, report
it as an integration step rather than making it.

Architecture:

- modular monolith
- Domain → Application → Infrastructure → API
- domain and application code must not depend on FastAPI, MongoDB, Redis,
  Playwright, or HTTP client implementations
- HTTP and browser fetching belong in infrastructure
- the crawler must consume discovery data through a narrow interface
- the crawler must not access the discovery or companies MongoDB collections
  directly
- use strict typing
- use timezone-aware UTC timestamps
- all external content is untrusted
- all network requests require SSRF protection, timeouts, redirect limits,
  response-size limits, and content-type validation

Implement the following.

1. Crawling domain models

Create:

CrawlRun
CrawlTarget
CrawledPage
CrawlStatus
PageFetchStatus
FetchMode
ContentStorageMode
BrowserFallbackReason
CrawlWarning
CrawlSummary
HttpMetadata
PageMetadata
ContentHashes

CrawlStatus values:

- queued
- running
- completed
- completed_with_warnings
- partial
- failed
- cancelled

PageFetchStatus values:

- queued
- fetching
- fetched
- unchanged
- skipped
- blocked_by_robots
- rejected
- failed
- browser_required
- browser_fetched

FetchMode values:

- http
- browser

ContentStorageMode values:

- inline
- external
- none

BrowserFallbackReason values:

- empty_html
- javascript_shell
- insufficient_text
- client_rendered_marker
- challenge_page
- unsupported_http_response
- manually_requested

CrawlTarget fields:

- crawl_target_id
- crawl_run_id
- company_id
- discovery_run_id
- discovered_url_id
- url
- normalized_url
- page_type
- priority
- fetch_mode
- depth
- expected_content_type
- previous_page_id
- previous_content_hash
- status
- attempt_count
- created_at
- updated_at

CrawlRun fields:

- crawl_run_id
- company_id
- discovery_run_id
- status
- started_at
- completed_at
- configuration_snapshot
- summary
- warnings
- error
- created_at
- updated_at

CrawledPage fields:

- page_id
- crawl_run_id
- company_id
- discovery_run_id
- discovered_url_id
- original_url
- final_url
- normalized_url
- page_type
- priority
- fetch_mode
- fetch_status
- http_metadata
- page_metadata
- content_storage
- content_hashes
- cleaned_html
- extracted_text
- raw_content_reference
- previous_page_id
- unchanged_from_page_id
- browser_fallback_reason
- warnings
- fetched_at
- created_at
- updated_at

HttpMetadata:

- status_code
- content_type
- content_length
- etag
- last_modified
- redirect_history
- response_headers_allowlist
- duration_ms
- remote_ip_validation_result

PageMetadata:

- title
- meta_description
- canonical_url
- language
- robots_meta
- og_site_name
- og_title
- generator
- html_size_bytes
- cleaned_html_size_bytes
- extracted_text_length
- link_count
- script_count
- stylesheet_count

ContentHashes:

- raw_content_sha256
- cleaned_html_sha256
- extracted_text_sha256
- structural_hash

CrawlSummary:

- targets_selected
- pages_fetched
- pages_unchanged
- pages_skipped
- pages_blocked_by_robots
- pages_failed
- pages_requiring_browser
- pages_browser_fetched
- bytes_downloaded
- warnings
- duration_ms

Use snake_case internally and camelCase only in HTTP schemas.

2. Crawl target selection

Create deterministic target-selection logic that consumes prioritized discovery
records.

Default inclusion:

Priority 1:
- always include

Priority 2:
- include by default

Priority 3:
- include selectively according to configured limits

Excluded:
- never include unless explicitly overridden

Required target-selection behavior:

- deduplicate by normalized URL
- preserve page type and priority
- prefer shallower URLs
- prefer URLs found in navigation, footer, robots, or sitemap
- cap total pages per company
- cap product pages separately
- cap collection/category pages separately
- support page-type allow and deny lists
- support manual URL inclusion
- support manual URL exclusion
- sort deterministically

Default selection order:

1. homepage
2. wholesale
3. trade
4. contact
5. about
6. store_locator
7. click_and_collect
8. shipping
9. careers
10. returns
11. faq
12. support
13. team
14. brands
15. subscription
16. blog
17. news
18. collection
19. category
20. sampled product
21. privacy
22. terms
23. unknown

Recommended local defaults:

- maximum pages per company: 30
- maximum product pages: 5
- maximum collection/category pages: 8
- maximum unknown pages: 3

All limits must be configurable.

3. Robots policy

The crawling module must check robots permission before fetching each URL.

Create a RobotsPolicyGateway protocol that returns:

- allowed
- disallowed
- unknown
- crawl_delay
- matched_rule
- source

Behavior:

- blocked URLs receive blocked_by_robots status
- unknown policy may proceed with a warning
- respect configured user agent
- honor crawl delay within reasonable limits
- do not silently ignore robots rules
- robots policy must be independently testable

Do not reimplement discovery parsing logic inside the crawler.

4. HTTP fetcher

Create an infrastructure HTTP fetcher.

Requirements:

- HTTP and HTTPS only
- GET requests only
- controlled User-Agent
- no cookies
- no authentication headers
- no automatic JavaScript execution
- configurable connect timeout
- configurable read timeout
- configurable total timeout
- configurable maximum redirects
- configurable maximum response size
- stream responses to enforce size limits
- validate every redirect target
- validate resolved IP addresses
- reject private, loopback, link-local, multicast, reserved, and internal
  addresses
- reject credentials in URLs
- reject unsupported schemes
- reject non-HTML responses for normal page targets
- allow text/plain only when explicitly configured
- decompress gzip and Brotli only within size limits
- return typed failure reasons
- capture response timing
- retain only allowlisted response headers
- do not log response bodies

Suggested allowlisted headers:

- content-type
- content-length
- etag
- last-modified
- cache-control
- content-language
- server
- x-powered-by

Do not automatically retry all failures.

Retry only transient failures such as:

- connection reset
- timeout
- HTTP 408
- HTTP 425
- HTTP 429
- HTTP 500
- HTTP 502
- HTTP 503
- HTTP 504

Use bounded exponential backoff with jitter.

Default:

- maximum attempts: 3
- maximum redirects: 5
- connect timeout: 5 seconds
- read timeout: 15 seconds
- total timeout: 20 seconds
- maximum HTML response: 5 MB

5. Conditional requests and change detection

Support conditional fetching when a previous page record exists.

Send where available:

- If-None-Match
- If-Modified-Since

Handle HTTP 304 as unchanged.

If the server returns 200:

- calculate content hashes
- compare to previous hashes
- mark unchanged when content is materially identical
- preserve the latest fetch metadata
- point unchanged_from_page_id to the previous page

Hashes:

- raw SHA-256
- cleaned HTML SHA-256
- extracted text SHA-256
- structural hash

Structural hash should reduce sensitivity to:

- whitespace
- dynamic timestamps
- random element IDs
- tracking attributes
- script order where practical

Do not make structural normalization so aggressive that meaningful content
changes are hidden.

6. HTML validation

Before processing HTML:

- validate Content-Type
- reject binary signatures
- reject empty responses
- detect truncated responses
- detect encoding
- decode safely
- cap decoded size
- tolerate malformed HTML
- retain decoding warnings
- reject obvious non-page responses such as image, PDF, ZIP, executable, or
  media content

Classify common blocked/challenge responses:

- Cloudflare challenge
- CAPTCHA
- access denied
- bot challenge
- maintenance page
- password-protected storefront

These may be marked:

- failed
- rejected
- browser_required

depending on configured policy.

7. HTML cleaning

Create a deterministic HTML cleaner.

Remove or normalize:

- script contents
- style contents
- noscript boilerplate where appropriate
- SVG contents where not useful
- tracking pixels
- comments
- inline event-handler attributes
- nonce values
- integrity values
- dynamic framework hydration payloads where safe
- duplicated whitespace
- known analytics script blocks

Preserve:

- semantic structure
- headings
- paragraphs
- lists
- tables
- forms
- labels
- buttons
- product text
- navigation text
- footer text
- links and href values
- image alt text
- structured data separately where useful

Do not execute or evaluate JavaScript.

Cleaning must be versioned.

8. Text extraction

Create deterministic visible-text extraction from cleaned HTML.

Requirements:

- preserve meaningful section order
- preserve headings
- preserve list items
- preserve table cell text
- include image alt text where meaningful
- exclude script/style text
- normalize whitespace
- avoid repeating navigation and footer content excessively
- cap maximum extracted text length
- record truncation
- do not summarize or interpret content

Recommended maximum extracted text:

- 250,000 characters per page

9. Page metadata extraction

Extract deterministic metadata:

- title
- meta description
- canonical URL
- html lang
- robots meta
- OG site name
- OG title
- generator
- link count
- script count
- stylesheet count

Also collect technology signals without converting them into company facts:

- script source hosts
- generator values
- known framework markers
- known commerce platform markers
- known analytics script markers
- known support-widget script markers

Store these as raw page-level signals in metadata.

Do not update the company technology profile in this task.

10. Browser fallback decision

Implement deterministic browser-fallback detection.

Possible reasons:

- response contains an application shell with very little text
- root element exists but content is empty
- common client-rendered framework markers are present
- substantial script payload but insufficient visible content
- page explicitly requires JavaScript
- HTTP response is a supported challenge page
- manual configuration requests browser mode

Return:

- browser_required boolean
- reason
- confidence
- detector rule IDs

Do not implement Playwright inside the main HTTP fetcher.

Create a BrowserPageFetcher protocol:

- fetch_rendered_page(request) -> rendered response

If a browser implementation already exists in the repository, add an adapter
inside the crawling module.

If it does not exist, use a fake in tests and leave the concrete implementation
as an integration step.

The crawl service should support these policies:

- never
- detect_only
- fetch_when_required
- always_for_selected_page_types

Default for this task:

- detect_only

This means browser-required pages are identified but not actually fetched unless
a browser adapter is explicitly supplied.

11. Content storage abstraction

Create a ContentStorage protocol.

Methods:

- store_raw_content
- store_cleaned_content
- load_content
- delete_content

The crawler must not depend directly on local disk or S3.

Implement local filesystem storage inside the crawling module for development.

Suggested layout:

data/
crawl-content/
{company_id}/
{crawl_run_id}/
{page_id}/
raw.html
cleaned.html
text.txt

Requirements:

- safe path construction
- no user-controlled path traversal
- atomic writes
- UTF-8
- content hashes verified
- return opaque content references
- do not expose filesystem paths in API responses

Storage policy:

- raw HTML: external storage
- cleaned HTML: inline only when below configured limit, otherwise external
- extracted text: inline only when below configured limit, otherwise external

Recommended inline limits:

- cleaned HTML: 250 KB
- extracted text: 250 KB

12. Persistence

Create a CrawlRepository protocol.

Methods:

- create_run
- update_run
- save_target
- update_target
- save_page
- get_run
- list_runs_by_company
- get_page
- list_pages_by_run
- get_latest_page_by_normalized_url
- find_target_by_url
- mark_run_cancelled

Implement a MongoDB repository only if the repository already contains an
approved MongoDB infrastructure pattern.

Collections:

crawl_runs
crawl_targets
pages

Recommended indexes:

crawl_runs:
- crawl_run_id unique
- company_id
- discovery_run_id
- status
- started_at

crawl_targets:
- crawl_target_id unique
- compound unique:
  - crawl_run_id
  - normalized_url
- company_id
- status
- priority

pages:
- page_id unique
- company_id
- crawl_run_id
- normalized_url
- fetched_at
- page_type
- fetch_status
- compound:
  - company_id
  - normalized_url
  - fetched_at descending

Do not store large raw HTML directly in MongoDB.

13. Integration ports

Define narrow protocols.

CompanyCrawlGateway:

- update_latest_crawl_run(company_id, crawl_run_id)
- update_processing_status(company_id, status)

DiscoveryCrawlGateway:

- get_discovery_run(discovery_run_id)
- list_discovered_urls(
  discovery_run_id,
  priorities,
  page_types,
  include_excluded
  )
- get_robots_policy(company_id, url, user_agent)

CrawlRepository:

- methods listed above

PageFetcher:

- fetch_page

BrowserPageFetcher:

- fetch_rendered_page

ContentStorage:

- methods listed above

Do not import concrete Company or Discovery Mongo repositories.

14. Crawling application service

Create a service such as:

WebsiteCrawlService

Responsibilities:

- validate company and discovery run references
- create crawl run
- select targets
- persist targets
- check cancellation
- evaluate robots policy
- throttle requests
- fetch pages
- apply retry policy
- process conditional responses
- validate and decode content
- clean HTML
- extract text
- extract page metadata
- compute hashes
- detect browser fallback requirements
- optionally invoke browser fetcher
- store content
- persist page records
- update target statuses
- update crawl summary
- update company processing status
- complete, partially complete, fail, or cancel the run

Failure isolation:

- one page failure must not fail the entire run
- storage failure for one page must not fail unrelated pages
- browser fallback failure must not discard the HTTP result
- repository failure may fail the run because state cannot be trusted
- homepage failure should mark the run partial or failed according to
  configuration
- cancellation should stop scheduling new targets but preserve completed pages

Support deterministic sequential crawling initially.

Do not add distributed concurrency in this task.

Allow a configurable low concurrency level for future use, but default to:

- concurrency per company: 1

15. Rate limiting and politeness

Implement per-company request pacing.

Requirements:

- configurable delay between requests
- honor robots crawl-delay where reasonable
- cap extreme crawl-delay values
- support Retry-After
- do not make concurrent requests to the same host by default
- use monotonic time for pacing
- cancellation-aware sleeping

Recommended defaults:

- minimum delay: 500 ms
- default delay: 1 second
- maximum honored crawl delay: 10 seconds
- 429 Retry-After maximum: 60 seconds

16. Idempotency and retries

A crawl run must be safe to retry.

Use an idempotency key based on:

- company_id
- discovery_run_id
- crawl configuration hash
- requested target set hash

Requirements:

- duplicate active run requests return the existing run or a typed conflict
- retrying a failed page does not duplicate page records
- same crawl run and normalized URL must have one target
- content writes must be overwrite-safe or version-safe
- completed target status must not regress without explicit retry
- stale worker updates must be rejected using document_version or equivalent

17. API schemas and router

Create but do not centrally register a crawling router.

Endpoints:

POST /api/companies/{company_id}/crawl-runs

Request:

{
"discoveryRunId": "discovery_run_123",
"options": {
"maxPages": 30,
"browserPolicy": "detect_only",
"forceRefresh": false,
"includePageTypes": [],
"excludePageTypes": [],
"manualUrls": []
}
}

Response:

{
"data": {
"crawlRunId": "crawl_run_123",
"companyId": "company_123",
"discoveryRunId": "discovery_run_123",
"status": "completed_with_warnings",
"summary": {
"targetsSelected": 18,
"pagesFetched": 15,
"pagesUnchanged": 1,
"pagesSkipped": 0,
"pagesBlockedByRobots": 1,
"pagesFailed": 1,
"pagesRequiringBrowser": 2,
"pagesBrowserFetched": 0,
"bytesDownloaded": 584321,
"warnings": 3,
"durationMs": 18422
}
}
}

GET /api/companies/{company_id}/crawl-runs/latest

GET /api/crawl-runs/{crawl_run_id}

GET /api/crawl-runs/{crawl_run_id}/targets

GET /api/crawl-runs/{crawl_run_id}/pages

GET /api/pages/{page_id}

Page and target list query parameters:

- page
- pageSize
- status
- pageType
- priority
- fetchMode
- browserRequired
- includeFailed

POST /api/crawl-runs/{crawl_run_id}/cancel

POST /api/crawl-runs/{crawl_run_id}/retry-failed

The POST crawl endpoint may execute synchronously for local development, but the
application service must remain independent of FastAPI and reusable by a worker.

Do not use FastAPI BackgroundTasks.

API responses must:

- use camelCase
- not expose raw HTML by default
- not expose local filesystem paths
- include opaque content references only where required
- cap extracted text previews
- redact unsafe response headers

18. Tests

Unit tests:

Target selection:

- priority ordering
- page-type ordering
- deduplication
- product limits
- collection limits
- unknown limits
- manual include
- manual exclude
- deterministic results
- maximum page cap

Robots:

- allowed
- disallowed
- unknown
- crawl delay
- extreme delay capped

HTTP safety:

- valid public HTTPS page
- unsupported scheme rejected
- credentials rejected
- localhost rejected
- private IPv4 rejected
- private IPv6 rejected
- redirect to private host rejected
- redirect limit
- oversized response
- non-HTML response
- timeout
- transient retry
- non-transient failure without retry
- Retry-After handling

HTML validation:

- valid HTML
- malformed HTML
- empty response
- binary signature
- incorrect content type
- encoding detection
- truncated content

Cleaning:

- removes scripts
- removes styles
- removes event handlers
- removes tracking payloads
- preserves headings
- preserves forms
- preserves links
- preserves tables
- deterministic output

Text extraction:

- headings
- lists
- tables
- image alt text
- whitespace normalization
- truncation
- repeated boilerplate reduction

Metadata:

- title
- description
- canonical
- language
- robots meta
- OG metadata
- generator
- script hosts
- framework markers

Hashing and change detection:

- identical raw content
- different whitespace
- dynamic IDs
- meaningful text change
- HTTP 304
- unchanged structural content
- previous page linkage

Browser fallback detection:

- normal server-rendered page
- empty app shell
- React shell
- Vue shell
- Next.js hydration shell
- high script-to-text ratio
- manual browser requirement
- deterministic rule IDs

Storage:

- safe paths
- atomic writes
- hash verification
- path traversal rejected
- opaque references
- inline threshold
- external threshold

Application service with fakes:

- successful run
- one page failure
- robots-blocked page
- homepage failure
- conditional unchanged page
- browser-required detection
- optional browser fetch success
- optional browser fetch failure preserving HTTP result
- cancellation
- duplicate active run
- retry failed targets
- company status update
- accurate summary
- idempotent retry

API schema tests:

- camelCase serialization
- no filesystem path exposure
- no raw HTML by default
- pagination
- enum serialization
- failed target filtering

19. Integration tests

Use local fake HTTP servers rather than public internet access.

Cover:

- redirect chain
- gzip HTML
- conditional ETag request
- Last-Modified request
- 304 response
- 429 with Retry-After
- transient 503 then success
- oversized streamed response
- malformed Content-Type
- robots delay
- local content storage round trip
- Mongo repository behavior if Mongo test infrastructure already exists

Do not write tests that depend on live third-party websites.

20. Fixtures

Create sanitized fixtures:

fixtures/crawling/
- page-homepage.html
- page-about.html
- page-wholesale.html
- page-contact.html
- page-malformed.html
- page-empty-shell.html
- page-react-shell.html
- page-vue-shell.html
- page-next-shell.html
- page-cloudflare-challenge.html
- page-access-denied.html
- page-password-storefront.html
- page-heavy-scripts.html
- page-dynamic-content-v1.html
- page-dynamic-content-v2.html
- page-meaningful-change.html
- page-non-utf8.html
- page-large.html

21. Recommended local defaults

Use configuration values rather than literals throughout the implementation.

Suggested defaults:

- maximum pages per company: 30
- maximum product pages: 5
- maximum collection/category pages: 8
- maximum unknown pages: 3
- concurrency per company: 1
- default delay between requests: 1 second
- minimum delay: 500 ms
- maximum honored robots delay: 10 seconds
- maximum Retry-After: 60 seconds
- connect timeout: 5 seconds
- read timeout: 15 seconds
- total timeout: 20 seconds
- maximum attempts: 3
- maximum redirects: 5
- maximum HTML response: 5 MB
- maximum extracted text: 250,000 characters
- inline cleaned HTML limit: 250 KB
- inline extracted text limit: 250 KB
- browser policy: detect_only
- raw content storage: external local filesystem

22. Constraints

Do not implement:

- website discovery
- StoreLeads import
- structured business extraction
- company facts
- evidence records
- AI analysis
- scoring
- ranking
- frontend pages
- production deployment
- CI/CD
- authentication
- distributed crawling
- proxy rotation
- CAPTCHA solving
- anti-bot bypass
- stealth browser techniques

Do not attempt to bypass website protections.

Do not use a full crawler framework unless one is already approved in the
repository.

Prefer small, focused components.

23. Before implementation

1. Inspect the repository.
2. Identify existing HTTP, configuration, MongoDB, logging, storage, and
   ID-generation patterns.
3. Identify public Company and Discovery application interfaces.
4. Identify whether a browser worker or Playwright adapter already exists.
5. Produce a short implementation plan.
6. List files to be created or modified.
7. Report required changes outside the allowed paths instead of making them.

24. After implementation

Report:

- files created or modified
- commands run
- tests and results
- target-selection behavior
- HTTP safety controls implemented
- robots behavior
- retry policy
- change-detection behavior
- storage behavior
- browser fallback detection
- known limitations
- required integration steps