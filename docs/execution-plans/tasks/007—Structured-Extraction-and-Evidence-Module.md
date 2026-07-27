Task 007 — Implement Structured Extraction and Evidence Modules

You are implementing the Structured Extraction and Evidence modules for the
eCommerce Opportunity Intelligence project.

Other worktrees may be implementing:

- frontend mock pages
- Company module
- StoreLeads import
- Website Discovery
- Website Crawling

Keep this task isolated to extraction and evidence.

Allowed paths:

- backend/app/modules/extraction/**
- backend/app/modules/evidence/**
- backend/tests/unit/extraction/**
- backend/tests/unit/evidence/**
- backend/tests/integration/extraction/**
- backend/tests/integration/evidence/**
- fixtures/extraction/**

Do not modify:

- frontend/**
- backend/app/modules/companies/**
- backend/app/modules/imports/**
- backend/app/modules/discovery/**
- backend/app/modules/crawling/**
- backend/app/main.py
- backend/app/api/**
- tools/**
- analysis, scoring, ranking, workflow, or shared root configuration files

If a central dependency, router registration, shared package, Company projection,
or MongoDB wiring change is required outside the allowed paths, report it as an
integration step instead of making it.

Architecture:

- modular monolith
- Domain → Application → Infrastructure → API
- domain and application code must not depend on FastAPI, MongoDB, Redis,
  HTTP clients, browser tools, or AI SDKs
- extractors must be deterministic and pure where practical
- extractors must not perform network requests
- extraction must consume crawled page data through narrow ports
- evidence must be first-class and independently queryable
- every accepted fact must reference one or more evidence records
- unknown must remain unknown
- absence of evidence must not be converted into a negative fact
- use strict typing
- use timezone-aware UTC timestamps
- all page content must be treated as untrusted input

Do not use AI in this task.

Implement the following.

1. Extraction domain models

Create:

ExtractionRun
ExtractionStatus
ExtractorDefinition
ExtractorExecution
FactCandidate
FactRecord
FactValue
FactStatus
FactSourceType
FactConflict
ExtractionWarning
ExtractionSummary
FieldPath
ConfidenceScore
VerificationState

ExtractionStatus values:

- queued
- running
- completed
- completed_with_warnings
- partial
- failed
- cancelled
- stale

VerificationState values:

- verified
- measured
- inferred
- unknown
- conflicting
- stale

FactStatus values:

- candidate
- accepted
- rejected
- superseded
- conflicting
- stale

FactSourceType values:

- json_ld
- open_graph
- meta_tag
- html_element
- link
- form
- script_marker
- cookie_marker
- page_metadata
- sitemap_summary
- deterministic_inference
- imported
- manual

ExtractionRun fields:

- extraction_run_id
- company_id
- crawl_run_id
- status
- extractor_version
- reconciliation_version
- started_at
- completed_at
- configuration_snapshot
- summary
- warnings
- error
- created_at
- updated_at

ExtractorDefinition fields:

- extractor_id
- name
- version
- supported_page_types
- output_field_paths
- priority
- enabled

ExtractorExecution fields:

- extractor_execution_id
- extraction_run_id
- page_id
- extractor_id
- extractor_version
- status
- candidates_produced
- warnings
- duration_ms
- started_at
- completed_at

FactCandidate fields:

- candidate_id
- extraction_run_id
- company_id
- page_id
- field_path
- value
- normalized_value
- value_type
- source_type
- extractor_id
- extractor_version
- confidence
- verification_state
- evidence_ids
- qualifiers
- observed_at
- created_at

FactRecord fields:

- fact_id
- company_id
- extraction_run_id
- field_path
- value
- normalized_value
- value_type
- status
- verification_state
- confidence
- evidence_ids
- selected_candidate_ids
- conflicting_candidate_ids
- source_count
- first_observed_at
- last_observed_at
- last_verified_at
- extractor_versions
- reconciliation_rule_ids
- created_at
- updated_at

FactConflict fields:

- conflict_id
- company_id
- extraction_run_id
- field_path
- candidate_ids
- selected_candidate_id
- conflict_type
- resolution
- rule_ids
- created_at

ExtractionSummary fields:

- pages_considered
- pages_processed
- pages_skipped
- extractor_executions
- candidates_created
- facts_accepted
- facts_conflicting
- facts_unknown
- evidence_created
- warnings
- duration_ms

Use snake_case internally and camelCase only in API schemas.

2. Evidence domain models

Create:

EvidenceRecord
EvidenceType
EvidenceLocation
EvidenceExcerpt
EvidenceStrength
EvidenceStatus
EvidenceReference

EvidenceType values:

- page_text
- html_attribute
- json_ld
- meta_tag
- link_target
- form_field
- script_marker
- cookie_marker
- page_metadata
- sitemap_metadata
- imported_value
- deterministic_inference
- manual_observation

EvidenceStatus values:

- active
- superseded
- stale
- unavailable
- rejected

EvidenceStrength values:

- weak
- moderate
- strong
- authoritative

EvidenceRecord fields:

- evidence_id
- company_id
- extraction_run_id
- page_id
- fact_field_path
- evidence_type
- status
- strength
- source_url
- normalized_source_url
- page_type
- extractor_id
- extractor_version
- location
- excerpt
- raw_value
- normalized_value
- content_hash
- observed_at
- last_verified_at
- created_at
- updated_at
- metadata

EvidenceLocation fields:

- selector
- xpath
- json_path
- attribute
- line_start
- line_end
- section_heading
- element_tag

EvidenceExcerpt fields:

- text
- prefix
- suffix
- truncated
- start_offset
- end_offset

Requirements:

- evidence excerpts must be concise
- do not store full page HTML in evidence
- store enough location information to reproduce the extraction
- evidence must link back to the crawled page
- evidence records must be immutable except for status and verification metadata
- changes should create new evidence rather than rewriting historical evidence

3. Field-path catalogue

Create a typed, versioned catalogue of supported fields.

Identity:

- identity.company_name
- identity.trading_name
- identity.platform
- identity.country
- identity.city
- identity.language

Business:

- business.wholesale
- business.trade_accounts
- business.click_and_collect
- business.subscription
- business.booking
- business.online_only
- business.custom_products
- business.brands

Catalogue:

- catalogue.product_count
- catalogue.product_count_estimate
- catalogue.sku_count_estimate
- catalogue.variant_evidence
- catalogue.collection_count
- catalogue.bundle_evidence
- catalogue.customization_evidence

Physical operations:

- operations.retail_store_count
- operations.showroom_count
- operations.warehouse_count
- operations.office_count
- operations.pickup_available
- operations.returns_location_count
- operations.locations

Technology:

- technology.commerce_platform
- technology.payment_providers
- technology.crm
- technology.erp
- technology.accounting
- technology.review_platforms
- technology.support_tools
- technology.analytics
- technology.loyalty
- technology.email_marketing
- technology.ai_signals
- technology.frameworks

Organisation:

- organisation.emails
- organisation.phone_numbers
- organisation.people
- organisation.internal_it_status
- organisation.recommended_contact_candidates

Growth:

- growth.hiring
- growth.expansion
- growth.new_store
- growth.warehouse_change
- growth.platform_migration
- growth.new_category
- growth.subscription_launch

Each field definition should include:

- field path
- value type
- cardinality
- allowed verification states
- merge strategy
- freshness policy
- minimum accepted confidence
- sensitive-data flag where applicable
- description

Do not use arbitrary string field paths throughout the code.

4. Extractor interface

Create a pure extractor protocol:

Extractor

Methods:

- definition
- supports(page_context)
- extract(page_context) -> list[FactCandidateDraft]

PageContext should contain only the data required for extraction:

- page_id
- company_id
- source_url
- normalized_url
- page_type
- cleaned_html
- extracted_text
- page_metadata
- raw_technology_signals
- fetched_at
- content_hashes

Extractors must:

- never perform network requests
- never access MongoDB
- never mutate page input
- return candidates and evidence drafts
- include extractor ID and version
- produce deterministic output for the same input
- emit structured warnings rather than logging and continuing silently

5. Identity extractors

Implement deterministic extractors.

Company name priority:

1. Organisation JSON-LD name
2. WebSite JSON-LD name
3. Open Graph site_name
4. homepage title pattern
5. logo alt text
6. about-page heading
7. domain fallback as low-confidence inference

Trading name:

- alternateName in JSON-LD
- explicit “trading as” patterns
- footer legal text where reliable

Country and city:

- PostalAddress JSON-LD
- contact-page address blocks
- store-location structured data
- footer address
- page locale and TLD only as low-confidence supporting signals

Language:

- html lang
- content-language metadata
- deterministic text-language marker only if already available locally

Requirements:

- preserve conflicts
- do not treat TLD as verified country
- do not infer city from phone area code
- legal company name and trading name must remain distinguishable

6. Business-model extractors

Implement extractors for:

Wholesale:

Positive signals:

- wholesale application
- wholesale enquiry
- become a stockist
- wholesale pricing
- retailer application
- wholesale account login

Trade accounts:

Positive signals:

- trade account
- trade application
- trade pricing
- professional account
- commercial account

Click and collect:

Positive signals:

- click and collect
- store pickup
- pick up in store
- collection available

Subscription:

Positive signals:

- subscribe and save
- recurring delivery
- product subscription
- membership delivery plan

Booking:

Positive signals:

- book appointment
- booking form
- schedule consultation
- reserve session

Online only:

Only accept when explicitly stated, such as:

- online-only store
- exclusively online
- no physical retail location

Do not infer online_only merely because no store page was found.

Custom products:

Positive signals:

- personalization
- custom engraving
- made to order
- custom printing
- bespoke product
- upload artwork

Brands:

Extract explicit brand lists from:

- brand pages
- navigation
- structured data
- product brand fields

Requirements:

- boolean fields should support true and unknown
- false requires explicit negative evidence or manual confirmation
- preserve source wording
- avoid matching unrelated uses of words such as “trade” or “subscription”

7. Catalogue extractors

Implement deterministic catalogue estimators.

Sources:

- discovery sitemap summaries
- crawled collection/category pages
- crawled sampled product pages
- page metadata
- pagination controls
- platform-specific embedded data already present in crawled content

Product count priority:

1. exact sitemap URL count classified as products
2. exact platform-provided total in local page data
3. pagination-derived estimate
4. sampled collection estimate
5. unknown

Collection count:

- sitemap classification count
- navigation/category listing count
- structured menu data

SKU estimate:

- exact local structured data where available
- product count multiplied by observed median variants only when enough samples
  exist
- otherwise unknown

Variant evidence:

- variant selectors
- product JSON-LD offers
- embedded variant arrays

Bundle evidence:

- bundle
- set
- kit
- multipack
- build-your-own

Customization evidence:

- personalization form controls
- engraving fields
- file upload fields
- custom text inputs

Requirements:

- distinguish exact values from estimates
- record estimation method
- store sample size
- attach confidence
- do not extrapolate from one product unless explicitly marked low confidence
- do not count collection URLs as products

8. Physical-operations extractors

Extract:

- retail stores
- showrooms
- warehouses
- offices
- pickup locations
- return locations

Sources:

- LocalBusiness and Store JSON-LD
- store-locator pages
- contact pages
- footer
- shipping and returns pages
- explicit warehouse/showroom wording

Create structured location candidates:

- location_type
- name
- address_line
- suburb
- city
- region
- postal_code
- country
- phone
- latitude
- longitude
- source wording

Requirements:

- deduplicate locations by normalized address and name
- distinguish stockists from company-owned retail stores
- distinguish warehouse from retail store
- do not count the same address in footer and contact page twice
- preserve uncertain ownership status
- retain raw address text
- do not geocode in this task

9. Technology-signal extractors

Consume raw technology signals from crawled pages.

Detect candidates for:

Commerce:

- Shopify
- WooCommerce
- Magento
- BigCommerce
- Shopline
- Squarespace Commerce
- Wix Stores
- custom/unknown

Payments:

- Stripe
- PayPal
- Afterpay
- Klarna
- Laybuy
- Windcave
- Shopify Payments
- Apple Pay
- Google Pay

CRM and marketing:

- HubSpot
- Salesforce
- Klaviyo
- Mailchimp
- ActiveCampaign

ERP and accounting:

- Odoo
- NetSuite
- Xero
- MYOB
- Cin7
- Unleashed

Reviews:

- Yotpo
- Judge.me
- Reviews.io
- Trustpilot
- Stamped

Support:

- Zendesk
- Gorgias
- Intercom
- Tidio
- Freshdesk

Analytics:

- Google Analytics
- Google Tag Manager
- Meta Pixel
- Hotjar
- Microsoft Clarity

Loyalty:

- Smile.io
- LoyaltyLion
- Yotpo Loyalty

Frameworks:

- React
- Vue
- Nuxt
- Next.js
- Angular
- Svelte

Evidence sources:

- script hosts
- script paths
- generator meta
- HTML markers
- cookie names supplied by page context
- inline configuration keys
- form endpoints
- known widget element IDs/classes

Requirements:

- signature rules must be versioned
- each technology requires one or more rule IDs
- confidence depends on signal quality
- agreement across pages raises confidence
- generic CDN usage must not prove a product
- framework detection must not be treated as internal technical capability
- absence of a signature does not mean the technology is absent

10. Organisation extractors

Emails:

- visible mailto links
- visible email text
- structured data
- contact pages
- footer

Phones:

- tel links
- structured data
- visible phone text

Normalize but preserve originals.

People:

Extract only explicitly named people with role context from:

- team pages
- about pages
- contact pages
- structured data
- careers leadership references

Person candidate fields:

- name
- role_title
- role_category
- email
- phone
- source_url
- confidence

Role categories:

- owner
- founder
- executive
- operations
- ecommerce
- marketing
- technology
- customer_service
- sales
- unknown

Internal IT status:

Allowed values:

- detected
- not_detected
- unknown

Rules:

- detected requires explicit technical staff, technology leadership, engineering
  careers, or internal-development wording
- not_detected must not be inferred from absence alone
- unknown is the default
- external agency credits may support external-maintenance evidence but do not
  prove no internal IT

Recommended contact candidates:

Create candidates only, not a final recommendation.

Priority signals:

1. ecommerce leadership
2. operations leadership
3. owner/founder for small businesses
4. technology leadership
5. marketing leadership
6. general contact

Do not use AI to choose the final contact.

11. Growth-signal extractors

Extract time-sensitive signals from:

- careers
- news
- blog
- homepage banners
- press releases
- store pages

Signal types:

- hiring
- opening a new store
- moving warehouse
- expanding distribution
- platform migration
- launching subscriptions
- entering a new category
- international expansion
- acquisition or merger
- major rebrand

Growth signal fields:

- signal_type
- statement
- event_date
- publication_date
- effective_date
- status
- source_url
- confidence

Requirements:

- distinguish publication date from event date
- do not treat old announcements as current
- mark stale signals according to freshness policy
- avoid interpreting routine job vacancies as major expansion without supporting
  context
- preserve the original statement as evidence excerpt

12. Pattern matching standards

Centralize pattern definitions.

Each pattern must have:

- rule_id
- version
- field_path
- positive patterns
- negative patterns
- context requirements
- supported page types
- base confidence
- evidence strength
- notes

Avoid:

- broad substring matching
- regexes without boundaries
- matching navigation labels without context
- treating one ambiguous keyword as strong evidence

All patterns require tests for false positives.

13. Evidence creation

Every candidate accepted for reconciliation must have at least one evidence
record.

Evidence factory responsibilities:

- create stable evidence IDs
- capture page reference
- capture selector or JSON path when available
- produce a concise excerpt
- include prefix and suffix context
- hash the relevant source fragment
- mark evidence strength
- preserve raw and normalized values
- cap excerpt length

Recommended excerpt limits:

- primary text: 300 characters
- prefix: 120 characters
- suffix: 120 characters

Requirements:

- no full HTML
- no scripts containing secrets or tokens
- redact obvious email tracking tokens
- redact URL query parameters likely to contain personal data
- preserve business contact details when they are the extracted fact
- evidence creation must be deterministic

14. Confidence policy

Implement a versioned deterministic confidence policy.

Inputs:

- source authority
- extractor reliability
- page type relevance
- directness
- number of agreeing sources
- freshness
- conflict penalty
- inference penalty

Suggested source authority examples:

- explicit JSON-LD organisation name: high
- direct visible contact-page statement: high
- navigation label: moderate
- script marker: moderate to high depending on signature
- domain or TLD inference: low

Suggested confidence behavior:

- direct authoritative single source may exceed 85
- two independent agreeing strong sources may exceed 90
- inferred values should usually remain below 75
- ambiguous keyword matches should remain below acceptance threshold
- active conflicts should cap confidence

Use integer confidence from 0 to 100.

Do not accept model-generated confidence.

15. Candidate acceptance thresholds

Configure by field definition.

Suggested defaults:

- authoritative exact fields: 70
- contact information: 70
- boolean capability signals: 65
- technology signals: 70
- catalogue estimates: 55
- growth signals: 65
- deterministic inferences: 50

Below-threshold candidates should remain available for debugging but must not
become accepted facts.

16. Reconciliation engine

Create a deterministic reconciliation engine.

Responsibilities:

- group candidates by company and field path
- normalize comparable values
- merge agreeing candidates
- identify conflicts
- rank candidates
- select accepted value or values
- produce FactRecord
- produce FactConflict where needed
- mark superseded candidates
- apply confidence policy
- preserve all evidence references

Reconciliation considerations:

- source authority
- confidence
- freshness
- page relevance
- number of independent pages
- extractor priority
- exact versus inferred
- manual versus automated
- imported versus discovered

Rules:

- manual verified value overrides automated values
- explicit JSON-LD may override weak title inference
- store-locator structured data may override footer location count
- recent explicit evidence may override stale evidence
- conflicting strong sources should remain conflicting
- a conflict must not be silently resolved only because one candidate appeared
  first
- array fields should merge deduplicated compatible values
- scalar fields should select one value or remain conflicting
- boolean false requires explicit negative evidence
- unknown must be emitted when no candidate passes threshold

Merge strategies:

- scalar_preferred
- scalar_conflict_preserving
- boolean_positive_only
- boolean_explicit
- set_union
- structured_entity_merge
- numeric_exact_or_estimate
- time_series

Reconciliation rules must be versioned and identified by rule IDs.

17. Specific reconciliation rules

Company name:

- Organisation JSON-LD
- WebSite JSON-LD
- OG site name
- page title
- logo alt
- domain fallback

Platform:

- strong commerce signatures across pages
- generator marker
- platform-specific assets
- imported platform as supporting evidence
- conflicts retained

Country and city:

- structured address
- explicit contact address
- store location
- footer address
- imported value
- TLD inference last

Wholesale and trade:

- explicit application/page statement
- navigation and link evidence
- generic word occurrence rejected

Physical locations:

- merge structured entities
- deduplicate normalized addresses
- preserve location type conflicts

Technology arrays:

- set union by normalized product name
- preserve evidence per technology
- keep per-item confidence

Contacts:

- deduplicate email and phone
- merge person records by normalized name plus role
- do not merge unrelated people with the same surname

Catalogue count:

- exact beats estimate
- more recent beats stale
- competing exact counts remain conflicting if materially different
- estimate stores method and range where possible

18. Freshness policy

Create field-specific freshness rules.

Suggested defaults:

- identity: 365 days
- platform: 180 days
- contact information: 180 days
- business capabilities: 180 days
- physical locations: 180 days
- technology: 90 days
- catalogue estimates: 30 days
- growth signals: 90 days
- careers signals: 30 days

Requirements:

- freshness policy must be configurable
- stale evidence remains in history
- stale evidence lowers confidence
- stale facts are not deleted
- extraction runs should be able to mark previous facts stale

19. Extraction application service

Create a service such as:

StructuredExtractionService

Responsibilities:

- validate company and crawl run
- create extraction run
- retrieve eligible crawled pages
- skip failed or unavailable pages
- build PageContext objects
- select applicable extractors
- execute extractors deterministically
- persist extractor execution records
- create candidates
- create evidence
- reconcile candidates
- persist accepted facts and conflicts
- update extraction summary
- update company processing status
- project latest accepted facts through a gateway
- complete, partially complete, fail, or cancel the run

Failure isolation:

- one extractor failure must not fail all extractors for a page
- one page failure must not fail the run
- evidence persistence failure for an accepted fact must prevent that fact from
  being accepted
- reconciliation failure for one field should mark the run partial
- repository failure may fail the run
- cancellation stops new extractor executions and preserves completed work

20. Integration ports

Define narrow protocols.

CompanyExtractionGateway:

- update_latest_extraction_run(company_id, extraction_run_id)
- update_processing_status(company_id, status)
- project_latest_facts(company_id, projection)

CrawlExtractionGateway:

- get_crawl_run(crawl_run_id)
- list_pages(
  crawl_run_id,
  statuses,
  page_types
  )
- load_page_content(page_id, content_kind)

ExtractionRepository:

- create_run
- update_run
- save_extractor_execution
- save_candidates
- save_facts
- save_conflicts
- get_run
- list_facts_by_company
- list_candidates_by_run
- get_latest_fact
- mark_previous_facts_stale

EvidenceRepository:

- save_evidence
- get_evidence
- list_evidence_for_fact
- list_evidence_for_page
- update_evidence_status

Do not import concrete Company or Crawling Mongo repositories.

21. Company projection

Create a projection model inside extraction, but do not modify the Company module
in this worktree.

Projection should include latest accepted values for:

- identity
- business
- catalogue
- operations
- technology
- organisation
- growth
- extraction quality

Each projected field should include:

- value
- verification_state
- confidence
- evidence_ids
- last_verified_at

The integration adapter may later map this to:

companies.latest_facts

or equivalent.

Do not flatten evidence away.

22. Persistence

Implement MongoDB repositories only if an approved MongoDB infrastructure
pattern already exists in the worktree.

Collections:

extraction_runs
extractor_executions
fact_candidates
facts
fact_conflicts
evidence

Recommended indexes:

extraction_runs:
- extraction_run_id unique
- company_id
- crawl_run_id
- status
- started_at

extractor_executions:
- extractor_execution_id unique
- extraction_run_id
- page_id
- extractor_id
- status

fact_candidates:
- candidate_id unique
- company_id
- extraction_run_id
- field_path
- page_id
- status

facts:
- fact_id unique
- company_id
- field_path
- status
- last_verified_at
- compound:
    - company_id
    - field_path
    - status

fact_conflicts:
- conflict_id unique
- company_id
- extraction_run_id
- field_path

evidence:
- evidence_id unique
- company_id
- extraction_run_id
- page_id
- fact_field_path
- status
- source_url

Do not store page HTML in extraction or evidence collections.

23. API schemas and routers

Create but do not centrally register extraction and evidence routers.

Endpoints:

POST /api/companies/{company_id}/extraction-runs

Request:

{
"crawlRunId": "crawl_run_123",
"options": {
"extractorIds": [],
"pageTypes": [],
"forceRefresh": false
}
}

Response:

{
"data": {
"extractionRunId": "extraction_run_123",
"companyId": "company_123",
"crawlRunId": "crawl_run_123",
"status": "completed_with_warnings",
"summary": {
"pagesConsidered": 18,
"pagesProcessed": 16,
"pagesSkipped": 2,
"extractorExecutions": 94,
"candidatesCreated": 61,
"factsAccepted": 27,
"factsConflicting": 2,
"factsUnknown": 8,
"evidenceCreated": 75,
"warnings": 4,
"durationMs": 1243
}
}
}

GET /api/companies/{company_id}/extraction-runs/latest

GET /api/extraction-runs/{extraction_run_id}

GET /api/extraction-runs/{extraction_run_id}/facts

GET /api/extraction-runs/{extraction_run_id}/candidates

GET /api/companies/{company_id}/facts

GET /api/facts/{fact_id}

GET /api/facts/{fact_id}/evidence

GET /api/evidence/{evidence_id}

Fact-list query parameters:

- page
- pageSize
- fieldPath
- status
- verificationState
- minimumConfidence
- includeStale
- includeConflicting

Evidence-list query parameters:

- page
- pageSize
- evidenceType
- strength
- status
- pageId
- fieldPath

API responses must:

- use camelCase
- never include full page HTML
- include concise evidence excerpts
- include source URLs
- expose extractor and rule versions
- distinguish unknown from false
- distinguish exact values from estimates
- preserve conflicts

Do not use FastAPI BackgroundTasks.

24. Tests

Unit tests: field catalogue

- valid field definitions
- unique field paths
- merge strategies
- confidence thresholds
- freshness policies
- typed value validation

Unit tests: extractors

Identity:

- Organisation JSON-LD name
- WebSite JSON-LD name
- OG site name
- title fallback
- logo alt fallback
- trading name
- structured address
- conflicting city
- TLD as low-confidence support only

Business:

- wholesale positive
- wholesale false positive prevention
- trade account positive
- click-and-collect positive
- subscription positive
- booking positive
- explicit online-only
- no online-only inference from missing stores
- custom product positive
- brand extraction

Catalogue:

- exact product sitemap count
- pagination estimate
- variant extraction
- SKU estimate with sufficient sample
- insufficient sample remains unknown
- collection count
- bundle signal
- customization form

Operations:

- JSON-LD store
- multiple stores
- warehouse wording
- showroom wording
- pickup location
- stockist not counted as owned store
- duplicate address merged
- conflicting location types

Technology:

- each major signature family
- generic CDN false positive
- multiple agreeing signals
- conflicting platform markers
- framework versus commerce distinction
- absence remains unknown

Organisation:

- mailto email
- visible email
- tel phone
- named person and role
- role categorization
- internal IT detected
- no internal IT inference from absence
- recommended contact candidate ordering

Growth:

- hiring
- new store
- warehouse move
- migration
- old announcement marked stale
- publication date versus event date
- false-positive prevention

Unit tests: evidence

- deterministic evidence ID
- selector location
- JSON path location
- concise excerpt
- excerpt truncation
- prefix and suffix
- fragment hash
- no full HTML
- URL query redaction
- business email preservation
- immutable evidence behavior

Unit tests: confidence

- source authority
- extractor reliability
- agreement boost
- freshness penalty
- conflict penalty
- inference cap
- confidence clamped to 0–100
- deterministic result

Unit tests: reconciliation

- agreeing scalar candidates
- conflicting strong scalar candidates
- manual override
- JSON-LD beats title
- recent beats stale
- set union
- boolean positive-only
- explicit false
- unknown when below threshold
- exact count beats estimate
- exact count conflict
- location merge
- contact deduplication
- technology per-item confidence
- evidence references preserved
- rule IDs preserved

Application tests with fakes:

- successful extraction run
- one extractor failure
- one page unavailable
- one field reconciliation failure
- evidence failure blocks fact acceptance
- cancellation
- stale previous fact marking
- company projection
- company status updates
- accurate summary
- idempotent retry
- same crawl run and configuration does not duplicate accepted facts

API schema tests:

- camelCase serialization
- unknown distinct from false
- estimate metadata
- conflict representation
- concise evidence only
- pagination
- enum serialization
- version fields exposed

25. Integration tests

Use stored crawl fixtures and fake gateways.

Cover:

- full extraction from homepage, about, contact, wholesale, store locator, and
  product pages
- evidence linked to facts
- conflicts persisted
- stale prior facts
- company projection generated
- Mongo repository behavior where test infrastructure exists
- retry without duplicate facts
- changed page content creates new evidence and supersedes old fact
- unchanged page content does not duplicate evidence unnecessarily

Do not use live websites.

26. Fixtures

Create sanitized fixtures:

fixtures/extraction/
- homepage-shopify.html
- homepage-woocommerce.html
- homepage-magento.html
- homepage-custom.html
- homepage-jsonld-organisation.html
- homepage-conflicting-name.html
- about-company.html
- about-team.html
- contact-address.html
- contact-multiple-locations.html
- wholesale-explicit.html
- wholesale-false-positive.html
- trade-account.html
- click-and-collect.html
- subscription.html
- online-only-explicit.html
- store-locator-owned.html
- store-locator-stockists.html
- warehouse-and-showroom.html
- collection-pagination.html
- product-variants.html
- product-customization.html
- careers-technology.html
- careers-general.html
- news-new-store.html
- news-old-expansion.html
- technology-signatures.html
- technology-conflicting-platforms.html
- structured-data-malformed.html

27. Versioning

Version independently:

- field catalogue
- extractor implementations
- pattern rules
- technology signatures
- evidence format
- confidence policy
- reconciliation rules
- freshness policy
- projection schema

Every extraction run must store all relevant versions.

28. Recommended initial implementation order

Implement in this order:

1. field catalogue
2. extraction and evidence domain models
3. extractor and repository ports
4. evidence factory
5. confidence policy
6. reconciliation engine
7. identity extractors
8. business extractors
9. organisation/contact extractors
10. operations extractors
11. technology extractors
12. catalogue extractors
13. growth extractors
14. application service
15. persistence
16. API schemas
17. integration tests

Do not begin with every extractor at once.

29. Constraints

Do not implement:

- AI-assisted extraction
- AI analysis
- opportunity scoring
- ranking
- outreach
- frontend pages
- website discovery
- page crawling
- browser rendering
- external enrichment
- geocoding
- third-party contact lookup
- authentication
- deployment
- CI/CD

Do not treat missing evidence as a negative fact.

Do not invent company information.

Do not store chain of thought.

30. Before implementation

1. Inspect the repository.
2. Identify existing domain, MongoDB, Pydantic, logging, ID-generation, and
   versioning patterns.
3. Identify public Company and Crawling application interfaces.
4. Review how crawled content references are loaded.
5. Produce a short implementation plan.
6. List files to create or modify.
7. Report required changes outside allowed paths rather than making them.

31. After implementation

Report:

- files created or modified
- commands run
- tests and results
- extractors implemented
- supported field paths
- confidence policy
- reconciliation behavior
- evidence behavior
- freshness rules
- known limitations
- required integration steps