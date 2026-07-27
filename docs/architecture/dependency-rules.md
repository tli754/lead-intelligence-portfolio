# Dependency Rules

This document states the layering rules from `ARCHITECTURE.md` in more
detail, worked through against two examples: `backend/app/domains/companies/`
(the flat convention, introduced by the paste-in importer feature) and
`backend/app/modules/companies/` (the hexagonal convention, introduced
later — see ARCHITECTURE.md's "Module convention" section for why two
conventions and two `Company` models coexist here without an ADR
reconciling them yet).

## The rule (flat convention)

```
router.py  -->  service.py  -->  repository.py  -->  MongoDB (Motor)
```

Dependencies only ever point rightward/downward in that chain. A file
must never import from a layer to its right when it lives to the left
(e.g. a router must never import Motor types), and must never be
imported by a layer to its right (e.g. a repository must never import
from a router).

The frontend depends only on the API (`frontend/src/api/*.ts` calling
`${VITE_API_BASE_URL}/api/...`); it never talks to MongoDB, and never
imports backend Python code.

## Worked example: `companies`

- **`backend/app/domains/companies/router.py`**
  Depends on: `CompanyImportService` (via a FastAPI `Depends`), and the
  domain's Pydantic models (`ImportRequest`, `ImportResponse`).
  Does NOT depend on: `CompanyRepository`, Motor, or any dedupe/parsing
  logic. The route handler is a two-line function: call the service,
  return its result.

- **`backend/app/domains/companies/service.py`** (`CompanyImportService`)
  Depends on: `CompanyRepositoryProtocol` (a `typing.Protocol`
  describing only the methods the service needs — this lets unit tests
  substitute a fake in-memory repository without touching MongoDB), and
  the pure functions in `parsing.py`.
  Does NOT depend on: FastAPI request/response types, Motor, or
  `pymongo`.
  Owns: format detection orchestration, in-paste dedupe delegation,
  DB-existing dedupe (calls `repository.get_existing_domains()` and
  filters), building `Company` documents, and calling
  `repository.insert_many()`.

- **`backend/app/domains/companies/repository.py`** (`CompanyRepository`)
  Depends on: Motor (`AsyncIOMotorDatabase`), `pymongo.errors`.
  Does NOT depend on: `service.py`, `router.py`, or any dedupe
  business rule (it doesn't decide what counts as a duplicate — it only
  answers "which of these domains already exist" and "insert these
  documents, telling me which ones failed on a duplicate key").
  Owns: all `find`/`insert_one`/`create_index` calls against the
  `companies` collection.

- **`backend/app/domains/companies/parsing.py`**
  Pure functions only (`normalize_domain`, `detect_format`,
  `parse_domain_list`, `parse_storeleads_html`). No MongoDB, no FastAPI,
  no I/O of any kind — this is what makes them trivially unit-testable
  without a database.

## Why a Protocol instead of the concrete repository class in the service

`CompanyImportService.__init__` accepts `CompanyRepositoryProtocol`
(structural typing), not the concrete `CompanyRepository` class. This
lets `backend/tests/domains/companies/test_service.py` pass a small
in-memory fake repository and test all dedupe/business-rule branches
without a MongoDB connection, while `backend/tests/domains/companies/
test_repository.py` separately tests the real Motor-backed
implementation against a live test database. Both test files stay fast
and focused on what they're actually responsible for verifying.

## The rule (hexagonal convention)

```
api/router.py --> application/service.py --> domain/repository.py (interface)
                                                       ^
                                    infrastructure/mongo_repository.py implements it
```

`application/` depends on `domain/`'s repository *interface* (an
`abc.ABC`), never on `infrastructure/`'s concrete Motor class directly.
FastAPI's dependency-injection wiring (`Depends(get_company_service)` in
`api/router.py`) is what actually constructs `MongoCompanyRepository` and
hands it to `CompanyService` — the only place the concrete infrastructure
class and the application service are imported into the same file.

## Worked example: `modules/companies`

- **`backend/app/modules/companies/api/router.py`** and **`api/schemas.py`**
  Depends on: `CompanyService`, the domain enums/exceptions (to catch and
  map them to HTTP status codes), and its own camelCase DTOs
  (`CompanyResponse`, `CompanyListItemResponse`, ...). `schemas.py`
  defines mapper functions (`company_to_response`,
  `company_to_list_item`) that translate the domain `Company` model into
  these DTOs — camelCase aliasing is an API concern, so it never touches
  `domain/models.py`.
  Does NOT depend on: `MongoCompanyRepository` directly in business
  logic — only in the `Depends(...)` wiring function.

