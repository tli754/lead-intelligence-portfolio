# Execution Plan: Wire Company Detail Page to the Real Backend API (Task 011)

Status: Done
Contract: `docs/contracts/completed/wire-company-detail-to-real-api.md`
Task brief: `docs/execution-plans/tasks/011-Wire-Company-Detail-to-Real-API.md`

Second of three follow-up tasks (010, 011, 012) splitting "wire the
frontend off mock data" into small, independently-planned pieces, per
CLAUDE.md's Task workflow. Built on top of Task 010 (merged first),
reusing its real-client conventions. Contract produced directly, based
on reading the real `modules/companies`/`modules/extraction`/
`modules/evidence` API schemas against the frontend's mock-derived Zod
schemas. Generator build done in an isolated git worktree, mirroring
Tasks 006/007/010's pattern.

## Scope

Frontend-only, as scoped: `frontend/src/api/companyDetail.ts` (new),
`frontend/src/api/fieldLabels.ts` (new), `frontend/src/api/queries.ts`,
`frontend/src/pages/CompanyDetailPage.tsx` (+ test). Zero backend files
touched — confirmed by the evaluator via `git diff --stat`.
`frontend/src/schemas/company.ts` and `frontend/src/components/
EvidenceViewer.tsx` were permitted-but-conditional paths in the
contract and turned out to need no changes at all — the existing schema
and component prop shapes already accommodated the real, composed data.

## Status log

- Contract produced and saved to `docs/contracts/active/`, based on a
  direct reading of `CompanyResponse`/`FactResponse`/`EvidenceResponse`
  against `CompanyDetail`/`EvidenceItem`'s Zod schemas, documenting 9
  concrete shape gaps up front (envelope/field mapping, `url` derivation,
  `emails`/`phones` field-path sourcing, `EvidenceStrength`-
  ->`ConfidenceLevel` mapping, `conflicts_with` limitation, `source`
  field choice).
- Generator build in an isolated git worktree
  (`.claude/worktrees/agent-aa840318d002b75ba`, branch
  `worktree-agent-aa840318d002b75ba`, based on Task 010's already-merged
  work), committing after each of T3 (field label map), T1+T2 (real
  client + composition function with full pagination), T4 (wiring) per
  the contract's suggested order.
- Generator did live end-to-end verification before declaring done —
  created a real company via `POST /api/companies` (explicitly avoiding
  the paste-in importer, per Task 013's already-documented
  `domains/companies`/`modules/companies` split), ran it through the
  real discovery->crawl->extraction pipeline against `example.com`, and
  confirmed `fetchCompanyDetail`'s output validated cleanly against
  `companyDetailSchema`. No Task-010-shaped contract-premise surprises
  found this time — the three endpoints matched the contract's
  assumptions exactly.
- Evaluator pass: **PASS**, first attempt. Independently re-verified all
  9 acceptance criteria, re-ran the full test/build/typecheck suite (72
  passing tests, clean `tsc --noEmit`/`build`), and additionally ran its
  own live pipeline round-trip (fresh scratch database, dropped after
  use) rather than trusting the generator's report. Cross-checked the
  generator's four documented deviations against backend source
  directly:
  - `workflow.shortlisted`/`.notesCount` sourced from real
    `CompanyResponse` fields (more accurate than Task 010's list-page
    derivation trick, which only exists because the *list* endpoint
    lacks these fields) — confirmed correct.
  - `url` derived as `https://${domain}` — a reasonable, low-risk,
    code-documented interpretation slightly beyond the contract's
    literal wording (which specified the source field but not a
    scheme); noted as non-blocking.
  - `emails`/`phones` sourced from `FactRecord.value` (bare `string[]`),
    not `normalized_value` (confirmed via `reconciliation.py`/
    `organisation_extractor.py` to be a `list[dict]` instead — using it
    would have been a bug).
  - `source` mapped from `evidenceType`, matching the contract's "either
    is defensible" guidance for that gap.
  - Verified the `FIELD_LABELS` map's 52 entries against
    `field_catalogue.py`'s full `FieldPath` enum by direct enumeration,
    not spot-checking.
- Merged to `main` via `git merge --no-ff worktree-agent-
  aa840318d002b75ba`. This file and the contract move to their
  `completed/` counterparts as part of this same update.

Status: **Done.**

Known limitation carried forward (documented in the contract, not a
defect): `evidence[].conflicts_with` is hardcoded `[]` for all real
data — `EvidenceViewer`'s "Conflicting evidence" banner won't fire until
a future task wires in `FactConflictResponse` data (keyed by
`field_path`+`candidate_ids`, not evidence IDs, so this needs its own
design work). `score`/`score_factors` remain `null`/`[]` pending a
scoring module that doesn't exist yet (see Task 008, AI analysis, which
explicitly excludes scoring).
