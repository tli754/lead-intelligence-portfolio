# Execution Plan: Wire Built Module Routers into the Live API (Task 009)

Status: Built, awaiting evaluator
Contract: `docs/contracts/active/wire-modules-into-live-api.md`
Task brief: `docs/execution-plans/tasks/009-Wire-Backend-Modules-into-Live-API.md`

## Scope

`backend/app/main.py` only — register `modules/imports`,
`modules/crawling`, `modules/extraction`, `modules/evidence` routers and
their `ensure_indexes()` calls. No frontend changes, no resolution of
the documented no-op `Company` gateways (both out of scope per the
user's explicit scoping decision — see contract).

## Status log

- Contract produced, saved to `docs/contracts/active/`.
- Implemented directly (task too small to warrant a separate generator
  delegation — single-file, mechanical composition-root change with no
  new domain logic).
- Verified: `git diff --stat` shows exactly `backend/app/main.py`
  changed (AC-05). `app.main.app.openapi()["paths"]` contains all 13
  new paths, zero collisions with existing routes (AC-01/AC-02). Full
  backend suite (`pytest backend/tests --ignore=backend/tests/modules/companies
  --ignore=backend/tests/test_company_module_api.py`) passes: 830/830
  (AC-03/AC-04). `ruff check`/`pyright` clean on `main.py`. App startup
  via `TestClient(app)` (triggers `lifespan`) succeeds against the real
  MongoDB instance with no errors (AC-06). No `BackgroundTasks`
  introduced (AC-07).
- Handing off to the evaluator agent against the contract next.
