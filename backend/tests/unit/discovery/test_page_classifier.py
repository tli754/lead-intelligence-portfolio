import pytest

from app.modules.discovery.domain.enums import PageType
from app.modules.discovery.domain.page_classifier import classify_page_type


class TestEachPageType:
    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("/", PageType.HOMEPAGE),
            ("/about", PageType.ABOUT),
            ("/about-us", PageType.ABOUT),
            ("/our-story", PageType.ABOUT),
            ("/contact", PageType.CONTACT),
            ("/contact-us", PageType.CONTACT),
            ("/get-in-touch", PageType.CONTACT),
            ("/wholesale", PageType.WHOLESALE),
            ("/wholesale-enquiries", PageType.WHOLESALE),
            ("/become-a-stockist", PageType.WHOLESALE),
            ("/trade", PageType.TRADE),
            ("/trade-account", PageType.TRADE),
            ("/trade-application", PageType.TRADE),
            ("/careers", PageType.CAREERS),
            ("/jobs", PageType.CAREERS),
            ("/work-with-us", PageType.CAREERS),
            ("/shipping", PageType.SHIPPING),
            ("/delivery", PageType.SHIPPING),
            ("/shipping-information", PageType.SHIPPING),
            ("/click-and-collect", PageType.CLICK_AND_COLLECT),
            ("/pickup", PageType.CLICK_AND_COLLECT),
            ("/store-pickup", PageType.CLICK_AND_COLLECT),
            ("/stores", PageType.STORE_LOCATOR),
            ("/store-locator", PageType.STORE_LOCATOR),
            ("/locations", PageType.STORE_LOCATOR),
            ("/our-stores", PageType.STORE_LOCATOR),
            ("/returns", PageType.RETURNS),
            ("/refund-policy", PageType.RETURNS),
            ("/returns-and-exchanges", PageType.RETURNS),
            ("/faq", PageType.FAQ),
            ("/faqs", PageType.FAQ),
            ("/frequently-asked-questions", PageType.FAQ),
            ("/support", PageType.SUPPORT),
            ("/help", PageType.SUPPORT),
            ("/help-centre", PageType.SUPPORT),
            ("/blog", PageType.BLOG),
            ("/journal", PageType.BLOG),
            ("/articles", PageType.BLOG),
            ("/news", PageType.NEWS),
            ("/press", PageType.NEWS),
            ("/media", PageType.NEWS),
            ("/team", PageType.TEAM),
            ("/our-team", PageType.TEAM),
            ("/people", PageType.TEAM),
            ("/brands", PageType.BRANDS),
            ("/our-brands", PageType.BRANDS),
            ("/subscription", PageType.SUBSCRIPTION),
            ("/subscribe", PageType.SUBSCRIPTION),
            ("/products/blue-shirt", PageType.PRODUCT),
            ("/product/blue-shirt", PageType.PRODUCT),
            ("/collections/summer", PageType.COLLECTION),
            ("/category/shoes", PageType.CATEGORY),
            ("/categories/shoes", PageType.CATEGORY),
            ("/privacy", PageType.PRIVACY),
            ("/privacy-policy", PageType.PRIVACY),
            ("/terms", PageType.TERMS),
            ("/terms-and-conditions", PageType.TERMS),
            ("/account", PageType.ACCOUNT),
            ("/login", PageType.ACCOUNT),
            ("/cart", PageType.CART),
            ("/checkout", PageType.CHECKOUT),
            ("/search", PageType.SEARCH),
        ],
    )
    def test_classifies_path(self, path: str, expected: PageType) -> None:
        result = classify_page_type(normalized_path=path)
        assert result.page_type == expected

    def test_unmatched_path_is_unknown(self) -> None:
        result = classify_page_type(normalized_path="/some-random-page-xyz")
        assert result.page_type == PageType.UNKNOWN
        assert result.confidence == 0


class TestAmbiguousPaths:
    def test_nested_path_still_matches_via_last_segment(self) -> None:
        result = classify_page_type(normalized_path="/pages/about-us")
        assert result.page_type == PageType.ABOUT

    def test_path_with_html_extension_still_matches(self) -> None:
        result = classify_page_type(normalized_path="/about-us.html")
        assert result.page_type == PageType.ABOUT

    def test_path_wins_over_conflicting_anchor_text(self) -> None:
        result = classify_page_type(normalized_path="/about-us", anchor_texts=["Contact Us"])
        assert result.page_type == PageType.ABOUT
        assert any(alt.page_type == PageType.CONTACT for alt in result.alternates)


class TestAnchorTextInfluence:
    def test_anchor_text_used_when_path_does_not_match(self) -> None:
        result = classify_page_type(normalized_path="/p123", anchor_texts=["Contact Us"])
        assert result.page_type == PageType.CONTACT
        assert 40 <= result.confidence <= 60

    def test_no_anchor_text_and_no_path_match_is_unknown(self) -> None:
        result = classify_page_type(normalized_path="/p123", anchor_texts=[])
        assert result.page_type == PageType.UNKNOWN


class TestConfidenceCalculation:
    def test_path_match_confidence_is_high(self) -> None:
        result = classify_page_type(normalized_path="/about-us")
        assert result.confidence >= 90

    def test_prefix_match_confidence(self) -> None:
        result = classify_page_type(normalized_path="/products/x")
        assert result.confidence == 90

    def test_more_corroborating_anchor_texts_increase_confidence(self) -> None:
        one = classify_page_type(normalized_path="/p1", anchor_texts=["Contact Us"])
        two = classify_page_type(
            normalized_path="/p2", anchor_texts=["Contact Us", "Contact"]
        )
        assert two.confidence >= one.confidence

    def test_sitemap_context_confidence(self) -> None:
        result = classify_page_type(normalized_path="/p999", sitemap_context="product")
        assert result.page_type == PageType.PRODUCT
        assert result.confidence == 70

    def test_homepage_confidence_is_maximum(self) -> None:
        result = classify_page_type(normalized_path="/")
        assert result.confidence == 100


class TestDeterministicResults:
    def test_same_input_produces_same_output(self) -> None:
        results = [classify_page_type(normalized_path="/about-us") for _ in range(5)]
        assert len({(r.page_type, r.confidence, r.rule_id) for r in results}) == 1

    def test_rule_id_is_recorded(self) -> None:
        result = classify_page_type(normalized_path="/about-us")
        assert result.rule_id
