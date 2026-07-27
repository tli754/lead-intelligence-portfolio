Task 013 — Reconcile `domains/companies` and `modules/companies`

Raised in conversation (not a pre-written brief), preserved here verbatim
as the record of what was actually asked, per CLAUDE.md's Task workflow.
Not yet scoped into a contract — this file records the discovery and the
decision to defer it, not an approved plan.

Context: while evaluating Task 010 (wiring `CompaniesPage` to the real
`GET /api/companies` endpoint), the evaluator agent found — and verified
live against MongoDB — that this repository has two entirely separate
`Company` models with no bridge between them:

- `backend/app/domains/companies` (the original, flat model) — backs
  `POST /api/companies/import`, which is what `frontend/src/pages/
  ImportPage.tsx`'s paste-in importer actually calls. Writes to the
  `companies` collection.
- `backend/app/modules/companies` (the hexagonal model, per
  ARCHITECTURE.md's "Module convention") — backs `GET /api/companies`,
  `POST /api/companies`, and every pipeline module's `CompanyService
  Gateway` (discovery, crawling, extraction, evidence). Writes to the
  `companies_pipeline` collection.

`docs/product/lead-definition.md` already documents this as a known,
deliberate split ("nothing currently promotes a record from model 1 into
model 2 — they are populated independently"). It was not a surprise in
the abstract — but Task 010 was the first concrete feature where it
actually blocked something: a company pasted in via `ImportPage` does
not appear on the now-real `CompaniesPage`, because they're different
collections. Task 010's contract was corrected to narrow its acceptance
criterion to companies created via `modules/companies`'s API directly,
and this gap was deferred rather than blocking that task's merge — see
`docs/contracts/completed/wire-companies-list-to-real-api.md`'s "Known
Limitation" section.

The user was asked (via AskUserQuestion) how to handle the AC-02 gap and
chose: narrow the contract and merge Task 010 now, with this
reconciliation work opened as a separate follow-up task rather than
blocking. This file is that follow-up, not yet planned in detail.

Ask, concretely (loosely — this has not been through a scoping pass yet):
make the paste-in importer's output visible to the rest of the system —
i.e. make `ImportPage` results appear on `CompaniesPage`, and make them
usable by the discovery/crawling/extraction/evidence pipeline, all of
which are built against `modules/companies`, not `domains/companies`.

Open questions a future planner pass needs to resolve before this can
become a contract:

- Which model is authoritative going forward? `domains/companies` is
  simpler and is what the working paste-in import flow (Task 003/004
  era) already targets; `modules/companies` is the hexagonal model every
  pipeline module (Tasks 005-007) was built against and is the one
  `ARCHITECTURE.md` treats as the module-convention target. Given the
  whole pipeline already depends on `modules/companies`, retiring
  `domains/companies` in favor of it (rather than the reverse) seems
  likely to be the right direction, but this needs a real design pass,
  not an assumption baked into this brief.
- Migration path for existing data: the `companies` collection currently
  has real records (confirmed non-empty during Task 010's evaluation)
  that would need migrating into `companies_pipeline`'s schema, or an
  explicit decision to leave them stranded.
  Repointing `ImportPage`/`POST /api/companies/import`'s parsing and
  dedupe logic (`backend/app/domains/companies/parsing.py`, `service.py`)
  at `modules/companies`'s `CompanyService` instead of
  `domains/companies`'s `CompanyImportService` — or a one-time migration
  script plus deprecating the `domains/companies` import endpoint
  entirely.
- Whether this should be one task or split further (e.g. "migrate
  existing data" as one task, "repoint the import endpoint" as another).

Not scoped as allowed-paths / out-of-scope yet — that's the next
planner's job once this is picked up.
