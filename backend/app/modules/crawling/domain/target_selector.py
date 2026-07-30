"""Deterministic crawl-target selection from prioritized discovery candidates.

Pure, I/O-free, and independently testable — takes a plain candidate
shape (not `DiscoveredUrl` itself) so it can be unit tested without
constructing a full discovery model.

## Design decisions (documented, not left implicit)

**Deduplication.** Candidates are first grouped by `normalized_url`. When
more than one candidate shares a `normalized_url` (e.g. the same page
linked with two different raw hrefs), the "canonical" candidate for that
URL is chosen by: shallowest `depth` first, then whether it was found via
a preferred source (navigation/footer/robots/sitemap, over a body-link-
only discovery), then, if still tied, the candidate's position in the
input list (first wins) — fully deterministic.

**Manual overrides.** `manual_exclude_urls` is checked first and wins
unconditionally — even over `manual_include_urls` and even over a
priority-1 classification. `manual_include_urls` is checked next and
bypasses every remaining rule (priority, page-type lists, caps).

**Page-type allow/deny lists.** Applied to every remaining (non-manual)
candidate, including priority-1 ones — an operator who explicitly denies
a page type is assumed to mean it regardless of priority. `deny` wins
over `allow` when a type appears in both lists (checked first).

**Default-denied page types.** `PageType.ACCOUNT`/`CART`/`CHECKOUT`/
`SEARCH` are not part of the task brief's literal 23-item default
ordering list (see `PAGE_TYPE_ORDER` below) and are excluded by default
unless explicitly present in `include_page_types` — regardless of
whatever priority the caller attached to them.

**Priority tiers.** Priority-1 candidates (surviving the filters above)
are always included, uncapped — a total-page or per-category cap can
never remove them. `EXCLUDED`-priority candidates are never included
unless manually included. Priority-2 and priority-3 candidates share the
same capped-selection pool: per-category caps
(`max_product_pages`/`max_collection_pages`/`max_unknown_pages`) and the
overall `max_pages_per_company` cap apply to *both* tiers alike — proven
necessary by the contract's own AC-02, which caps a set of all-priority-2
candidates by category. Category caps: `PageType.PRODUCT` counts against
`max_product_pages`; `PageType.COLLECTION`/`PageType.CATEGORY` share
`max_collection_pages`; `PageType.UNKNOWN` counts against
`max_unknown_pages`; every other page type is bounded only by the overall
`max_pages_per_company` cap.

**Cap fill order.** Within the priority-2/3 pool, candidates are ordered
by `(priority, page-type order, depth, preferred-source, normalized_url)`
before applying caps — so priority-2 candidates fill available slots
before priority-3 ones, and, within one priority/page-type, shallower and
better-sourced candidates win a scarce slot first. This fill order is
separate from the *final* output order below.

**Final deterministic sort.** Regardless of fill order, the returned list
is always sorted by `(page-type order, priority, normalized_url)` — the
task brief's literal 23-item order (`PAGE_TYPE_ORDER`), with "sampled
product" mapped onto `PageType.PRODUCT`, and the four discovery-only page
types absent from that list (`ACCOUNT`/`CART`/`CHECKOUT`/`SEARCH`) sorted
after `UNKNOWN`, last.
"""

from pydantic import BaseModel, Field

from app.modules.crawling.domain.config import CrawlConfig
from app.modules.discovery.domain.enums import DiscoveryPriority, DiscoverySource, PageType

# The task brief's exact 23-item default page-type order (section 2).
# "sampled product" maps onto `PageType.PRODUCT` (documented in the
# module docstring above).
_ORDERED_PAGE_TYPES: tuple[PageType, ...] = (
    PageType.HOMEPAGE,
    PageType.WHOLESALE,
    PageType.TRADE,
    PageType.CONTACT,
    PageType.ABOUT,
    PageType.STORE_LOCATOR,
    PageType.CLICK_AND_COLLECT,
    PageType.SHIPPING,
    PageType.CAREERS,
    PageType.RETURNS,
    PageType.FAQ,
    PageType.SUPPORT,
    PageType.TEAM,
    PageType.BRANDS,
    PageType.SUBSCRIPTION,
    PageType.BLOG,
    PageType.NEWS,
    PageType.COLLECTION,
    PageType.CATEGORY,
    PageType.PRODUCT,
    PageType.PRIVACY,
    PageType.TERMS,
    PageType.UNKNOWN,
)

# `ACCOUNT`/`CART`/`CHECKOUT`/`SEARCH` are present in discovery's `PageType`
# enum but absent from the brief's 23-item list — sorted after `UNKNOWN`,
# last, in a fixed (alphabetical) order for full determinism.
_TRAILING_PAGE_TYPES: tuple[PageType, ...] = (
    PageType.ACCOUNT,
    PageType.CART,
    PageType.CHECKOUT,
    PageType.SEARCH,
)

PAGE_TYPE_ORDER: dict[PageType, int] = {
    page_type: index for index, page_type in enumerate(_ORDERED_PAGE_TYPES + _TRAILING_PAGE_TYPES)
}

DEFAULT_DENY_PAGE_TYPES: frozenset[PageType] = frozenset(_TRAILING_PAGE_TYPES)

_PRIORITY_ORDER: dict[DiscoveryPriority, int] = {
    DiscoveryPriority.PRIORITY_1: 1,
    DiscoveryPriority.PRIORITY_2: 2,
    DiscoveryPriority.PRIORITY_3: 3,
    DiscoveryPriority.EXCLUDED: 4,
}

