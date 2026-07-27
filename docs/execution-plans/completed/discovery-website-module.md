# Execution Plan: Website Discovery Module (Task 005)

Status: Complete
Contract: none written — built directly from an ad-hoc task brief ("Task
005"), not through the planner→contract workflow used by
`paste-in-importer`. Full design plan: see the approved plan this task
was implemented from.

## Scope

Isolated to `backend/app/modules/discovery/**`,
`backend/tests/unit/discovery/**`, `backend/tests/integration/discovery/**`,
`fixtures/discovery/**`, per the task's explicit path restrictions.
`backend/app/main.py`, `modules/companies/**`, `modules/imports/**`, and
all root config files were off-limits — confirmed untouched by `git
diff --stat`. No Playwright, no full crawling, no page-content storage,
no evidence/AI/scoring/frontend work included.

## What was built

Given a company's domain, the module resolves its homepage over plain
HTTP(S) (no Playwright), extracts links, reads `robots.txt` and
sitemaps, classifies page types, assigns priorities, deduplicates across
sources, and persists the results — all through the same hexagonal
(domain → application → infrastructure → api) layering as
`modules/companies` and `modules/imports`.

**Domain** (`domain/`): `DiscoveryRun`/`DiscoveredUrl`/`DiscoverySummary`
models (UTC-coerced timestamps, same pattern as `modules/companies`);
`url_normalizer.py` (a separate implementation from
`modules/imports/domain/website_normalizer.py` — notably does **not**
strip `www`, since discovery treats it as a meaningful subdomain);
`domain_relationships.py` (same-domain / same-registrable-domain, the
latter a documented heuristic, not a full public-suffix-list); a stdlib
`html.parser.HTMLParser`-based link extractor (header/nav/footer/main
context tracking, canonical/alternate `<link>` capture); a line-based
`robots.txt` parser (case-insensitive `Sitemap:` capture, raw rule
groups for a *future* crawler — no enforcement here); a stdlib
`xml.etree.ElementTree`-based sitemap parser (urlset/index/nested-index/
gzip/plain-text, off-domain rejection, large-product-sitemap sampling
with an aggregate count preserved); a versioned (`CLASSIFICATION_RULES_VERSION
= "v1"`), deterministic page-type classifier (every example path in the
task's spec, plus anchor-text corroboration as a weaker secondary
signal); a priority assigner (three tiers + exclusions, with a
config-driven override map rather than hardcoded conditionals); and a
reconciliation module merging same-URL candidates across sources
(union sources/anchors/source-urls, strongest confidence, highest
priority, shallowest depth, alternates preserved in metadata).

**Application** (`application/website_discovery_service.py`):
`WebsiteDiscoveryService.run_discovery` orchestrates the full run —
resolve homepage (the one step allowed to fail the whole run) → extract
links → robots.txt (best-effort, never fails the run) → sitemaps
(each fetched/parsed individually, one bad sitemap only adds a warning)
→ reconcile → classify/prioritize → persist → update run status →
update company status. Cancellation is checked between every major step
via an optional `cancellation_check` callable (no task-queue/worker
framework exists in this repo yet, so this is the practical
interpretation of "must support cancellation between major steps").

**Infrastructure** (`infrastructure/`): `HttpxDiscoveryClient` (the real
HTTP adapter — see "HTTP safety" below); `MongoDiscoveryRepository`
(Motor-backed, `discovery_runs` + `discoveries` collections, indexes
exactly as specified); `CompanyServiceDiscoveryGateway` (the real
adapter wrapping `modules/companies`' own `CompanyService`, reusing its
`get_company_service` DI function — same integration pattern
`modules/imports` already established).

**API** (`api/`): `POST /api/companies/{company_id}/discovery-runs`,
`GET /api/companies/{company_id}/discovery-runs/latest`,
`GET /api/discovery-runs/{discovery_run_id}`,
`GET /api/discovery-runs/{discovery_run_id}/urls` — all camelCase,
matching the task's exact example response shape. **Built but not
registered** in `backend/app/main.py`, per the task's own instruction.

## Deliberate design decisions worth flagging

- **`DiscoveryRepository.get_latest_run_for_company`** was added beyond
  the task's literal section-11 method list — nothing in that list
  (`create_run`, `update_run`, `save_discovered_urls`, `get_run`,
  `list_discovered_urls`, `find_existing_url`) can serve the required
  `GET .../discovery-runs/latest` endpoint. Documented in the method's
  own docstring as a deliberate, justified extension.
- **`DiscoveredUrl.is_same_domain`** is interpreted as "same
  *registrable* domain as the company's root domain," not an exact
  hostname match — the more useful check in practice, since a resolved
  homepage often lives on `www.` or another subdomain. Documented in
  `application/website_discovery_service.py`'s `is_same_domain_or_registrable`.
- **`CompanyDiscoveryGateway.update_processing_status`** takes the real
  `modules.companies.domain.enums.ProcessingStatus` (a pure value type,
  zero FastAPI/Mongo imports) rather than a second, redundant status
  enum — consistent with Task 004's precedent of importing a domain
  exception type across the same module boundary.
- **A real cross-module bug was caught and fixed during manual
  verification, not left as a gap**: `modules/companies`' transition
  graph (built in Task 003) rejects `imported → discovered` directly —
  it requires the intermediate `discovering` state. The service now
  calls `update_processing_status(..., DISCOVERING)` when a run starts,
  before attempting `DISCOVERED`/`FAILED` at the end. This was only
  caught by running a real end-to-end request against the real
  `CompanyService` (see Testing below) — none of the fakes used in the
  automated integration tests validate transitions, so this class of
  bug is invisible to fake-backed tests alone.

## HTTP safety / SSRF protections implemented

- Only `http`/`https` schemes allowed; every other scheme rejected at
  the domain-layer normalizer.
- `localhost` and `*.localhost` rejected by name, before any DNS lookup.
- Every request (the initial URL **and every redirect hop**, followed
  manually with `follow_redirects=False`) resolves its hostname via
  `asyncio`'s `getaddrinfo` and rejects if **any** resolved address is
  private, loopback, link-local, multicast, reserved, or unspecified
  (IPv4 and IPv6 both covered via stdlib `ipaddress`).
- Connect/read timeouts, a capped redirect count, and a streamed,
  size-capped response body (aborted mid-download once the configured
  limit is exceeded, never fully buffered first) are all configurable
  via `DiscoveryConfig`.
- `Content-Type` validated (strict for homepage HTML, lenient/tolerant
  of a missing header for `robots.txt`/sitemaps, matching real-world
  server misconfiguration).
- A controlled `User-Agent`; no `Authorization` header ever set or
  persisted; a fresh `httpx.AsyncClient` per request chain with
  `client.cookies.clear()` after every hop, so no cookie or auth state
  ever survives across requests or redirect hops.
- Concurrency bounded via `asyncio.Semaphore(max_concurrent_requests)`,
  scoped to one discovery run's HTTP client instance.
- No raw response bodies are ever logged — only host/status/byte-count
  metadata.

**Documented residual risk — DNS rebinding (TOCTOU):** the `getaddrinfo`
validation happens immediately before each request, but `httpx`'s own
connection internally re-resolves the hostname when it actually opens
the socket. A DNS server returning a validated public IP to the
pre-check and a private IP (very short TTL) to the moment `httpx`
connects would bypass this. Full closure requires a custom transport
pinning the validated IP at the socket level while preserving the
original `Host`/SNI — out of scope for this ticket, which explicitly
allows documenting this instead of fully closing it. Fully documented
in `infrastructure/httpx_discovery_client.py`'s module docstring.

## Sitemap limits used (all in `domain/config.py`'s `DiscoveryConfig`, overridable)

`max_sitemap_files=50`, `max_sitemap_depth=5`, `max_urls_per_run=2000`,
`large_sitemap_threshold=200` (entries beyond this in one document
trigger sampling), `sitemap_sample_size=50` (kept entries once
sampling triggers), `max_xml_elements_per_document=200_000` (XML-bomb
defense-in-depth, on top of the response-size cap and a capped gzip
decompression read loop that also guards against a small-compressed/
huge-decompressed "zip bomb" payload).

## Testing

218 new tests, all passing:
- **Unit** (`backend/tests/unit/discovery/`, 196 tests, pure domain
  logic, no gateway/repository/HTTP): every case in the task's URL-
  normalization, HTML-extraction, robots, sitemap, classification,
  priority, and reconciliation test lists, run against the 11 fixtures
  in `fixtures/discovery/`.
- **Integration** (`backend/tests/integration/discovery/`, 22 tests,
  fakes for gateway/repository/HTTP client, no real MongoDB or network):
  successful run, homepage failure aborts the run, robots failure
  doesn't, one bad sitemap doesn't, duplicate-safe retry, company status
  update, summary accuracy, cancellation between steps, camelCase API
  schemas, pagination, enum serialization, excluded-URL filtering.

`ruff` and `pyright` clean on all changed/new paths. Full backend suite
(excluding the pre-existing stale Task-002 paths, unrelated to this
work): 386 passed.

**Additionally verified manually** (not part of the automated suite,
since it requires real network access) against the **real** stack: real
MongoDB, real `CompanyService` via `CompanyServiceDiscoveryGateway`, and
a real `HttpxDiscoveryClient` fetch of `https://example.com`. This is
what caught the `imported → discovered` transition bug described above
— confirmed fixed by re-running the same real request end-to-end
afterward, including confirming the company's `processing.status`
correctly reads `discovered` in MongoDB via the real
`GET /api/companies/{id}` endpoint. Smoke-test data cleaned up
afterward.

## Known limitations

- `registrable_domain()` uses a short hardcoded list of common compound
  TLDs (`co.nz`, `co.uk`, `com.au`, etc.), not a full Public Suffix
  List — would need a new dependency to fix properly (out of scope,
  `pyproject.toml` off-limits to this task).
- The XML-bomb defense is response-size-cap + element-count-cap based,
  not a hardened parser like `defusedxml` (also a new dependency, same
  constraint).
- "Multilingual English patterns" for page classification means several
  English synonyms per page type, not true multi-language support.
- `httpx` is currently a **dev-only** dependency — it works today
  because it's already installed (used by the test suite's ASGI
  client), but this should be formalized.