- **`backend/app/modules/companies/application/service.py`** (`CompanyService`)
  Depends on: `domain.repository.CompanyRepository` (the `ABC`, not the
  Mongo implementation), `domain.transitions` (pure functions validating
  a processing/workflow status change before persisting it).
  Does NOT depend on: FastAPI, Motor, or `pymongo`.
  Owns: duplicate-domain checking before create, fetching the current
  company and validating a status transition before calling
  `repository.update_processing_status()`/`update_workflow_status()`.

- **`backend/app/modules/companies/infrastructure/mongo_repository.py`**
  (`MongoCompanyRepository(CompanyRepository)`)
  Depends on: Motor (`AsyncIOMotorDatabase`), `pymongo` (`ReturnDocument`,
  `DuplicateKeyError`).
  Does NOT depend on: `application/` or `api/`, and contains no status-
  transition validation — that's the service's job; this layer only
  knows how to read/write documents and translate a Mongo
  `DuplicateKeyError` into the domain's typed `DuplicateCompanyError`.
  Owns: all `find`/`insert_one`/`find_one_and_update`/`create_index`
  calls against the `companies_pipeline` collection.

- **`backend/app/modules/companies/domain/`**
  `models.py`, `enums.py`, `transitions.py`, `exceptions.py`,
  `normalization.py`, `repository.py` (the interface). Zero imports of
  FastAPI, Motor, or any other external SDK — stricter than the flat
  convention, which only forbids Mongo driver types from `service.py`,
  not from `models.py`.

## Worked example: `modules/imports` (a module that depends on another module)

`imports` never touches MongoDB at all — its only external dependency is
`companies`, reached through a port it defines itself, not through
`companies`' persistence layer:

```
imports/api/router.py --> imports/application/{preview,import}_service.py
                                     --> imports/domain/gateway.py (CompanyImportGateway, ABC)
                                                  ^
                    imports/infrastructure/company_service_gateway.py implements it,
                    by calling companies/application/service.py's CompanyService
                    (never companies/infrastructure/mongo_repository.py)
```

- **`backend/app/modules/imports/domain/gateway.py`** (`CompanyImportGateway`)
  An `ABC` with exactly two methods (`exists_by_domain`,
  `create_imported_company`) — the smallest interface `imports` needs
  from `companies`, not a general-purpose company API. Zero imports of
  FastAPI, Motor, or `app.modules.companies` — a port is defined in
  terms of what the *dependent* module needs, without knowing anything
  about the *providing* module's internals.

- **`backend/app/modules/imports/application/{preview_service,import_service}.py`**
  Depend on: `domain.gateway.CompanyImportGateway` (the `ABC`).
  Does NOT depend on: `CompanyService`, `MongoCompanyRepository`, or
  anything else concrete from `companies` — swapping the adapter (e.g.
  for a test fake) never touches this layer.

- **`backend/app/modules/imports/infrastructure/company_service_gateway.py`**
  (`CompanyServiceImportGateway(CompanyImportGateway)`)
  Depends on: `app.modules.companies.application.service.CompanyService`
  and `app.modules.companies.domain.exceptions.DuplicateCompanyError`
  (to catch and re-raise as `imports`' own
  `CompanyAlreadyExistsError`) — **never**
  `app.modules.companies.infrastructure.mongo_repository`. This is the
  one file in `imports/` that imports anything from `companies/` at all.
  A `CompanyService` instance is handed in via FastAPI's
  `Depends(get_company_service)` in `imports/api/router.py`, reusing
  `companies/api/router.py`'s own DI wiring function rather than
  constructing a repository or service by hand.

- **`backend/app/modules/imports/domain/{storeleads_html_parser,website_normalizer,
  platform_normalizer,row_builder}.py`**
  Pure functions/classes, stdlib-only (`html.parser`, `urllib.parse`,
  `ipaddress`) — no new third-party dependency was added to parse HTML
  or validate hostnames.

## Enforcement

These rules are currently enforced by code review only (see AC-12 in
the paste-in importer contract). `tools/check_architecture.py` is
reserved for automating this check (e.g. via static import-graph
analysis) but is out of scope for the paste-in importer feature and is
currently a 0-byte stub.
