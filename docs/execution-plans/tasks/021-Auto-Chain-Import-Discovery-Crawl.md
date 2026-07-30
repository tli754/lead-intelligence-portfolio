can I change the workflow to auto discocery and auto scrawl, worker pick
message from the queue

(Same request as `020-Adopt-RQ-Discovery-Vertical-Slice.md` — see that
brief for the full context and the two clarifying answers. This brief
covers the auto-chaining wiring specifically, which depends on Task
020's discovery-RQ adoption already existing.)

Concretely, once discovery is queued (Task 020):

1. `POST /api/companies` (single-company creation) and
   `POST /api/imports/storeleads` (bulk commit) both auto-enqueue a
   discovery job for each newly-created company, instead of Task 015's
   synchronous inline `run_discovery` call (single-create path) or no
   trigger at all (bulk path, per ADR 0003's original rejection —
   superseded by the new ADR this task's planning produces).
2. When a discovery job reaches any terminal status
   (`completed`/`completed_with_warnings`/`failed`), a crawl job is
   automatically enqueued for that same company, using the
   just-finished discovery run's id — unconditionally, regardless of
   how many targets discovery found or whether it failed outright.
3. Worker process(es) (`python -m app.worker`) consume both queues
   continuously; the import/create HTTP response no longer blocks on
   discovery or crawling in any form.

Explicitly NOT covered by this task (left as-is, or handled by a
sibling task): extraction module's own RQ adoption (crawl completion
auto-chaining into extraction) — not requested in this conversation,
extraction has no network I/O and no documented latency problem
today, per ADR 0004's own reasoning for why crawling and now discovery
were prioritized over extraction.