## Required follow-up outside this task's allowed paths — now done

All four items below were completed in a follow-up pass that touched
`backend/app/main.py`, `pyproject.toml`, and `modules/companies/`
(all originally off-limits to Task 005 itself):

- **Registered `discovery_router`** in `backend/app/main.py`.
- **Promoted `httpx`** from `[project.optional-dependencies].dev` to
  `[project.dependencies]` in `pyproject.toml`.
- **Added `CompanyRepository.update_latest_discovery_run_id`** (domain
  interface) and its `MongoCompanyRepository` implementation, plus
  `CompanyService.update_latest_discovery_run`.
  `CompanyServiceDiscoveryGateway.update_latest_discovery_run` now
  calls it instead of being a logged no-op.
- **Wired `MongoDiscoveryRepository.ensure_indexes()`** into the app
  startup lifespan in `main.py`, alongside the two existing
  `ensure_indexes()` calls.

Verified together via a real end-to-end smoke test against the live
stack (real MongoDB, real HTTP fetch of `https://example.com`): a
created company's `processing.status` correctly transitioned
`imported → discovering → discovered`, and
`processing.latestDiscoveryRunId` was persisted and readable via
`GET /api/companies/{id}` — previously confirmed stuck at `null`. Both
`discovery_runs` and `discoveries` collections had their indexes
present after a fresh app start. Smoke-test data cleaned up
afterward. Full backend suite (`pytest backend/tests`, same ignores
as before) still passes: 386 passed. `ruff` and `pyright` clean.

Still open, unchanged from before:

- The DNS-rebinding TOCTOU gap documented above.
- The two "Known limitations" above (no Public Suffix List, XML-bomb
  defense is cap-based) — both require a new dependency and remain out
  of scope.
