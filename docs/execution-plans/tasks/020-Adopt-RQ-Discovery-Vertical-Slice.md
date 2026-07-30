can I change the workflow to auto discocery and auto scrawl, worker pick
message from the queue

Clarified in conversation, across two questions:

1. Trigger scope: unified across both company-creation paths — bulk
   StoreLeads import (`POST /api/imports/storeleads`) AND single-company
   creation (`POST /api/companies`, which since Task 015 already
   auto-triggers discovery, but synchronously/inline). Both should use
   the same auto-enqueue mechanism going forward; Task 015's synchronous
   single-create trigger is being replaced, not left alongside a second
   mechanism.
2. Auto-crawl condition: always auto-enqueue a crawl run the moment a
   discovery run reaches ANY terminal status (`completed`,
   `completed_with_warnings`, or `failed`) — no conditional logic on
   target count or discovery outcome. Simplest, most predictable rule;
   crawling's own existing logic already handles "nothing to fetch"
   gracefully (zero targets selected, zero fetched, a normal terminal
   crawl run).

This is the follow-up ADR 0003 explicitly anticipated: it rejected
auto-triggering discovery on bulk import specifically because, at the
time, discovery ran synchronously inline — auto-triggering it for N
imported rows would have turned a sub-second import into a
multi-minute one, one row at a time. ADR 0003's own Consequences
section says this conclusion "should be revisited in a new ADR" once a
queue exists. A queue now exists for crawling (Task 017/ADR 0004), but
not yet for discovery — so making this workflow change properly means
first adopting the same RQ enqueue/execute split for
`WebsiteDiscoveryService.run_discovery` that Task 017 built for
`WebsiteCrawlService.start_crawl_run`, then wiring two new triggers on
top of both queues:
- Company creation (both paths) auto-enqueues a discovery job instead
  of running discovery inline.
- A discovery job's completion (any terminal status) auto-enqueues
  that company's crawl job.

Confirmed motivating context from this session: 18 companies were
bulk-imported, and discovery/crawling both had to be triggered by hand,
per company, via direct API calls — no button, no automation. The goal
is for import (bulk or single) to result in discovery and then
crawling happening automatically, with worker process(es) consuming
both queues, and the import/create endpoint's response no longer
blocking on any of it.

This task brief covers the discovery-module RQ adoption specifically
(the vertical-slice half, mirroring Task 017's pattern exactly). The
auto-chaining wiring itself (enqueue-on-create, chain-on-discovery-
completion) is covered by the sibling task brief
`021-Auto-Chain-Import-Discovery-Crawl.md`, since discovery must be
queued before anything can chain into it.
