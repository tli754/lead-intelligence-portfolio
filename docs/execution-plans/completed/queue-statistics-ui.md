# Execution Plan: Queue Statistics UI (Task 019)

Status: Done
Contract: `docs/contracts/completed/019-queue-statistics-ui.md`
Task brief: `docs/execution-plans/tasks/019-Queue-Statistics-UI.md`
Builds on: `docs/decisions/0004-adopt-rq-as-queue-system.md`,
`docs/contracts/completed/017-rq-crawling-vertical-slice.md`

Adds observability for the crawling RQ queue Task 017 introduced —
until this task, a crawl run sitting in `queued` forever (e.g. because
no `rq worker` process was running) had zero signal anywhere in the
product. A small, auto-refreshing statistics panel was added to the
existing `JobsPage`, backed by a new, generalized backend endpoint.

## Scope

Added: `backend/app/domains/queue_stats/` — a new flat-convention
domain (`schemas.py`, `service.py`, `router.py`), modeled on
`backend/app/domains/health/`'s precedent for a small, cross-cutting,
non-hexagonal-module router. `GET /api/queue-stats?queue=<name>`
(defaulting to `"crawling"`) returns per-queue counts (queued, started,
finished, failed, deferred, scheduled — read directly from RQ's
`Queue.count` and its five registry classes), up to 50 failed job IDs
(`FAILED_JOB_ID_LIMIT`, enforced both at the router's bounded
`get_job_ids` call and again defensively in `build_queue_stats`), and
`workers_alive` (a count of `rq.Worker.all()` entries excluding
`suspended` state). Deliberately generalizes to any queue name with no
code change, so discovery/extraction can reuse this same endpoint once
they adopt RQ (ADR 0004's module-by-module rollout) — accepting an
unknown/never-used queue name just returns an all-zero snapshot, not an
error.

Added on the frontend: `frontend/src/schemas/queueStats.ts` (Zod),
`frontend/src/api/queueStats.ts` (`fetchQueueStats`,
`QueueStatsRequestError`), `useQueueStats` in
`frontend/src/api/queries.ts` (`refetchInterval: 7000`), and
`frontend/src/components/QueueStatsPanel.tsx` — rendered above the
existing jobs table in `JobsPage.tsx`. The panel shows six count
labels, a worker-liveness pill (`"warning"` tone, not `"critical"`,
when no worker is alive — a stopped-worker-in-local-dev is not
inherently a system failure), and up to 8 failed-job-id badges with a
"+N more" suffix beyond that. An all-zero/no-worker response renders as
a normal state, not an error — a deliberate design point, since a
naive implementation could easily misclassify "nothing has run yet"
as a failure.

Zero changes to any other module/domain — `queue_stats` depends only
on `app.queue` (already cross-cutting infrastructure since Task 017),
nothing from `modules/crawling` or any other module.

## Status log

- Investigated current state before scoping: `JobsPage` had no
  aggregate/queue-level view (only per-run rows); RQ already exposed
  everything needed (`Queue.count`, five registries, `Worker.all`)
  without new infrastructure; no existing product doc planned this as
  a feature.
- Scoped via `AskUserQuestion`: panel on `JobsPage` (not a new page),
  counts + failed-job list + worker liveness (not counts-only), and
  auto-refresh polling (not manual-refresh-only).
- Task brief and feature contract written (contract via a `planner`
  agent pass, given the cross-layer design decisions — endpoint
  placement, response shape, failed-id cap, worker-liveness
  definition, frontend component behavior — all needed to be explicit
  rather than left to the generator to guess).
- Implementation by a `generator` agent pass, in an isolated git
  worktree (main checkout had unrelated work in flight at the time).
- Evaluator pass: **PASS**, first attempt. Independently re-ran both
  backend (`901 passed`) and frontend (`126 passed`, 12 files) test
  suites, confirmed `ruff`/`pyright`/`tsc`/architecture checks clean,
  and specifically verified the trickiest acceptance criterion (AC-11:
  an all-zero, no-worker response must render as a normal state, not
  the destructive error `Alert`) by confirming the test asserts the
  *absence* of the error alert/role on that path, not just presence of
  the zero values.
- Contract moved from `docs/contracts/active/` to
  `docs/contracts/completed/` as part of this same update.

Status: **Done.**

## Required follow-up (not built by this task, reported per the contract)

1. Update `CLAUDE.md`'s directory listing to include
   `backend/app/domains/queue_stats/` and the three new frontend files
   (`api/queueStats.ts`, `schemas/queueStats.ts`,
   `components/QueueStatsPanel.tsx`).
2. When discovery/extraction adopt RQ (their own future contracts), no
   change to this feature's backend or frontend code is anticipated —
   `?queue=discovery`/`?queue=extraction` already work today. The only
   possible future follow-up is a frontend queue-selector control if
   multiple populated queues become worth surfacing simultaneously —
   not built here, deliberately out of scope.
