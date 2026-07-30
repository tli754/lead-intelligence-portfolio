Task 015 — Auto-trigger discovery on company creation

Raised in conversation (not a pre-written brief), preserved here verbatim
as the record of what was actually asked, per CLAUDE.md's Task workflow.

Immediately after Task 014 (StoreLeads import UI) was committed, the user
asked to plan ADR 0003
(`docs/decisions/0003-auto-discovery-trigger-placement.md`), which had been
committed alongside Task 014's changes but not yet acted on. That ADR
records an architectural constraint — auto-triggering discovery must live
at the API router/composition layer, never inside `CompanyService`, and is
only currently authorized on the single-record `POST /api/companies` create
path, not the bulk import-commit path — and explicitly leaves implementing
point 3 of its Decision section ("if auto-discovery-on-create is wanted
now...") to a future feature contract.

Ask, concretely: implement that point 3 — wire
`WebsiteDiscoveryService.run_discovery` into `POST /api/companies`, inline
and synchronously (no `BackgroundTasks`), right after
`CompanyService.create_company` succeeds.

The ADR itself left one further question open: how the create endpoint's
response should reflect what a now-synchronous discovery run actually did.
Put to the user directly (via `AskUserQuestion`) before planning proceeded,
and answered: **re-fetch the company via `CompanyService.get_company(company_id)`
after discovery completes, and return that** — same `CompanyResponse`
shape as today, no new fields, just populated post-discovery.

This record captures the ask; the approved implementation plan lives in
the feature contract this task's "Decided" step produces
(`docs/contracts/active/015-auto-discovery-trigger.md`), and the actual
code changes are this task's "Built" step.
