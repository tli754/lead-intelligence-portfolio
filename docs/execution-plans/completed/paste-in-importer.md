# Execution Plan: Paste-in Importer

Contract: `docs/contracts/active/paste-in-importer.md`
Status: Complete

## Order of work

- [x] 1. Root `pyproject.toml` (deps + tool config)
- [x] 2. Backend entrypoint skeleton (`main.py`, `config.py`, `db.py`, health route)
- [x] 3. `docker-compose.yml` (MongoDB) + `.env.example`
- [x] 4. `backend/tests/conftest.py` (test DB fixtures)
- [x] 5. `companies` domain models
- [x] 6. `CompanyRepository`
- [x] 7. Repository tests
- [x] 8. Parsing functions (`normalize_domain`, `detect_format`, `parse_domain_list`, `parse_storeleads_html`) — platform_version intentionally never captured, see contract Task 8
- [x] 9. Parsing unit tests, incl. fixture-based storeleads regression test (`backend/tests/fixtures/storeleads_sample.html` copied from `docs/data/storeLeads.html`)
- [x] 10. `CompanyImportService`
- [x] 11. Service unit tests
- [x] 12. Router (`POST /api/companies/import`), wired into `main.py`
- [x] 13. API/integration tests (`backend/tests/test_company_import.py`)
- [x] 14. Frontend scaffold (Vite + React + TS + Vitest/RTL)
- [x] 15. `ImportPage` + typed API client + results rendering + wired into `App.tsx`
- [x] 16. Frontend component test
- [x] 17. Documentation: `ARCHITECTURE.md`, `CLAUDE.md`, `docs/architecture/dependency-rules.md`, `docs/architecture/mongodb-design.md`, `docs/product/lead-definition.md`, ADR in `docs/decisions/`

## Notes for the generator

- This is the first feature in the repo — nothing exists yet, you are also standing up the skeleton.
- `docs/data/storeLeads.html` is the real sample paste this feature must handle; copy it into `backend/tests/fixtures/storeleads_sample.html` for the regression test.
- Full task detail, acceptance criteria, and rationale for every non-obvious decision (Company vs Lead naming, platform_version exclusion, dedupe policy) live in the contract — read it in full before starting.
