# ADR 0001: Foundational decisions for the paste-in importer

- Status: Accepted
- Date: 2026-07-24
- Feature: `docs/contracts/active/paste-in-importer.md`

## Context

The paste-in importer is the first feature in this repository. It also
stands up the base backend/frontend skeleton. Three decisions made
during this feature are non-obvious enough, and consequential enough
for every future feature, to record here rather than leave implicit in
code.

## Decision (a): imported records are stored as `Company`, not `Lead`

The entity this feature creates is modeled and persisted as `Company`
(`backend/app/domains/companies/models.py`, `companies` MongoDB
collection), not `Lead`.

**Rationale:** This repository's own planning conventions (worked
examples referenced by the planning agent) use `CompanyRepository` and
`test_company_import.py` for exactly this kind of dedupe-by-domain
import, and reserve `LeadScore` as a separate, later, downstream
artifact produced by a future scoring feature. A paste-in import
produces raw, unscored data — calling it a "Lead" before any scoring or
qualification logic exists would overload a term this product treats as
meaningful (a scored/qualified entity). `docs/product/lead-definition.md`
is reserved for that future feature to define what actually promotes a
`Company` into a "Lead". This feature populates no scoring/qualification
field and therefore creates nothing called "Lead".

**Consequences:** Any future feature that scores or qualifies companies
must decide whether "Lead" becomes a new model/collection, a computed
view over `Company` + a score, or something else — that decision is
explicitly out of scope here and must not be pre-empted by this
feature's naming.

## Decision (b): `platform_version` is excluded from v1

The `Company` model has no `platform_version` field, and no parsing
function in `backend/app/domains/companies/parsing.py` attempts to
extract it, even though storelead.app's HTML export includes a "pv"
(Platform Version) column.

**Rationale:** Confirmed against the real sample file
(`docs/data/storeLeads.html`, and its copy used for tests,
`backend/tests/fixtures/storeleads_sample.html`, lines ~2900–3022):
platform-version values (e.g. `"2.4"`, `"2.3"`) are rendered as a
trailing block of bare version-like strings, decoupled from any row,
with no domain anchor adjacent to them. There is no reliable way to
associate them back to a specific row from the raw paste alone.
Silently guessing an association would produce wrong data attributed to
the wrong company — an unacceptable silent-failure mode for this
system.

The row-segmentation algorithm in `parse_storeleads_html` (domain
matches as row-boundary anchors) naturally never selects this block by
construction, not by an explicit filter: version-like strings such as
`2.4` do not match the hostname pattern (`normalize_domain`'s
validation regex requires at least one `.`-separated label of 2+
alphabetic characters), so they never become row anchors; and they
contain no `mailto:`/`tel:`/`href="https`-pattern content, so they
cannot contaminate the *last* row's chunk (which extends to end-of-file
and therefore does span the trailing version block) either. No code
exists whose job is "strip out platform_version" — there is simply
nothing in the extraction patterns that would ever match it.

**Consequences:** If storelead.app's export format changes to interleave
platform-version data per-row (rather than trailing all rows), this
decision should be revisited — see the Risks section of the paste-in
importer contract, which flags this assumption explicitly.

## Decision (c): dedupe policy is "ignore, never update"

When a paste contains a domain that already exists in the `companies`
collection, the import is skipped and reported under
`skipped_existing_in_db`. The existing document is left completely
unchanged — there is no merge/upsert/enrichment path in v1, even if the
new paste contains richer data (e.g. a plain domain-list import followed
later by a richer storeleads-HTML paste for the same domain).

**Rationale:** An upsert/merge policy raises real design questions this
feature does not need to answer to deliver its core value (getting raw
lead data into the system at all): which fields should a newer paste be
allowed to overwrite, should overwriting be silent or logged, what
happens to `imported_at` on a merge, etc. Deferring those questions
keeps this feature's scope to exactly "get data in, deduplicated by
domain" and keeps `Company` records simple and immutable, which also
makes reasoning about the system's data at any point in time
straightforward (a `Company` document never changes after creation).

**Consequences (explicit, documented limitation, not an oversight):**

- A domain first imported via a sparse plain-domain-list paste can never
  be enriched by a richer storeleads HTML paste for the same domain in
  v1. An upsert/merge feature is a reasonable near-term follow-up, out
  of scope here.
- Concurrent imports of the same brand-new domain from two clients could
  both pass the service-layer "not already in DB" check before either
  persists. This is mitigated at the MongoDB layer (a unique index on
  `domain`, defense-in-depth) and at the repository layer
  (`CompanyRepository.insert_many()` catches the resulting
  `DuplicateKeyError` per-document rather than raising it), not by any
  application-level locking.
