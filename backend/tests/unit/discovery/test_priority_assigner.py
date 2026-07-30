import pytest

from app.modules.discovery.domain.config import DiscoveryConfig
from app.modules.discovery.domain.enums import DiscoveryPriority, PageType
from app.modules.discovery.domain.priority_assigner import assign_priority, has_excluded_extension


class TestPriorityTiers:
    @pytest.mark.parametrize(
        "page_type",
        [
            PageType.HOMEPAGE,
            PageType.ABOUT,
            PageType.CONTACT,
            PageType.WHOLESALE,
            PageType.TRADE,
            PageType.CAREERS,
            PageType.SHIPPING,
            PageType.CLICK_AND_COLLECT,
            PageType.STORE_LOCATOR,
        ],
    )
    def test_tier_1(self, page_type: PageType) -> None:
        priority = assign_priority(
            page_type=page_type,
            normalized_url="https://example.com/x",
            is_same_domain=True,
            config=DiscoveryConfig(),
        )
        assert priority == DiscoveryPriority.PRIORITY_1

    @pytest.mark.parametrize(
        "page_type",
        [
            PageType.RETURNS,
            PageType.FAQ,
            PageType.SUPPORT,
            PageType.BLOG,
            PageType.NEWS,
            PageType.TEAM,
            PageType.BRANDS,
            PageType.SUBSCRIPTION,
        ],
    )
    def test_tier_2(self, page_type: PageType) -> None:
        priority = assign_priority(
            page_type=page_type,
            normalized_url="https://example.com/x",
            is_same_domain=True,
            config=DiscoveryConfig(),
        )
        assert priority == DiscoveryPriority.PRIORITY_2

    @pytest.mark.parametrize(
        "page_type",
        [
            PageType.PRODUCT,
            PageType.COLLECTION,
            PageType.CATEGORY,
            PageType.PRIVACY,
            PageType.TERMS,
            PageType.UNKNOWN,
        ],
    )
    def test_tier_3(self, page_type: PageType) -> None:
        priority = assign_priority(
            page_type=page_type,
            normalized_url="https://example.com/x",
            is_same_domain=True,
            config=DiscoveryConfig(),
        )
        assert priority == DiscoveryPriority.PRIORITY_3


class TestExclusions:
    @pytest.mark.parametrize(
        "page_type", [PageType.ACCOUNT, PageType.CART, PageType.CHECKOUT, PageType.SEARCH]
    )
    def test_excluded_page_types(self, page_type: PageType) -> None:
        priority = assign_priority(
            page_type=page_type,
            normalized_url="https://example.com/x",
            is_same_domain=True,
            config=DiscoveryConfig(),
        )
        assert priority == DiscoveryPriority.EXCLUDED

    def test_external_domain_is_excluded_regardless_of_page_type(self) -> None:
        priority = assign_priority(
            page_type=PageType.ABOUT,
            normalized_url="https://other.com/about",
            is_same_domain=False,
            config=DiscoveryConfig(),
        )
        assert priority == DiscoveryPriority.EXCLUDED

    @pytest.mark.parametrize(
        "url",
        [
            "https://example.com/image.jpg",
            "https://example.com/video.mp4",
            "https://example.com/font.woff2",
            "https://example.com/style.css",
            "https://example.com/script.js",
            "https://example.com/archive.zip",
        ],
    )
    def test_excluded_file_extensions(self, url: str) -> None:
        assert has_excluded_extension(url) is True
        priority = assign_priority(
            page_type=PageType.UNKNOWN,
            normalized_url=url,
            is_same_domain=True,
            config=DiscoveryConfig(),
        )
        assert priority == DiscoveryPriority.EXCLUDED

    def test_pdf_is_not_excluded_by_extension(self) -> None:
        # PDFs may be "specifically useful later" (e.g. a wholesale terms
        # sheet) — deliberately not blanket-excluded, unlike archives.
        assert has_excluded_extension("https://example.com/terms.pdf") is False


class TestOverrides:
    def test_override_takes_precedence_over_default_map(self) -> None:
        config = DiscoveryConfig(priority_overrides={PageType.BLOG: DiscoveryPriority.PRIORITY_1})
        priority = assign_priority(
            page_type=PageType.BLOG,
            normalized_url="https://example.com/blog/post",
            is_same_domain=True,
            config=config,
        )
        assert priority == DiscoveryPriority.PRIORITY_1

    def test_no_override_falls_back_to_default(self) -> None:
        config = DiscoveryConfig(priority_overrides={})
        priority = assign_priority(
            page_type=PageType.BLOG,
            normalized_url="https://example.com/blog/post",
            is_same_domain=True,
            config=config,
        )
        assert priority == DiscoveryPriority.PRIORITY_2
