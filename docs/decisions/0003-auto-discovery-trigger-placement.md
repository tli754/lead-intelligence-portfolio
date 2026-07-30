# ADR 0003: Where an auto-triggered discovery run can (and can't) live

- Status: Accepted
- Date: 2026-07-28
- Feature: none yet — no feature contract currently proposes
  auto-triggering discovery on company creation. This ADR exists to
  record the architectural constraint and the concrete gap it exposes
  ahead of that contract, so whoever picks up "auto-run discovery after
  import/create" doesn't have to re-derive it from source.

## Context

Today, `WebsiteDiscoveryService.run_discovery(company_id)` only ever
runs when something explicitly calls
`POST /api/companies/{company_id}/discovery-runs`
(`modules/discovery/api/router.py:71-84`). No code path creates a
company and automatically kicks off discovery for it.

Two endpoints create companies:

1. `POST /api/companies` (`modules/companies/api/router.py:81-97`) —
   direct single-record creation via `CompanyService.create_company`.
   Not currently called by any frontend page.
2. `POST /api/imports/storeleads` (`modules/imports/api/router.py:55-63`)
   — the StoreLeads bulk-commit endpoint ADR 0002 designates as the
   real import path forward. Each row goes through
   `CompanyImportGateway.create_imported_company`
   (`infrastructure/company_service_gateway.py`), which itself wraps
   `CompanyService.create_company`.

The natural place to "just add a discovery call" would be inside
`CompanyService.create_company` itself. That's not available:
`modules/companies` is a leaf module every other module (`discovery`,
`crawling`, `evidence`, `extraction`, `imports`) depends on *through a
gateway it defines*, never the reverse
(`docs/architecture/dependency-rules.md`). Having `modules/companies`
call into `modules/discovery` would create the exact dependency cycle
that document forbids. So any trigger has to live above both services
— in a router / composition layer that already knows about both — not
inside either application service.

### The gap this exposes

`CompanyImportGateway.create_imported_company`
(`modules/imports/domain/gateway.py:38-52`) returns `None` by design —
the port was deliberately kept minimal (see its docstring: "Raises
`CompanyAlreadyExistsError` ... Any other exception is a genuine
per-row failure"). It never hands back the created company's ID.
`WebsiteDiscoveryService.run_discovery` needs exactly that ID as its
sole argument. So wiring auto-discovery into the import-commit path is
not "add one call at the router" — it first requires widening the
gateway's contract to return the new `company_id`, then threading that
back through `ImportRow`/`ImportResult` so the router has something to
act on. `POST /api/companies` doesn't have this gap:
`create_company`'s response already includes the new company's ID.

### The bigger tradeoff: synchronous, real network I/O

`run_discovery` fetches robots.txt, sitemap(s), and homepage candidates
inline, with no queue and no `BackgroundTasks` — consistent with every
other module's router (`discovery/api/router.py`, `crawling/api/router.py`,
and `extraction/api/router.py` each carry a comment to this effect,
matching CLAUDE.md's note that Redis/background workers are
deliberately not scaffolded yet). Bolting a discovery call onto the
*bulk* import-commit endpoint means an N-row paste's HTTP response
wouldn't return until N companies had each been crawled for discovery —
turning a sub-second "create records" call into a multi-minute one, and
coupling import success to arbitrary external websites being reachable
(one slow or dead site stalls or fails the whole import response).

## Decision

1. Auto-triggering discovery must be implemented at the API
   router/composition layer — never inside `CompanyService` or any
   other application service — because only that layer is allowed to
   depend on both `modules/companies` and `modules/discovery`.
2. Auto-triggering discovery is **not** to be wired into the bulk
   `POST /api/imports/storeleads` commit path as a blocking call. The
   latency/failure coupling described above is a bad trade in a
   no-queue architecture. Bulk auto-triggering after an N-row import
   should wait until an actual background-execution mechanism exists,
   and should get its own ADR when that mechanism is built — it is not
   authorized by this one.
3. If auto-discovery-on-create is wanted now, the only path this ADR
   approves is triggering it from `POST /api/companies`
   (`modules/companies/api/router.py:81`), the single-record create
   endpoint, calling `WebsiteDiscoveryService.run_discovery` inline
   after `create_company` succeeds, still synchronous — no
   `BackgroundTasks` — matching the "one thing per call" pattern the
   rest of this codebase already follows. This is still a real,
   not-yet-scoped change (routing/DI wiring, error handling if
   discovery fails after the company was already created) and requires
   its own feature contract before implementation; this ADR only
   clears the architectural question of *where* such a trigger is
   allowed to live.

## Rationale

- Dependency direction is non-negotiable per
  `docs/architecture/dependency-rules.md`; every existing cross-module
  interaction in this codebase goes through a gateway defined by the
  *depended-on* module, never the other way around. A trigger inside
  `CompanyService` would be the first violation of that rule.
- The router/composition layer is where this kind of cross-cutting
  orchestration already happens implicitly (e.g. `main.py` registering
  both routers) — extending it to actively call a second service after
  the first succeeds is consistent with that layer's existing role,
  not a new architectural concept.
- Single-record create (`POST /api/companies`) has no fan-out problem:
  one request, one company, one discovery run — the same shape as
  every other synchronous call in this codebase. Bulk import does not
  share that shape, and forcing it into the same pattern would
  degrade a currently sub-second endpoint into one bounded by the
  slowest website among N.

## Consequences

- Nothing changes yet. This ADR authorizes future work in the
  `POST /api/companies` path; it does not implement it. A feature
  contract is still required before code changes, including whatever
  error-handling policy is chosen for "company created but discovery
  failed" (e.g. return 201 with a warning vs. a partial-failure
  response — left to that contract).
- Any future work to auto-trigger discovery from the *import* path
  must first land a separate, smaller change: widening
  `CompanyImportGateway.create_imported_company`'s return type to
  surface the created `company_id` (or an equivalent lookup), and
  threading it through `ImportRow`/`ImportResult`. That change is
  useful independent of this ADR's queuing conclusion and is not itself
  blocked by it — only the *bulk auto-trigger* is blocked, not the
  gateway widening.
- When Redis/a task queue is eventually scaffolded (CLAUDE.md notes
  it's deliberately absent today), this ADR's blocking-call conclusion
  for the bulk path should be revisited in a new ADR rather than
  amended here — this one's job is to record why synchronous
  auto-discovery-on-bulk-import was rejected *given today's
  architecture*, not to forbid it forever.
