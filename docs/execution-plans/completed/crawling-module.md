# Execution Plan: Website Crawling Module (Task 006)

Status: Complete
Contract: `docs/contracts/completed/crawling-module.md` — the first task
since the original paste-in-importer feature to go through the full
planner → generator → evaluator pipeline, rather than the ad-hoc
task-brief approach used for Tasks 004/005 (imports, discovery).

## History

An earlier, ad-hoc (no-contract) attempt at this task was started in a
background worktree, got cut off mid-fix, and was left incomplete (no
API layer, no MongoDB repository, no tests). That worktree and its
branch (`worktree-agent-aa962b95aad62bb2b`) were deleted before this run
started — nothing from it was reused. This execution restarted the task
from scratch using the formal contract-driven process.

## Scope

Isolated to `backend/app/modules/crawling/**`,
`backend/tests/unit/crawling/**`, `backend/tests/integration/crawling/**`,
`fixtures/crawling/**`, per the contract's allowed paths — confirmed via
`git diff --stat` against every other module before merge. `backend/app/main.py`,
`modules/companies/**`, `modules/discovery/**`, `modules/imports/**`,
`pyproject.toml`, and root config files were untouched.

## What was built

Given a company's discovery run, the crawler selects a deterministic,
capped set of target URLs (priority- and page-type-driven), checks
robots.txt permission per URL, fetches pages over plain HTTP(S) with SSRF
protection (no Playwright — plain `httpx`, following the exact pattern
`modules/discovery/infrastructure/httpx_discovery_client.py` already
established), supports conditional (ETag/Last-Modified) requests and
content-hash-based change detection (raw hash + a noise-tolerant
structural hash), validates and cleans HTML, extracts visible text and
page metadata (including technology signals, never written to any
company-facing field), detects when a page needs a real browser to
render (`detect_only` by default), stores content through a local
filesystem abstraction, and persists everything through the same
hexagonal (domain → application → infrastructure → api) layering as
`modules/companies`, `modules/imports`, and `modules/discovery`.

## Process

1. **Planner** produced `docs/contracts/completed/crawling-module.md`
   from the task brief (`docs/execution-plans/tasks/006—WebsiteCrawlingModule.md`):
   36 acceptance criteria, 33 implementation tasks, and explicit
   resolutions for three cross-module ambiguities the brief left open:
   - `CompanyCrawlGateway.update_latest_crawl_run` — a documented, logged
     no-op (`CompanyService` has no such method yet; mirrors the exact
     gap `update_latest_discovery_run` had before Task 005's own
     follow-up closed it).
   - `DiscoveryCrawlGateway` — wraps `DiscoveryRepository` directly via
     the existing, already-public `get_discovery_repository` DI function
     in `modules/discovery/api/router.py`, rather than a new service
     method (discovery has no query-capable service to wrap).
   - `RobotsPolicyGateway` — new matching/evaluation logic owned
     entirely by this module, reusing `modules/discovery/domain/robots_parser.parse_robots_txt`'s
     pure parsing function directly rather than reimplementing it.
2. **Generator** implemented the contract in an isolated git worktree.
   Self-reported 212 passing tests, clean `ruff`/`pyright`, and flagged
   two things itself: an untested `challenge_page_policy` branch, and a
   latent idempotency-key non-determinism bug (found and fixed mid-session
   — `CrawlConfig`'s `frozenset` fields serialize to JSON-list order that
   varies with Python's per-process hash randomization; fixed by explicit
   sorting in `domain/idempotency.py` before hashing).
3. **Evaluator** independently verified all 36 acceptance criteria
   against actual code and test execution (not the contract's prose, not
   the generator's report) — **PASS**, with two Important (non-blocking)
   findings:
   - `challenge_page_policy="failed"/"rejected"` had zero test coverage
     (confirmed real, matching the generator's own disclosure).
   - `CompanyServiceCrawlGateway.update_processing_status` let
     `CompanyService`'s real `CompanyNotFoundError` propagate unchanged
     instead of translating it into the module's own
     `CompanyNotFoundForCrawlError` — found independently by the
     evaluator, not self-reported. Would have made the router's 404
     handler dead code against the real adapter once wired up.
4. Both findings were fixed before merge: the gateway now translates the
   error (regression-tested against the real `CompanyService` over an
   in-memory fake `CompanyRepository`, confirmed to fail before the fix
   and pass after), and all three `challenge_page_policy` values now have
   service-level test coverage. Full suite re-verified: 218 crawling
   tests (up from 212), `ruff`/`pyright` clean.
5. Merged to `main` (`git merge --no-ff`). Full repo suite: 627 passed
   (up from 409 pre-merge), `ruff check .` and `pyright` clean.

## Known limitations

- No public-suffix-list/registrable-domain library (same documented gap
  `modules/discovery` already has) — not needed directly by this module.
- `Accept-Encoding` never advertises `br` (Brotli) — no Brotli-capable
  dependency exists in this repository and `pyproject.toml` is off-limits
  to this task; a compliant server therefore never sends Brotli, so this
  is a sidestep rather than an unhandled case.
- Same DNS-rebinding/TOCTOU residual risk as `HttpxDiscoveryClient`,
  copied forward and documented, not silently repeated.
- Sequential-only crawling (concurrency = 1 per company), as mandated —
  no distributed/parallel fetching.
- `Retry-After` is only parsed as numeric seconds, not an HTTP-date.
- Local filesystem content storage has no retention/cleanup policy —
  out of scope for this task.

## Required follow-up outside this task's allowed paths — not yet done

- **Register `crawling_router`** in `backend/app/main.py`, and wire
  `MongoCrawlRepository.ensure_indexes()` into the app's startup
  lifespan.
- **Add `CompanyService.update_latest_crawl_run`** (+
  `CompanyRepository.update_latest_crawl_run_id` interface and
  `MongoCompanyRepository` implementation) in `modules/companies/`,
  mirroring `update_latest_discovery_run` exactly, then switch
  `CompanyServiceCrawlGateway.update_latest_crawl_run` from its
  documented no-op to a real call.
- (Optional, non-blocking) Promote `DiscoveryRepositoryCrawlGateway`'s
  direct-`DiscoveryRepository`-import approach into a proper
  `DiscoveryQueryService` in `modules/discovery/application/`, for
  architectural symmetry with `CompanyService`.
- A real `BrowserPageFetcher` adapter (e.g. Playwright), if/when
  browser-rendered crawling is actually needed — currently `detect_only`,
  and no browser-automation dependency exists in this repository at all.
- (Optional, minor) Add `data/` (the local content-storage base
  directory) to root `.gitignore`.

This list mirrors Task 005's own "Required follow-up" pattern — expect a
similar closing commit once these are picked up.
