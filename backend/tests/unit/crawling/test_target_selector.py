"""Unit tests for `domain/target_selector.py` — pure, no I/O."""

from app.modules.crawling.domain.config import CrawlConfig
from app.modules.crawling.domain.target_selector import CrawlCandidate, select_crawl_targets
from app.modules.discovery.domain.enums import DiscoveryPriority, DiscoverySource, PageType

P1 = DiscoveryPriority.PRIORITY_1
P2 = DiscoveryPriority.PRIORITY_2
P3 = DiscoveryPriority.PRIORITY_3
EXCLUDED = DiscoveryPriority.EXCLUDED


def _candidate(
    normalized_url: str,
    *,
    page_type: PageType = PageType.UNKNOWN,
    priority: DiscoveryPriority = P2,
    depth: int = 1,
    discovery_sources: list[DiscoverySource] | None = None,
) -> CrawlCandidate:
    return CrawlCandidate(
        normalized_url=normalized_url,
        page_type=page_type,
        priority=priority,
        depth=depth,
        discovery_sources=discovery_sources or [DiscoverySource.BODY_LINK],
    )


class TestPriorityOneAlwaysIncluded:
    def test_priority_one_always_included(self) -> None:
        priority_one = _candidate("https://example.com/", page_type=PageType.HOMEPAGE, priority=P1)
        overflow = [
            _candidate(
                f"https://example.com/product-{i}",
                page_type=PageType.PRODUCT,
                priority=P3,
            )
            for i in range(50)
        ]
        config = CrawlConfig(max_pages_per_company=5, max_product_pages=2)

        result = select_crawl_targets([priority_one, *overflow], config=config)

        assert any(target.normalized_url == priority_one.normalized_url for target in result)


class TestPerCategoryCaps:
    def test_per_category_caps(self) -> None:
        products = [
            _candidate(f"https://example.com/products/{i}", page_type=PageType.PRODUCT)
            for i in range(10)
        ]
        collections = [
            _candidate(f"https://example.com/collections/{i}", page_type=PageType.COLLECTION)
            for i in range(12)
        ]
        unknowns = [
            _candidate(f"https://example.com/unknown/{i}", page_type=PageType.UNKNOWN)
            for i in range(6)
        ]
        config = CrawlConfig(max_product_pages=5, max_collection_pages=8, max_unknown_pages=3)

        result = select_crawl_targets([*products, *collections, *unknowns], config=config)

        selected_products = [t for t in result if t.page_type == PageType.PRODUCT]
        selected_collections = [t for t in result if t.page_type == PageType.COLLECTION]
        selected_unknowns = [t for t in result if t.page_type == PageType.UNKNOWN]

        assert len(selected_products) == 5
        assert len(selected_collections) == 8
        assert len(selected_unknowns) == 3
        assert len(result) <= config.max_pages_per_company


class TestDeduplication:
    def test_deduplicates_by_normalized_url(self) -> None:
        config = CrawlConfig()
        first = _candidate("https://example.com/about", page_type=PageType.ABOUT, priority=P1)
        second = _candidate("https://example.com/about", page_type=PageType.ABOUT, priority=P1)

        result = select_crawl_targets([first, second], config=config)

        matching = [target for target in result if target.normalized_url == first.normalized_url]
        assert len(matching) == 1


class TestManualInclude:
    def test_manual_include_overrides_exclusion(self) -> None:
        config = CrawlConfig()
        excluded = _candidate(
            "https://example.com/cart", page_type=PageType.CART, priority=EXCLUDED
        )

        result = select_crawl_targets(
            [excluded], config=config, manual_include_urls=frozenset({excluded.normalized_url})
        )

        assert any(target.normalized_url == excluded.normalized_url for target in result)


class TestManualExclude:
    def test_manual_exclude_wins(self) -> None:
        config = CrawlConfig()
        priority_one = _candidate("https://example.com/", page_type=PageType.HOMEPAGE, priority=P1)

        result = select_crawl_targets(
            [priority_one],
            config=config,
            manual_exclude_urls=frozenset({priority_one.normalized_url}),
        )

        assert result == []


