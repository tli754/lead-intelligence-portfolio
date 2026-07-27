Task 005 — Implement Website Discovery Module

You are implementing the Website Discovery module for the
eCommerce Opportunity Intelligence project.

Other worktrees may be implementing:

- frontend mock pages
- Company module
- StoreLeads import module

Keep this task isolated to the discovery module.

Allowed paths:

- backend/app/modules/discovery/**
- backend/tests/unit/discovery/**
- backend/tests/integration/discovery/**
- fixtures/discovery/**

Do not modify:

- frontend/**
- backend/app/modules/companies/**
- backend/app/modules/imports/**
- backend/app/main.py
- shared root configuration files
- tools/**
- crawler, extraction, evidence, AI, scoring, or ranking modules

If a dependency or central router change is required outside the allowed paths,
report it as an integration step instead of making it.

Architecture:

- modular monolith
- Domain → Application → Infrastructure → API
- domain and application code must not depend on FastAPI or MongoDB
- HTTP fetching belongs in infrastructure
- discovery must not access the companies MongoDB collection directly
- discovery must use public company and repository interfaces
- use strict typing
- use timezone-aware UTC timestamps
- all network operations must have timeouts and response-size limits
- website content must be treated as untrusted input

Do not use Playwright in this task.
Discovery should use normal HTTP requests only.
Browser-rendered discovery will be added later if required.

Implement the following.

1. Discovery domain models

Create:

DiscoveryRun
DiscoveredUrl
DiscoverySource
DiscoveryStatus
PageType
DiscoveryPriority
UrlValidationResult
DiscoverySummary

DiscoveryRun fields:

- discovery_run_id
- company_id
- root_domain
- homepage_url
- status
- started_at
- completed_at
- summary
- error
- created_at
- updated_at

DiscoveryStatus values:

- queued
- running
- completed
- completed_with_warnings
- failed

DiscoveredUrl fields:

- discovered_url_id
- discovery_run_id
- company_id
- url
- normalized_url
- page_type
- page_type_confidence
- priority
- discovery_sources
- source_urls
- anchor_texts
- depth
- is_same_domain
- is_allowed
- first_discovered_at
- last_discovered_at
- metadata

DiscoverySource values:

- homepage
- navigation
- footer
- body_link
- robots
- sitemap
- sitemap_index
- canonical
- alternate
- redirect

PageType values:

- homepage
- about
- contact
- wholesale
- trade
- careers
- shipping
- click_and_collect
- store_locator
- returns
- faq
- support
- blog
- news
- team
- brands
- subscription
- product
- collection
- category
- privacy
- terms
- account
- cart
- checkout
- search
- unknown

DiscoveryPriority values:

- 1
- 2
- 3
- excluded

DiscoverySummary fields:

- URLs found
- URLs accepted
- URLs excluded
- sitemap URLs found
- robots URLs found
- duplicate URLs merged
- warnings
- duration_ms

Use snake_case internally and camelCase only in HTTP schemas.

2. URL normalization

Create a deterministic URL normalizer.

Requirements:

- support http and https only
- lowercase scheme and hostname
- remove URL fragments
- remove default ports
- remove trailing slash except for root
- normalize repeated slashes in path
- preserve query strings only when explicitly allowed
- remove common tracking query parameters:
  - utm_source
  - utm_medium
  - utm_campaign
  - utm_term
  - utm_content
  - gclid
  - fbclid
- sort retained query parameters
- reject:
  - javascript:
  - mailto:
  - tel:
  - data:
  - file:
  - ftp:
  - localhost
  - IP addresses
  - private/internal hosts
  - credentials in URLs
  - malformed URLs
- safely handle internationalized domains
- resolve relative URLs against the source page
- preserve meaningful subdomains
- identify same-domain and same-registrable-domain relationships

Do not fetch DNS in domain logic.

3. Homepage URL resolution

Given an imported company domain, try homepage candidates in this order:

- https://{domain}
- https://www.{domain}
- http://{domain}
- http://www.{domain}

Requirements:

- follow redirects within a safe redirect limit
- validate each redirect target
- reject redirects to private/internal hosts
- record the final homepage URL
- record redirect history
- prefer HTTPS when valid
- use configurable connect/read timeouts
- use configurable maximum response size
- accept HTML responses only
- return typed failure reasons

Do not retry indefinitely.

4. Homepage link extraction

Parse the resolved homepage HTML.

Extract links from:

- header
- navigation elements
- footer
- main body
- canonical link
- alternate links

For each link capture:

- href
- resolved URL
- anchor text
- element context
- source URL
- approximate depth

Requirements:

- tolerate malformed HTML
- ignore empty href values
- ignore non-web schemes
- merge duplicate normalized URLs
- retain all discovery sources and anchor text evidence
- do not execute JavaScript

Use a parser already approved by the project where available.
Do not add a browser dependency.

5. robots.txt discovery

Request:

/robots.txt

Requirements:

- support missing robots.txt
- parse Sitemap directives case-insensitively
- capture multiple sitemap URLs
- do not treat a missing robots file as failure
- store warnings for malformed directives
- do not implement full crawling permission enforcement yet, but expose a
  robots policy result that a future crawler can use
- use the same SSRF and response-size protections as homepage fetching

6. Sitemap discovery

Support:

- XML sitemap
- sitemap index
- nested sitemap indexes
- gzip-compressed sitemap responses
- plain-text sitemap lists where practical

Requirements:

- configurable maximum sitemap files
- configurable maximum sitemap nesting depth
- configurable maximum URLs per discovery run
- prevent recursive loops
- normalize all discovered URLs
- reject off-domain sitemap entries by default
- retain source sitemap URL
- record parsing warnings
- tolerate namespaces
- do not download product pages
- only parse sitemap documents

Priority should be given to sitemap entries likely to represent useful page
types rather than storing every product URL.

For very large product sitemaps:

- keep aggregate counts
- retain only a configurable sample
- identify that a product sitemap exists
- do not enqueue tens of thousands of product URLs

7. Page-type classification

Implement deterministic classification based on:

- normalized path
- anchor text
- URL filename
- sitemap context
- common multilingual English patterns where practical

Examples:

about:
- /about
- /about-us
- /our-story

contact:
- /contact
- /contact-us
- /get-in-touch

wholesale:
- /wholesale
- /wholesale-enquiries
- /become-a-stockist

trade:
- /trade
- /trade-account
- /trade-application

careers:
- /careers
- /jobs
- /work-with-us

shipping:
- /shipping
- /delivery
- /shipping-information

click_and_collect:
- /click-and-collect
- /pickup
- /store-pickup

store_locator:
- /stores
- /store-locator
- /locations
- /our-stores

returns:
- /returns
- /refund-policy
- /returns-and-exchanges

faq:
- /faq
- /faqs
- /frequently-asked-questions

support:
- /support
- /help
- /help-centre

blog:
- /blog
- /journal
- /articles

news:
- /news
- /press
- /media

team:
- /team
- /our-team
- /people

brands:
- /brands
- /our-brands

subscription:
- /subscription
- /subscribe

product:
- /products/
- /product/

collection:
- /collections/

category:
- /category/
- /categories/

privacy:
- /privacy
- /privacy-policy

terms:
- /terms
- /terms-and-conditions

Assign a confidence value from 0 to 100.

Classification rules must be versioned.

Do not use AI classification in this task.

8. Priority assignment

Priority 1:

- homepage
- about
- contact
- wholesale
- trade
- careers
- shipping
- click_and_collect
- store_locator

Priority 2:

- returns
- faq
- support
- blog
- news
- team
- brands
- subscription

Priority 3:

- product
- collection
- category
- privacy
- terms
- unknown URLs that appear potentially useful

Excluded:

- account
- login
- cart
- checkout
- search results
- password reset
- tracking URLs
- external domains
- image files
- video files
- fonts
- stylesheets
- JavaScript files
- downloadable binaries unless specifically useful later

Allow priority overrides through configuration rather than hardcoding them
throughout the application.

9. Deduplication and reconciliation

When the same normalized URL is found from several sources:

- store one DiscoveredUrl
- merge discovery sources
- merge anchor texts
- merge source URLs
- keep the strongest page-type confidence
- keep the highest priority
- keep the shallowest depth
- preserve warnings or conflicts

Examples:

A URL found in navigation and sitemap should contain both sources.

If page-type classifiers disagree:

- retain the selected page type
- retain alternative classifications in metadata
- record the rule identifiers used

10. Discovery application service

Create a service such as:

WebsiteDiscoveryService

Responsibilities:

- obtain company domain through a CompanyDiscoveryGateway
- create a discovery run
- resolve homepage
- fetch homepage
- extract links
- inspect robots.txt
- inspect sitemaps
- normalize and reconcile URLs
- classify page types
- assign priorities
- persist results
- update run status
- return a summary

The service must support cancellation between major steps.

A single failed sitemap must not fail the entire discovery run.

A homepage failure should fail the run because discovery cannot continue
reliably.

11. Integration ports

Define narrow protocols.

CompanyDiscoveryGateway:

- get_company_domain(company_id)
- update_latest_discovery_run(company_id, discovery_run_id)
- update_processing_status(company_id, status)

DiscoveryRepository:

- create_run
- update_run
- save_discovered_urls
- get_run
- list_discovered_urls
- find_existing_url

HttpDiscoveryClient:

- fetch_html
- fetch_text
- fetch_binary
- resolve_homepage

Do not depend on a concrete Company MongoDB repository.

If the Company module is unavailable in the current worktree, use a fake gateway
for tests and report the adapter as an integration step.

12. Persistence

Implement a MongoDB discovery repository only if the project already has an
approved MongoDB infrastructure pattern available in this worktree.

Collections:

discoveries
discovery_runs

Recommended indexes:

discovery_runs:
- discovery_run_id unique
- company_id
- status
- started_at

discoveries:
- discovered_url_id unique
- compound unique:
  - discovery_run_id
  - normalized_url
- company_id
- page_type
- priority
- normalized_url

Do not store raw homepage HTML in the discoveries collection.

If shared MongoDB wiring would require modifying files outside scope, create the
repository implementation and expose its constructor, but leave central
dependency wiring for integration.

13. HTTP safety and SSRF protection

Mandatory:

- allow only HTTP and HTTPS
- reject private IPv4 and IPv6 ranges
- reject loopback
- reject link-local
- reject multicast
- reject reserved ranges
- reject localhost names
- validate every redirect
- set connect and read timeouts
- cap redirect count
- cap response size
- validate Content-Type
- use a controlled User-Agent
- limit concurrent requests per company
- do not send cookies
- do not persist authentication headers
- do not log raw response bodies

DNS rebinding protection should be supported by the infrastructure design.
If full enforcement is not practical in this ticket, document the exact
remaining risk.

14. API schemas and router

Create but do not centrally register the discovery router.

Endpoints:

POST /api/companies/{company_id}/discovery-runs

Response:

{
"data": {
"discoveryRunId": "discovery_run_123",
"companyId": "company_123",
"status": "completed",
"summary": {
"urlsFound": 46,
"urlsAccepted": 18,
"urlsExcluded": 28,
"sitemapUrlsFound": 32,
"robotsUrlsFound": 2,
"duplicateUrlsMerged": 7,
"warnings": 1,
"durationMs": 842
}
}
}

GET /api/companies/{company_id}/discovery-runs/latest

GET /api/discovery-runs/{discovery_run_id}

GET /api/discovery-runs/{discovery_run_id}/urls

URL list query parameters:

- page
- pageSize
- priority
- pageType
- source
- includeExcluded

Use camelCase in API JSON.

The POST endpoint may execute synchronously for development if the discovery
service is fast enough, but the application service must not depend on FastAPI.
The future worker should be able to call the same service.

Do not use FastAPI BackgroundTasks.

15. Tests

Unit tests:

URL normalization:

- absolute HTTPS URL
- relative URL
- fragments removed
- default ports removed
- tracking parameters removed
- retained query parameters sorted
- www handling
- meaningful subdomains preserved
- internationalized domain handling
- malformed URL rejected
- localhost rejected
- private IPv4 rejected
- private IPv6 rejected
- credentials rejected
- unsupported schemes rejected

Homepage resolution:

- HTTPS succeeds first
- www fallback
- HTTP fallback
- safe redirect
- redirect loop
- redirect to private host rejected
- non-HTML response rejected
- oversized response rejected
- timeout returns typed failure

HTML extraction:

- navigation links
- footer links
- relative links
- duplicate links
- canonical link
- malformed HTML
- empty href
- mailto and tel ignored

robots.txt:

- one sitemap
- multiple sitemaps
- mixed-case directives
- missing robots
- malformed directive

Sitemap:

- normal URL set
- sitemap index
- nested index
- namespace handling
- gzip sitemap
- duplicate sitemap entries
- recursion loop
- off-domain URLs
- maximum file limit
- maximum URL limit
- large product sitemap sampling

Classification:

- each page type
- ambiguous paths
- anchor-text influence
- excluded pages
- confidence calculation
- deterministic results

Reconciliation:

- duplicate URLs merged
- multiple sources retained
- strongest confidence selected
- highest priority retained
- shallowest depth retained

Application tests using fakes:

- successful discovery run
- homepage failure
- robots failure with continued execution
- one sitemap failure with continued execution
- duplicate-safe retry
- company status update
- run summary accuracy
- cancellation between steps

API schema tests:

- camelCase serialization
- pagination
- enum serialization
- excluded URL filtering

16. Fixtures

Create sanitized fixtures:

fixtures/discovery/
- homepage-basic.html
- homepage-navigation-footer.html
- homepage-malformed.html
- homepage-duplicate-links.html
- robots-basic.txt
- robots-multiple-sitemaps.txt
- sitemap-basic.xml
- sitemap-index.xml
- sitemap-nested.xml
- sitemap-products-large.xml
- sitemap-malformed.xml

17. Constraints

Do not implement:

- full website crawling
- page-content storage
- Playwright
- JavaScript rendering
- structured business extraction
- evidence records
- AI analysis
- scoring
- ranking
- frontend pages
- authentication
- deployment
- CI/CD

Do not add a broad crawler framework unless the repository already uses one.
Prefer small focused HTTP and parsing components.

18. Before implementation

1. Inspect the repository.
2. Identify existing HTTP, MongoDB, configuration, logging, and ID-generation
   patterns.
3. Identify any existing Company public application interface.
4. Produce a short implementation plan.
5. List files to be created or modified.
6. Report required changes outside allowed paths rather than making them.

19. After implementation

Report:

- files created or modified
- commands run
- tests and results
- supported discovery sources
- SSRF protections implemented
- sitemap limits used
- known limitations
- required integration steps