_PREFERRED_SOURCES: frozenset[DiscoverySource] = frozenset(
    {
        DiscoverySource.NAVIGATION,
        DiscoverySource.FOOTER,
        DiscoverySource.ROBOTS,
        DiscoverySource.SITEMAP,
        DiscoverySource.SITEMAP_INDEX,
    }
)

_PRODUCT_PAGE_TYPES: frozenset[PageType] = frozenset({PageType.PRODUCT})
_COLLECTION_PAGE_TYPES: frozenset[PageType] = frozenset({PageType.COLLECTION, PageType.CATEGORY})
_UNKNOWN_PAGE_TYPES: frozenset[PageType] = frozenset({PageType.UNKNOWN})


class CrawlCandidate(BaseModel):
    """A minimal, discovery-shaped candidate URL to select from.

    Deliberately not `DiscoveredUrl` itself — see module docstring.
    """

    normalized_url: str
    page_type: PageType
    priority: DiscoveryPriority
    depth: int = 0
    discovery_sources: list[DiscoverySource] = Field(default_factory=list)


class SelectedTarget(BaseModel):
    """One candidate that survived selection, in final deterministic order."""

    normalized_url: str
    page_type: PageType
    priority: DiscoveryPriority
    depth: int
    discovery_sources: list[DiscoverySource]


def _is_preferred_source(candidate: CrawlCandidate) -> bool:
    return any(source in _PREFERRED_SOURCES for source in candidate.discovery_sources)


def _category_cap(page_type: PageType, config: CrawlConfig) -> tuple[str, int] | None:
    if page_type in _PRODUCT_PAGE_TYPES:
        return "product", config.max_product_pages
    if page_type in _COLLECTION_PAGE_TYPES:
        return "collection", config.max_collection_pages
    if page_type in _UNKNOWN_PAGE_TYPES:
        return "unknown", config.max_unknown_pages
    return None


def _page_type_sort_key(page_type: PageType) -> int:
    return PAGE_TYPE_ORDER.get(page_type, len(PAGE_TYPE_ORDER))


def _final_sort_key(candidate: CrawlCandidate) -> tuple[int, int, str]:
    return (
        _page_type_sort_key(candidate.page_type),
        _PRIORITY_ORDER[candidate.priority],
        candidate.normalized_url,
    )


def _fill_order_key(candidate: CrawlCandidate) -> tuple[int, int, int, int, str]:
    return (
        _PRIORITY_ORDER[candidate.priority],
        _page_type_sort_key(candidate.page_type),
        candidate.depth,
        0 if _is_preferred_source(candidate) else 1,
        candidate.normalized_url,
    )


def _dedupe_by_normalized_url(candidates: list[CrawlCandidate]) -> list[CrawlCandidate]:
    best_index: dict[str, int] = {}
    best_candidate: dict[str, CrawlCandidate] = {}
    for index, candidate in enumerate(candidates):
        existing = best_candidate.get(candidate.normalized_url)
        if existing is None:
            best_candidate[candidate.normalized_url] = candidate
            best_index[candidate.normalized_url] = index
            continue

        challenger_key = (candidate.depth, 0 if _is_preferred_source(candidate) else 1, index)
        existing_key = (
            existing.depth,
            0 if _is_preferred_source(existing) else 1,
            best_index[candidate.normalized_url],
        )
        if challenger_key < existing_key:
            best_candidate[candidate.normalized_url] = candidate
            best_index[candidate.normalized_url] = index

    return list(best_candidate.values())


def select_crawl_targets(
    candidates: list[CrawlCandidate],
    *,
    config: CrawlConfig,
    manual_include_urls: frozenset[str] = frozenset(),
    manual_exclude_urls: frozenset[str] = frozenset(),
    include_page_types: frozenset[PageType] = frozenset(),
    exclude_page_types: frozenset[PageType] = frozenset(),
) -> list[SelectedTarget]:
    """Selects the bounded, prioritized, deterministic set of crawl targets.

    See the module docstring for the full decision rationale.
    """
    deduped = _dedupe_by_normalized_url(candidates)

    always_included: list[CrawlCandidate] = []
    capped_pool: list[CrawlCandidate] = []

    for candidate in deduped:
        if candidate.normalized_url in manual_exclude_urls:
            continue
        if candidate.normalized_url in manual_include_urls:
            always_included.append(candidate)
            continue

        if candidate.page_type in exclude_page_types:
            continue
        if include_page_types:
            if candidate.page_type not in include_page_types:
                continue
        elif candidate.page_type in DEFAULT_DENY_PAGE_TYPES:
            continue

        if candidate.priority == DiscoveryPriority.EXCLUDED:
            continue
        if candidate.priority == DiscoveryPriority.PRIORITY_1:
            always_included.append(candidate)
            continue

        capped_pool.append(candidate)

    selected_urls: set[str] = {candidate.normalized_url for candidate in always_included}
    category_counts = {"product": 0, "collection": 0, "unknown": 0}
    total_count = len(always_included)

    for candidate in sorted(capped_pool, key=_fill_order_key):
        category = _category_cap(candidate.page_type, config)
        if category is not None:
            category_name, cap = category
            if category_counts[category_name] >= cap:
                continue

        if total_count >= config.max_pages_per_company:
            break

        selected_urls.add(candidate.normalized_url)
        if category is not None:
            category_counts[category[0]] += 1
        total_count += 1

    selected = [candidate for candidate in deduped if candidate.normalized_url in selected_urls]
    selected.sort(key=_final_sort_key)

    return [
        SelectedTarget(
            normalized_url=candidate.normalized_url,
            page_type=candidate.page_type,
            priority=candidate.priority,
            depth=candidate.depth,
            discovery_sources=list(candidate.discovery_sources),
        )
        for candidate in selected
    ]