class TestDeterministicOutput:
    def test_deterministic_output(self) -> None:
        config = CrawlConfig()
        candidates = [
            _candidate("https://example.com/faq", page_type=PageType.FAQ),
            _candidate("https://example.com/", page_type=PageType.HOMEPAGE, priority=P1),
            _candidate("https://example.com/about", page_type=PageType.ABOUT, priority=P1),
            _candidate("https://example.com/blog", page_type=PageType.BLOG),
        ]

        first_run = select_crawl_targets(candidates, config=config)
        second_run = select_crawl_targets(candidates, config=config)

        assert [t.normalized_url for t in first_run] == [t.normalized_url for t in second_run]


class TestPageTypeOrdering:
    def test_output_follows_default_page_type_order(self) -> None:
        config = CrawlConfig()
        candidates = [
            _candidate("https://example.com/blog", page_type=PageType.BLOG, priority=P1),
            _candidate("https://example.com/", page_type=PageType.HOMEPAGE, priority=P1),
            _candidate("https://example.com/about", page_type=PageType.ABOUT, priority=P1),
        ]

        result = select_crawl_targets(candidates, config=config)

        assert [t.page_type for t in result] == [PageType.HOMEPAGE, PageType.ABOUT, PageType.BLOG]


class TestAllowDenyLists:
    def test_exclude_page_types_denies_even_priority_one(self) -> None:
        config = CrawlConfig()
        candidate = _candidate("https://example.com/blog", page_type=PageType.BLOG, priority=P1)

        result = select_crawl_targets(
            [candidate], config=config, exclude_page_types=frozenset({PageType.BLOG})
        )

        assert result == []

    def test_include_page_types_only_admits_listed_types(self) -> None:
        config = CrawlConfig()
        candidates = [
            _candidate("https://example.com/blog", page_type=PageType.BLOG, priority=P1),
            _candidate("https://example.com/news", page_type=PageType.NEWS, priority=P1),
        ]

        result = select_crawl_targets(
            candidates, config=config, include_page_types=frozenset({PageType.BLOG})
        )

        assert [t.page_type for t in result] == [PageType.BLOG]

    def test_deny_wins_over_allow_for_same_type(self) -> None:
        config = CrawlConfig()
        candidate = _candidate("https://example.com/blog", page_type=PageType.BLOG, priority=P1)

        result = select_crawl_targets(
            [candidate],
            config=config,
            include_page_types=frozenset({PageType.BLOG}),
            exclude_page_types=frozenset({PageType.BLOG}),
        )

        assert result == []

    def test_account_cart_checkout_search_denied_by_default(self) -> None:
        config = CrawlConfig()
        candidate = _candidate(
            "https://example.com/account", page_type=PageType.ACCOUNT, priority=P2
        )

        result = select_crawl_targets([candidate], config=config)

        assert result == []

    def test_account_included_when_explicitly_allow_listed(self) -> None:
        config = CrawlConfig()
        candidate = _candidate(
            "https://example.com/account", page_type=PageType.ACCOUNT, priority=P2
        )

        result = select_crawl_targets(
            [candidate], config=config, include_page_types=frozenset({PageType.ACCOUNT})
        )

        assert len(result) == 1


class TestMaximumPageCap:
    def test_total_cap_enforced_across_uncategorized_page_types(self) -> None:
        config = CrawlConfig(max_pages_per_company=5)
        candidates = [
            _candidate(f"https://example.com/about-{i}", page_type=PageType.ABOUT)
            for i in range(20)
        ]

        result = select_crawl_targets(candidates, config=config)

        assert len(result) == 5


class TestDepthAndSourceTiebreaks:
    def test_shallower_depth_wins_dedup(self) -> None:
        config = CrawlConfig()
        shallow = _candidate("https://example.com/about", page_type=PageType.ABOUT, depth=1)
        deep = _candidate("https://example.com/about", page_type=PageType.ABOUT, depth=3)

        result = select_crawl_targets([deep, shallow], config=config)

        assert len(result) == 1

    def test_excluded_priority_never_included_without_manual_override(self) -> None:
        config = CrawlConfig()
        candidate = _candidate(
            "https://example.com/checkout",
            page_type=PageType.CHECKOUT,
            priority=EXCLUDED,
        )

        result = select_crawl_targets([candidate], config=config)

        assert result == []
