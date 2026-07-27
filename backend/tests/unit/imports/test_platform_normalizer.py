import pytest

from app.modules.imports.domain.platform_normalizer import normalize_platform


class TestNormalizePlatform:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Shopify", "shopify"),
            ("WooCommerce", "woocommerce"),
            ("Magento", "magento"),
            ("Custom", "custom"),
            ("SHOPIFY", "shopify"),
            ("  shopify  ", "shopify"),
        ],
    )
    def test_normalizes_known_platforms(self, raw: str, expected: str) -> None:
        assert normalize_platform(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "   ", "BigCommerce", "not a platform"])
    def test_unknown_or_blank_maps_to_none(self, raw: str | None) -> None:
        assert normalize_platform(raw) is None

    def test_does_not_infer_from_a_website(self) -> None:
        # normalize_platform never looks at anything but its own argument.
        assert normalize_platform(None) is None
