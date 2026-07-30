# CLAUDE.md

Guidance for agents (planner, generator, evaluator) working in this
repository. Read `ARCHITECTURE.md` before implementing anything.

## Stack

- **Backend:** Python 3.11+, FastAPI, Pydantic v2 / pydantic-settings,
  Motor (async MongoDB driver), pymongo (transitive dependency of Motor,
  reserved for future sync worker scripts), uvicorn.
- **Database:** MongoDB, accessed exclusively via `CompanyRepository`
  and future `*Repository` classes — never directly from routes or
  services.
- **Frontend:** React + TypeScript, built with Vite. Styled with
  Tailwind CSS v4 and shadcn/ui (Radix-based) components under
  `src/components/ui/` — treat these as generated primitives (they
  match the canonical shadcn source) and compose them rather than
  editing their internals. No router library yet (see
  `ARCHITECTURE.md`). Tests with Vitest + React Testing Library.
- **Local infra:** `docker-compose.yml` runs MongoDB only, for
  environments without one already available. If MongoDB is already
  reachable at `localhost:27017` (e.g. a shared dev-infra stack), use
  that instead — don't run both, they'll conflict on the port. Redis
  and background workers are deliberately not scaffolded yet — nothing
  in the repository uses a queue.

## Directory layout

```
backend/
  app/
    main.py              # FastAPI app, router registration, startup hooks
    config.py             # pydantic-settings Settings (the only place env vars are read)
    db.py                  # Motor client factory + get_database() FastAPI dependency
    domains/
      health/
        router.py          # GET /api/health
    modules/
      companies/            # hexagonal variant — see ARCHITECTURE.md's
                             # "Module convention" section. The flat-convention
                             # `domains/companies` (paste-in importer, `companies`
                             # collection) that this once coexisted alongside was
                             # removed as dead weight after Task 014 superseded it
                             # (see ADR 0002's addendum) — this is now the only
                             # `Company` model in the codebase.
        domain/              # models.py, enums.py, transitions.py, exceptions.py,
                              # repository.py (interface), normalization.py
        application/          # service.py — depends only on the domain repository interface
        infrastructure/        # mongo_repository.py — all Motor access for this module
        api/                     # router.py, schemas.py (camelCase DTOs)
      imports/               # StoreLeads HTML import — depends on modules/companies only
                              # through domain/gateway.py's CompanyImportGateway port, never
                              # MongoDB directly
        domain/                # models.py, enums.py, gateway.py (port), storeleads_html_parser.py,
                                # website_normalizer.py, platform_normalizer.py, row_builder.py
        application/            # preview_service.py (read-only), import_service.py
        infrastructure/          # company_service_gateway.py — the real CompanyImportGateway
                                  # adapter, wraps modules/companies' CompanyService
        api/                       # router.py, schemas.py (camelCase DTOs)
      discovery/             # website discovery (sitemap/robots/link crawl to find
                              # candidate pages) — depends on modules/companies only
                              # through infrastructure/company_service_gateway.py
        domain/                # models.py, enums.py, gateway.py (port), repository.py
                                # (interface), sitemap_parser.py, robots_parser.py,
                                # html_link_extractor.py, page_classifier.py,
                                # priority_assigner.py, url_normalizer.py,
                                # domain_relationships.py, reconciliation.py
        application/            # website_discovery_service.py
        infrastructure/          # mongo_discovery_repository.py, httpx_discovery_client.py,
                                  # company_service_gateway.py
        api/                       # router.py, schemas.py (camelCase DTOs)
      crawling/               # fetches and stores page content for discovered URLs —
                              # depends on modules/companies (company_service_gateway.py)
                              # and modules/discovery (discovery_repository_gateway.py)
        domain/                # models.py, enums.py, gateway.py (port), repository.py
                                # (interface), content_storage.py (port), page_fetcher.py
                                # (port), robots_policy.py, rate_limiter.py, retry_policy.py,
                                # html_cleaner.py, html_validator.py, text_extractor.py,
                                # metadata_extractor.py, hashing.py, idempotency.py,
                                # target_selector.py, browser_fallback.py
        application/            # website_crawl_service.py
        infrastructure/          # mongo_crawl_repository.py, httpx_page_fetcher.py,
                                  # local_filesystem_content_storage.py,
                                  # http_robots_policy_gateway.py, company_service_gateway.py,
                                  # discovery_repository_gateway.py
        api/                       # router.py, schemas.py (camelCase DTOs)
      evidence/               # stores the source snippets (evidence) that back
                              # extracted facts — no dependency on other modules
        domain/                # models.py, enums.py, repository.py (interface),
                                # evidence_factory.py
        application/            # evidence_service.py
        infrastructure/          # mongo_evidence_repository.py
        api/                       # router.py, schemas.py (camelCase DTOs)
      extraction/             # turns crawled page content into structured facts with
                              # evidence — depends on modules/crawling
                              # (crawl_repository_gateway.py), modules/evidence
                              # (evidence_service_gateway.py), and modules/companies
                              # (company_service_gateway.py, with two documented no-ops:
                              # update_latest_extraction_run, project_latest_facts — see
                              # docs/contracts/completed/
                              # structured-extraction-and-evidence-module.md)
        domain/                # models.py, enums.py, gateway.py (port), repository.py
                                # (interface), extractor.py, extractors/, field_catalogue.py,
                                # pattern_types.py, candidate_builder.py, confidence_policy.py,
                                # reconciliation.py, reconciliation_rules.py,
                                # freshness_policy.py, company_projection.py, idempotency.py,
                                # html_helpers.py
        application/            # structured_extraction_service.py
        infrastructure/          # mongo_extraction_repository.py, crawl_repository_gateway.py,
                                  # evidence_service_gateway.py, company_service_gateway.py
        api/                       # router.py, schemas.py (camelCase DTOs)
  tests/
    conftest.py            # shared fixtures: test MongoDB database, HTTP test client
    test_health.py
    modules/
      companies/            # stale — see "Where tests live" below
    unit/
      companies/             # domain/application/API-schema unit tests for modules/companies
                              # (no MongoDB): test_normalization.py, test_models.py,
                              # test_transitions.py, test_api_schemas.py
      imports/                # pure domain-logic unit tests for modules/imports (no MongoDB,
                               # no gateway): test_storeleads_html_parser.py,
                               # test_website_normalizer.py, test_platform_normalizer.py,
                               # test_row_builder.py
      discovery/               # pure domain-logic unit tests for modules/discovery
      crawling/                 # pure domain-logic unit tests for modules/crawling
      evidence/                  # pure domain-logic unit tests for modules/evidence
      extraction/                 # pure domain-logic unit tests for modules/extraction,
                                   # including test_pattern_coverage.py (per-rule
                                   # true/false-positive fixture coverage)
    integration/
      companies/              # real-MongoDB integration tests for modules/companies:
                               # test_create_company.py, test_retrieve_company.py,
                               # test_list_companies.py, test_*_status_transitions.py,
                               # test_duplicate_domain.py
      imports/                 # modules/imports tests via a FakeCompanyImportGateway
                                # (conftest.py) and a locally-built FastAPI app with only the
                                # imports router — no real MongoDB, no shared app.main.app:
                                # test_preview.py, test_import.py, test_api_schema_serialization.py
      discovery/                # real-MongoDB integration tests for modules/discovery
      crawling/                  # real-MongoDB integration tests for modules/crawling
      evidence/                   # real-MongoDB integration tests for modules/evidence
      extraction/                  # real-MongoDB integration tests for modules/extraction,
                                    # including test_full_pipeline.py (crawl content ->
                                    # extracted facts with evidence, end to end)
frontend/
  components.json         # shadcn/ui CLI config (style, aliases, theme)
  src/
    main.tsx, App.tsx       # QueryClientProvider + BrowserRouter wiring lives in main.tsx
    index.css              # Tailwind v4 import + shadcn CSS variables + fixed status-tone palette
    pages/                 # ImportPage, CompaniesPage, CompanyDetailPage, JobsPage (+ tests)
    components/
      Layout.tsx            # shared nav shell, rendered by App.tsx's <Routes>
      EvidenceViewer.tsx     # groups evidence by field, flags conflicting values
      status/                 # ProcessingStatusBadge, WorkflowStatusBadge, JobStatusBadge,
                               # ConfidenceMeter — reusable status/confidence indicators
      ui/                     # shadcn/ui primitives (button, textarea, card, table, select, ...)
    api/
      companies.ts           # typed HTTP client for the real paste-importer backend
      queries.ts               # TanStack Query hooks — pages depend on these, not on clients directly
      mock/                     # mock API layer (client.ts, fixtures.ts) backing the
                                 # CompaniesPage/CompanyDetailPage/JobsPage — not wired to
                                 # a real backend yet
    schemas/                # Zod schemas + inferred types, validated at the mock API boundary
    types/                  # TS types mirroring backend Pydantic models by hand (no Zod)
    lib/                    # utils.ts (cn()), format.ts (date/score/"Unknown" formatting)
    test/                   # renderWithProviders.tsx — shared test-provider wrapper

tests/
  # Reserved for future full-stack/browser tests spanning frontend +
  # backend (e.g. Playwright). Not used by the paste-in importer
  # feature — its browser-test requirement was explicitly waived (see
  # its contract's Required Tests section).

fixtures/
  storeleads/                # sanitized StoreLeads HTML <table> snippets used by
                              # backend/tests/{unit,integration}/imports/ — a top-level
                              # directory (not backend/tests/fixtures/) because Task 004's
                              # allowed paths specified it there explicitly

docs/
  architecture/            # dependency-rules.md, mongodb-design.md, runtime-design.md
  product/                 # vision.md, scoring-model.md, lead-definition.md
  decisions/                # ADRs
  contracts/                 # feature contracts (active/completed)
  execution-plans/            # per-feature execution checklists
    tasks/
      # Preserved raw task briefs provided to Planner or Generator.
      # These files record the original request and should not be treated
      # as completion reports.
```

