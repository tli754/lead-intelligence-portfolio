Context: no queue or worker system exists in this repository today. Every
pipeline stage (discovery, crawling, extraction) runs synchronously inline
from its FastAPI route handler — confirmed by reading
`backend/app/modules/discovery/api/router.py`,
`backend/app/modules/crawling/api/router.py`, and
`backend/app/modules/extraction/api/router.py`. CLAUDE.md documents this as
deliberate ("Redis and background workers are deliberately not scaffolded
yet — nothing in the repository uses a queue"). ADR 0003
(`docs/decisions/0003-auto-discovery-trigger-placement.md`) explicitly
defers its own blocking-call conclusion "When Redis/a task queue is
eventually scaffolded... this ADR's blocking-call conclusion for the bulk
path should be revisited in a new ADR."

Back on 2026-07-24 (pre-scaffold, before any code existed), the verbal
decision on the queue layer was Redis + Python workers, with a pipeline of
crawl -> interpret -> score as separate queued jobs so scoring can rerun
without re-crawling or re-hitting OpenAI. That decision was never written
into an ADR and nothing since has confirmed or revisited it.

Ask, part 1 (investigation, completed in conversation before this brief was
written): investigate what would need to change in this codebase to adopt
RQ (the Python `rq` library) as the queue system. Findings, for the record:

- All three pipeline services (`run_discovery`, `start_crawl_run`,
  `start_extraction_run`) already take plain arguments, not FastAPI types —
  each router's docstring says this is deliberate so "a future worker can
  call it identically." No service-layer changes should be needed to make
  them queue-callable.
- No backend "jobs" module exists. The frontend `JobsPage`
  (`frontend/src/pages/JobsPage.tsx`) synthesizes a "job" client-side by
  merging `GET /api/discovery-runs`, `/api/crawl-runs`, `/api/extraction-runs`
  in `frontend/src/api/jobs.ts` and mapping each run's own status enum down
  to a shared 4-value `JobStatus`. There's no `job_id`; it reuses the run's
  own ID. Task 012's contract
  (`docs/contracts/completed/wire-jobs-page-to-pipeline-runs.md`) explicitly
  states "there is no queue or worker system in this repository" — that line
  goes stale once this work lands.
- Each module has its own run model/collection (`DiscoveryRun`/
  `discovery_runs`, `CrawlRun`/`crawl_runs`, `ExtractionRun`/
  `extraction_runs`, documented in `docs/architecture/mongodb-design.md`).
  No generic cross-stage `PipelineRun` model exists, and no field records
  `queued_at` distinctly from `created_at`.
- `backend/app/config.py` has no `REDIS_URL` or queue-related setting.
  `pyproject.toml` has no `rq` or `redis` dependency.
  `docker-compose.yml` runs only `mongo`, no redis service — but the shared
  `/srv/infra` dev stack already runs Redis on `localhost:6379` (confirmed
  reachable), matching how this project already reuses the shared Mongo
  instead of its own compose service.
- The extraction module's two documented no-ops
  (`update_latest_extraction_run`, `project_latest_facts` — see
  `docs/contracts/completed/structured-extraction-and-evidence-module.md`)
  are the real blocker to full crawl -> extract -> score auto-chaining, but
  are out of scope for this task.

Ask, part 2 (this task): apply RQ as the queue system, starting with the
crawling module as a single vertical slice — not all three stages at once.
Crawling was chosen because it's the longest-running stage, making it the
best candidate to validate the queue pattern before rolling it out to
discovery and extraction. Scope explicitly excludes: auto-chaining crawl
into extraction, discovery or extraction module changes, and resolving the
two extraction no-ops above.
