# Execution Plan: Extend Platform Normalization for PrestaShop/OpenCart (Task 018)

Status: Done
Contract: amendment within `docs/contracts/active/016-vaadin-grid-import-support.md`
(T4 "Amendment (Task 018...)" paragraph, AC-03/AC-03a)
Task brief: `docs/execution-plans/tasks/018-Extend-Platform-Normalization.md`

Small, targeted fix, not a new feature: `normalize_platform`
(`backend/app/modules/imports/domain/platform_normalizer.py`) only
recognized `{shopify, woocommerce, magento, custom}`. Task 016's own
contract explicitly documented — as accepted behavior — that a
`platform` cell value of `"PrestaShop"` normalizes to `null`. But
PrestaShop and OpenCart are exactly the two platforms in Task 016's own
motivating real fixtures (`.claude/data/storeLeads_prestaShop.html`,
`.claude/data/storeLeads_openCart.html`), confirmed by parsing both
directly. This was a premise defect in the original contract, not an
intentional scope limit — the fixtures were never checked against the
normalizer's known-platform set.

## Scope

Changed: `_KNOWN_PLATFORMS` in `platform_normalizer.py` now also
includes `"prestashop"`/`"opencart"` (case-insensitive, same pattern as
the existing four values). `test_platform_normalizer.py` gained four
parametrize cases. Deliberately did not add other real-world platforms
(e.g. BigCommerce) with no confirmed evidence in this repository's
fixtures — scope limited to what was actually proven missing.

Contract `016-vaadin-grid-import-support.md` was amended in place
(legitimate: it was still in `docs/contracts/active/`, never moved to
`completed/`) — T4's narrative corrected, AC-03's example changed from
PrestaShop (no longer unrecognized) to BigCommerce (still genuinely
unrecognized) with its verification pointer corrected to the actual
normalization test (it previously pointed at a parser-passthrough test
that never asserted `null`), and a new AC-03a added for the
PrestaShop/OpenCart-now-recognized case.

Verified end-to-end against the real fixtures, not just unit tests:
parsing `.claude/data/storeLeads_prestaShop.html` and
`.claude/data/storeLeads_openCart.html` through
`parse_storeleads_vaadin_grid` + `normalize_platform` now yields
`{prestashop, woocommerce}` and `{opencart}` respectively — zero rows
dropped to `null` that shouldn't be.

Zero other files changed by this fix. An evaluator pass separately
flagged an unrelated, pre-existing uncommitted change to
`frontend/src/pages/ImportPage.tsx` (a max-width style tweak,
predating this session) sitting in the same working tree — noted as
out of scope and left untouched, not part of this task's commit.

## Status log

- Investigated three distinct "platform" concepts in this codebase
  (StoreLeads-import `identity.platform`, crawled-site
  `technology.commerce_platform` signature detection, an unimplemented
  `identity.platform` catalogue slot) before scoping, via
  `AskUserQuestion` — user chose the StoreLeads-import normalizer fix.
- Task brief and contract amendment written directly in this session
  (small, well-understood, single-function change — no separate
  planner pass needed).
- Fix implemented and self-verified (unit + integration + full backend
  suite, ruff, pyright, manual end-to-end check against the real
  fixtures) before requesting evaluation.
- Evaluator pass: **PASS**. Independently confirmed AC-03/AC-03a,
  re-ran the full backend suite (894 passed), ruff/pyright clean,
  confirmed scope was minimal (no speculative platforms added), and
  independently re-parsed both real fixtures end-to-end. Flagged the
  unrelated stray `ImportPage.tsx` diff as out of scope (correctly —
  it predates this task and isn't part of it).

Status: **Done** for this specific normalizer fix.

## Known gap, not addressed by this task

`docs/contracts/active/016-vaadin-grid-import-support.md` as a whole
remains in `docs/contracts/active/` — Task 016's original, broader
scope (the Vaadin-grid parser itself) was committed to `main` directly
(`a2815d4`) without ever going through an evaluator pass or getting a
`docs/execution-plans/completed/` record, a pre-existing gap this
session did not create and did not attempt to close beyond the one
amendment described above. Moving 016's contract to `completed/` would
misrepresent that gap as resolved — left as-is, flagged here for
visibility.
