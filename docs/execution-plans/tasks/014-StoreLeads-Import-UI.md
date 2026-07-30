Task 014 — Wire a StoreLeads-table import UI to `modules/imports`

Raised in conversation (not a pre-written brief), preserved here verbatim
as the record of what was actually asked, per CLAUDE.md's Task workflow.

The user first asked where ADR 0002
(`docs/decisions/0002-storeleads-import-targets-modules-imports.md`) was —
it existed on disk but was untracked by git. Having confirmed it, the user
said: "plan it." — asking for an implementation plan for the frontend work
that ADR 0002 explicitly identifies as not-yet-scoped (see that ADR's
"Consequences" section: "Building the StoreLeads import UI requires a new
frontend API client ... and either reworking `ImportPage.tsx` or adding a
new page — this is real, not-yet-scoped frontend work").

ADR 0002 itself left two product questions open for whoever picked this
work up (its "Explicitly open questions" section). Those were put to the
user directly (via AskUserQuestion) before planning proceeded, and answered:

1. **How does the new StoreLeads-table UI relate to the existing `/import`
   page?** → Replace `ImportPage.tsx` wholesale. Not a second tab, not a
   new route — `/import` keeps its path, its contents change.
2. **What happens to the legacy plain-domain-list paste / "quick add
   domain" form** (no equivalent in the `modules/imports` contract — no
   preview step, no platform/country/city)? → Drop it entirely, not kept
   alongside the new flow.

Ask, concretely: replace the paste-in importer's single-shot flow
(`ImportPage.tsx` → `importCompanies()` → `POST /api/companies/import`,
writing to the legacy `companies` collection nothing else reads) with a
paste → preview → commit flow against `modules/imports`' already-built,
already-tested endpoints (`POST /api/imports/storeleads/preview`,
`POST /api/imports/storeleads`), per ADR 0002's binding implementation
contract (exact request/response JSON, enum wire-values, and field-
normalization rules are already specified there and are not re-litigated
by this task).

This record captures the ask; the approved implementation plan lives in
the feature contract this task's "Decided" step produces
(`docs/contracts/active/014-storeleads-import-ui.md`, per CLAUDE.md's
workflow), and the actual code changes are this task's "Built" step.