## Where tests live

Two conventions coexisted here — see ARCHITECTURE.md's (now-resolved) fork
note. The flat convention's only non-trivial example, `domains/companies`,
was removed (see ADR 0002's addendum); `domains/health` remains as a
minimal scaffolding-only domain, tested by the top-level
`backend/tests/test_health.py` rather than a mirrored `domains/health/`
test directory.

- **Hexagonal-convention modules** (`backend/app/modules/<name>/`): tests
  live under `backend/tests/unit/<name>/` (pure domain/application/API-
  schema tests, no MongoDB) and `backend/tests/integration/<name>/`,
  rather than mirroring the app tree. `modules/companies`,
  `modules/discovery`, `modules/crawling`, `modules/evidence`, and
  `modules/extraction`'s integration tests hit real MongoDB via the
  shared `client`/`test_database` fixtures in `backend/tests/conftest.py`.
  `modules/imports`'s integration tests do not — that module never
  touches MongoDB directly (only a `CompanyImportGateway` port), so its
  `backend/tests/integration/imports/conftest.py` instead builds a
  `FakeCompanyImportGateway` and a locally-scoped `FastAPI()` app
  containing only the imports router.
- **Known stale:** `backend/tests/modules/companies/**` and
  `backend/tests/test_company_module_api.py` reference an earlier shape
  of `modules/companies` and currently fail to even import — running the
  full suite with plain `pytest backend/tests` aborts on collection.
  Until they're deleted, either ignore them explicitly
  (`pytest backend/tests --ignore=backend/tests/modules/companies
  --ignore=backend/tests/test_company_module_api.py`) or target the
  paths you actually need.
- Both conventions run with `pytest` from the repository root
  (`testpaths = backend/tests` is configured in `pyproject.toml`).
- `frontend/src/**/*.test.tsx` — component tests live next to the
  component they test, run with `pnpm run test` (Vitest) inside
  `frontend/`.
- Top-level `tests/` is reserved for future full-stack/browser tests
  (e.g. Playwright) spanning both frontend and backend together. It is
  intentionally empty until a feature needs it.

## Task workflow

Every feature must leave behind three artifacts, in this order, before
it can be considered done:

1. **Asked** — the raw task brief, preserved verbatim under
   `docs/execution-plans/tasks/`. Do not paraphrase or edit it after
   the fact; it's a record of what was actually requested.
2. **Decided** — the planner's feature contract in
   `docs/contracts/active/`, or an ADR in `docs/decisions/` for
   foundational/architectural decisions that aren't scoped to one
   feature. This is what the evaluator checks the implementation
   against — never skip it, even for small features.
3. **Built** — the execution plan / completion record in
   `docs/execution-plans/completed/`, written once the evaluator
   reports PASS. At that point move the matching contract from
   `docs/contracts/active/` to `docs/contracts/completed/`.

A feature isn't done until all three exist and are consistent with
each other. `docs/execution-plans/tasks/` records are historical —
never edit them to match what was later decided or built.

## Environment variables

See `.env.example`. Backend settings are defined once in
`backend/app/config.py`; nothing else should read `os.environ`
directly.

## Further reading

- `ARCHITECTURE.md` — layering rules and dependency direction.
- `docs/architecture/dependency-rules.md` — the same rules, worked
  through against the `companies` domain as a concrete example.
- `docs/architecture/mongodb-design.md` — collection/schema/index
  design.
- `docs/product/lead-definition.md` — what a `Company` is (and is not
  yet) in this product.
- `docs/decisions/` — ADRs recording non-obvious decisions and their
  rationale.
