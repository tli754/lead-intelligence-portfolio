Task 009 — Wire built-but-unregistered module routers into the live API

Raised in conversation (not a pre-written brief), preserved here verbatim
as the record of what was actually asked, per CLAUDE.md's Task workflow.

Context: after Task 007 (structured extraction and evidence modules)
was merged, the assistant was asked "what feature do I have now?" and
reported that four modules — `modules/imports`, `modules/crawling`,
`modules/extraction`, and `modules/evidence` — have fully built and
tested API routers (`api/router.py`) that are **not** registered in
`backend/app/main.py`, so none of their endpoints are reachable over
HTTP yet, even though `modules/discovery` and `modules/companies` are
already live. The assistant asked whether to open a task for wiring
this up; the user replied "wired to live API NEXT //".

Follow-up scoping question and answer (via AskUserQuestion): the user
selected "Router registration only" — explicitly **not** in scope:
- Resolving the documented no-op `Company` gateways
  (`update_latest_crawl_run`, `update_latest_extraction_run`,
  `project_latest_facts`) — these require a `Company`/`CompanyProcessing`
  schema design decision (flattened vs. nested) that both Task 006's
  and Task 007's contracts explicitly flagged as needing its own future
  task.
- Wiring the frontend (`frontend/src/api/mock/`) to the newly-live
  endpoints — a separate, larger frontend task.

Ask, concretely: register `modules/imports`, `modules/crawling`,
`modules/extraction`, and `modules/evidence`'s existing, already-tested
routers in `backend/app/main.py` (mirroring how `modules/discovery` and
`modules/companies` are already registered), and add the corresponding
`ensure_indexes()` calls to the FastAPI `lifespan` startup hook for any
of those modules with their own MongoDB collections — without changing
any module's own domain/application/infrastructure code, and without
touching the frontend.
