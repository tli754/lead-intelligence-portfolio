# ADR 0005: Auto-chain company creation → discovery → crawl, via RQ

- Status: Accepted
- Date: 2026-07-29
- Feature: `docs/contracts/active/020-rq-discovery-vertical-slice.md`
  (the immediate, concrete follow-through this ADR authorizes — adopts
  the RQ enqueue/execute split for `WebsiteDiscoveryService`, mirroring
  `docs/contracts/completed/017-rq-crawling-vertical-slice.md`'s pattern
  exactly). The *auto-chaining wiring itself* — enqueue-discovery-on-
  company-creation, enqueue-crawl-on-discovery-completion — is a
  second, not-yet-scoped feature contract (`021-Auto-Chain-Import-
  Discovery-Crawl`, per its task brief
  `docs/execution-plans/tasks/021-Auto-Chain-Import-Discovery-Crawl.md`),
  deliberately not designed by this ADR or by Task 020's contract.

## Context

Two prior ADRs bracket this decision:

`docs/decisions/0003-auto-discovery-trigger-placement.md` (Accepted,
2026-07-28) established *where* an auto-triggered discovery call is
architecturally allowed to live (the router/composition layer, never
inside `CompanyService` — see that ADR's Decision #1) and concluded
that, given the architecture at the time (no queue, `run_discovery`
running synchronously inline), auto-triggering discovery on the *bulk*
`POST /api/imports/storeleads` commit path was a bad trade: an N-row
import's HTTP response would block on N sequential real-website
discovery runs. It approved a narrower, still-synchronous trigger only
on the single-record `POST /api/companies` path (Decision #3) — later
built by Task 015, which added exactly this: `create_company` awaits
`WebsiteDiscoveryService.run_discovery` inline, before returning the
created company, with no `try`/`except` around the call (confirmed by
direct inspection of
`backend/app/modules/companies/api/router.py`'s `create_company`
handler and `get_discovery_service_for_company_creation` DI wiring).
Critically, ADR 0003's own Consequences section flagged this bulk-path
conclusion as provisional: "When Redis/a task queue is eventually
scaffolded ... this ADR's blocking-call conclusion for the bulk path
should be revisited in a new ADR rather than amended here."

`docs/decisions/0004-adopt-rq-as-queue-system.md` (Accepted,
2026-07-29) supplied that queue: it adopted RQ + Redis as this
repository's general background-job system and, per its own explicit
module-by-module rollout (Decision #3), applied it to crawling first
(`docs/contracts/completed/017-rq-crawling-vertical-slice.md`). ADR
0004's Decision #4 was explicit that it was *not itself* revisiting
ADR 0003 — "that revisiting is deliberately deferred again here, to a
future ADR scoped specifically to bulk-import auto-discovery once
discovery itself is queued." This ADR is that deferred revisiting.

The concrete trigger for doing it now: 18 companies were bulk-imported
in a real session and both discovery and crawling had to be started by
hand, per company, via direct API calls — no automation, no button.
The user asked directly whether the workflow could become "auto
discovery and auto crawl, worker pick[s up the] message from the
queue" (verbatim task brief,
`docs/execution-plans/tasks/020-Adopt-RQ-Discovery-Vertical-Slice.md`).
Two clarifying questions were asked in that conversation and answered
explicitly by the user, not assumed by planning:

1. **Trigger scope** — should the new auto-enqueue mechanism apply to
   both company-creation paths, or only to the bulk path (leaving
   Task 015's synchronous single-create trigger in place alongside a
   second, different mechanism)? **Answered: unified.** Both
   `POST /api/companies` and `POST /api/imports/storeleads` should use
   the same auto-enqueue-discovery mechanism. Task 015's synchronous
   trigger on the single-create path is being *replaced*, not left
   running alongside a queued path for bulk.
2. **Auto-crawl condition** — should a crawl only auto-start if
   discovery found a non-trivial number of targets, or succeeded
   outright? **Answered: unconditional.** A crawl run is auto-enqueued
   the instant a discovery run reaches *any* terminal status
   (`completed`, `completed_with_warnings`, or `failed`) — no
   conditional logic on target count or discovery outcome. The
   rationale offered and accepted: this is the simplest, most
   predictable rule, and crawling's own existing logic already
   tolerates "nothing to fetch" gracefully (zero targets selected,
   zero pages fetched, a normal terminal crawl run with an empty
   summary) — so a failed or empty discovery run does not need special
   handling to avoid crashing or corrupting a downstream crawl run.

These are recorded here as real, user-confirmed product decisions —
not defaults invented during planning.

Making this change properly requires discovery to be queued first:
`WebsiteDiscoveryService.run_discovery(company_id, *, cancellation_check=None)`
(`backend/app/modules/discovery/application/website_discovery_service.py`)
still runs entirely synchronously today, with no RQ enqueue/execute
split analogous to what Task 017 built for
`WebsiteCrawlService.start_crawl_run`. Auto-enqueueing discovery from
two HTTP request paths without first queuing discovery itself would
simply reproduce ADR 0003's original problem in a new place — an
auto-*enqueue* call is only cheap and safe to run inline if what it
enqueues is a fast, bounded operation (persist a `queued` run, return),
not the full discovery crawl. This is exactly the seam Task 017 already
cut for crawling (`enqueue_crawl_run` vs. `execute_crawl_run`), and it
must exist for discovery before any auto-chaining wiring is safe to
build.

## Decision

1. **ADR 0003's bulk-import blocking-call conclusion is superseded**,
   specifically and only insofar as a queue now removes the reason it
   was rejected. ADR 0003 itself is not edited — per CLAUDE.md's task
   workflow and per ADR 0003's own instruction ("should be revisited in
   a new ADR... rather than amended here"), this is a new ADR
   recording the updated decision, not a retroactive change to the old
   one. ADR 0003's reasoning about *why* the bulk path was rejected
   *given the architecture at the time* (no queue, synchronous inline
   execution) remains historically accurate and is not disputed.
2. **Discovery adopts the same RQ enqueue/execute split pattern Task
   017 built for crawling.** `WebsiteDiscoveryService.run_discovery` is
   split into an `enqueue_discovery_run` half (fast: persist a `queued`
   `DiscoveryRun`, no network I/O beyond resolving the company's
   domain) and an `execute_discovery_run` half (the actual homepage/
   robots/sitemap fetching), following Task 017's exact precedent for
   why this split is what makes auto-enqueueing safe to call inline.
   This is a general architectural decision; the concrete mechanics
   (method names, job wrapper functions, router changes, job timeout,
   worker queue-name registration) are designed in Task 020's own
   feature contract, not this ADR.
3. **Both company-creation paths auto-enqueue a discovery job per
   company**, replacing any synchronous inline call:
   - `POST /api/companies` (single-record creation) — replaces Task
     015's synchronous inline `run_discovery` call with an enqueue
     call onto the discovery RQ queue.
   - `POST /api/imports/storeleads` (bulk commit) — gains an
     auto-enqueue call it never had before (ADR 0003 originally
     rejected only the *blocking, synchronous* version of this; an
     enqueue call is fast and bounded exactly like the single-create
     path's new enqueue call, so the same reasoning that approved
     single-create's trigger now equally applies to bulk).
   Both paths use the *same* mechanism — no second, parallel trigger
   pattern is kept for either path. This was confirmed via the user's
   explicit "unified across both paths" answer above, not chosen as a
   planning default.
4. **A discovery job's completion, at any terminal status, auto-
   enqueues that company's crawl job**, unconditionally — no branching
   on `DiscoveryRun.status` value, target count, or presence of
   `error`. This was confirmed via the user's explicit "unconditional"
   answer above. Crawling's own existing "zero targets selected, zero
   fetched" handling (already exercised by its own test suite per
   `docs/contracts/completed/017-rq-crawling-vertical-slice.md`) is
   relied upon, not re-verified by this ADR, to make an unconditional
   auto-crawl safe even after a `failed` or targetless discovery run.
5. **The natural home for the "enqueue crawl on discovery completion"
   hook is inside the discovery RQ job wrapper function** (the
   as-yet-unbuilt analogue of Task 017's
   `backend/app/modules/crawling/infrastructure/rq_jobs.py`, once Task
   020 builds it) — symmetric to how Task 017's own
   `backend/app/modules/crawling/infrastructure/rq_jobs.py` is already
   the one place in the crawling module that knows a crawl run just
   reached a terminal status (it calls `execute_crawl_run`/
   `retry_failed` to completion and returns). This is a placement
   decision recorded here for continuity between planning passes; it
   is a design suggestion for whoever plans Task 021, not a directive
   this ADR enforces at the code level. **Task 020 does not build this
   hook.** It is explicitly out of scope for Task 020's contract — see
   that contract's own "Note for Task 021" callout — and remains
   unbuilt until Task 021's own feature contract designs and
   authorizes the concrete wiring (including whatever
   `discovery_run_id` → `crawl_run_id` linkage, error-handling policy,
   and idempotency-key handling that wiring needs).
6. **This ADR authorizes the general policy only — not the concrete
   wiring.** Task 020's feature contract designs discovery's RQ
   mechanics specifically (mirroring Task 017's pattern). A future,
   not-yet-written Task 021 feature contract designs the concrete
   auto-chain wiring itself: exactly where in
   `modules/companies/api/router.py`'s `create_company` and
   `modules/imports/**`'s commit path the enqueue-discovery call moves
   to, exactly what the discovery-job-wrapper's post-completion hook
   looks like, and how failures in either enqueue step are surfaced
   (or not) to the original HTTP caller. Neither of those designs is
   done by this ADR.
7. **Extraction is explicitly NOT covered.** This ADR does not
   authorize RQ adoption for `StructuredExtractionService`, and does
   not authorize any auto-chain from crawl completion into an
   extraction run. ADR 0004's module-by-module rollout already left
   extraction unqueued and untouched; this ADR does not change that.
   Per the Task 021 task brief's own words: "extraction module's own
   RQ adoption... not requested in this conversation, extraction has
   no network I/O and no documented latency problem today." Any future
   work on extraction chaining requires its own ADR and its own
   feature contract.

## Rationale

- **The reason ADR 0003 rejected bulk auto-discovery no longer
  applies once discovery is queued.** ADR 0003's entire objection was
  latency/failure coupling from a *synchronous, blocking* call inside
  a bulk endpoint — "turning a sub-second 'create records' call into a
  multi-minute one... coupling import success to arbitrary external
  websites being reachable." An enqueue call (per Task 017's own
  precedent, confirmed to do only a domain lookup plus one Mongo write
  before returning) does not have this property: it's the same class
  of fast, bounded operation ADR 0003 itself already approved for the
  single-create path in its Decision #3, just now available to the
  bulk path too because the "actually crawl a website" part has moved
  off the request/response cycle entirely.
- **Unifying both creation paths onto one mechanism, rather than
  running Task 015's synchronous trigger alongside a new queued bulk
  trigger, avoids two different auto-discovery behaviors coexisting
  for no reason.** A caller of either endpoint should get the same
  guarantee (a discovery job will run in the background) without
  needing to know which endpoint they used. This was the user's
  explicit choice, not merely a simplicity preference invented in
  planning — recorded as such per this ADR's own instruction to record
  it as a real decision.
- **Unconditional auto-crawl-on-discovery-completion is the simplest
  rule that is still correct**, because the alternative (conditional
  auto-crawl based on discovery outcome) requires designing and
  maintaining a policy for edge cases — e.g., "what target count counts
  as too few to bother crawling?" — that crawling's own code already
  answers by construction: a crawl run against a discovery run with
  zero accepted targets is not a special case crawling's own logic
  needs help handling, it's already a normal, well-defined terminal
  state. Adding conditional logic here would be solving a problem that
  does not exist.
- **Placing the future auto-chain hook inside the discovery job
  wrapper (not the router, not `CompanyService`) is the direct,
  intentional analogue of where Task 017's own crawling job wrapper
  already lives** — the one place in the codebase that already knows,
  synchronously, the exact moment a background pipeline stage finished
  and can act on it without any new signaling mechanism (no webhook, no
  polling, no second queue). This mirrors, rather than reinvents,
  Task 017's own established pattern.
- **Deferring extraction is consistent with ADR 0004's own stated
  reasoning for prioritizing crawling and now discovery over
  extraction** — extraction has no network I/O and no documented
  latency problem, so there is no motivating pressure to queue it or
  chain into it, and doing so now would be scope creep relative to
  what was actually asked in this conversation.

## Consequences

- `docs/contracts/active/020-rq-discovery-vertical-slice.md` becomes
  the immediate required next step: `WebsiteDiscoveryService` gains the
  enqueue/execute split, `backend/app/modules/discovery/infrastructure/rq_jobs.py`
  is created, `backend/app/worker.py`'s `QUEUE_NAMES` gains
  `"discovery"`, and `POST /api/companies/{company_id}/discovery-runs`
  changes from synchronous execution to enqueue-then-return-`queued`.
  This ADR does not implement any of that — it authorizes it.
- A second, not-yet-written feature contract (Task 021) is required
  before any of the following actually changes:
  - `modules/companies/api/router.py`'s `create_company` handler stops
    calling `WebsiteDiscoveryService.run_discovery` synchronously and
    instead enqueues a discovery job.
  - `modules/imports/**`'s bulk-commit path gains an auto-enqueue call
    it does not have today.
  - The discovery RQ job wrapper gains a post-completion hook that
    enqueues a crawl job.
  None of this is authorized to be built as part of Task 020 — Task
  020's own contract explicitly scopes it out (see that contract's
  "Out of Scope" section and its "Note for Task 021" callout).
- Until Task 021 lands, `POST /api/companies` keeps its current,
  Task-015-built synchronous discovery trigger unchanged, and
  `POST /api/imports/storeleads` keeps triggering nothing automatically
  — both are stale relative to this ADR's policy decision but are not
  regressions; they are simply not yet updated to match it.
- Extraction remains synchronous and unqueued, and no crawl-completion-
  into-extraction chaining exists or is authorized. This is unchanged
  by this ADR and is expected to require its own future ADR/contract
  pair if ever requested.
- `frontend/src/pages/JobsPage.tsx` and its status-mapping table
  (`frontend/src/api/jobs.ts`) already generalize across discovery,
  crawling, and (unused) extraction statuses via one shared mapping —
  confirmed by direct inspection. No frontend change is anticipated by
  this ADR, in Task 020, or (most likely) in Task 021 either, though
  that remains that future contract's call to confirm.
