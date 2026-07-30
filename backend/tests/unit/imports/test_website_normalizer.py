import pytest

from app.modules.imports.domain.website_normalizer import (
    WebsiteNormalizationError,
    normalize_website,
)


class TestNormalizeWebsite:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("https://example.co.nz", "example.co.nz"),
            ("http://www.example.co.nz/", "example.co.nz"),
            ("example.co.nz", "example.co.nz"),
            ("shop.example.co.nz/path", "shop.example.co.nz"),
            ("EXAMPLE.CO.NZ", "example.co.nz"),
            ("example.co.nz.", "example.co.nz"),
            ("example.com:8080", "example.com"),
            ("https://example.com?query=1#section", "example.com"),
            ("www.example.com", "example.com"),
        ],
    )
    def test_normalizes(self, raw: str, expected: str) -> None:
        assert normalize_website(raw) == expected

    def test_preserves_meaningful_subdomains_other_than_www(self) -> None:
        assert normalize_website("shop.example.co.nz/path") == "shop.example.co.nz"
        assert normalize_website("https://www.shop.example.co.nz") == "shop.example.co.nz"

    def test_rejects_empty_value(self) -> None:
        with pytest.raises(WebsiteNormalizationError):
            normalize_website("   ")

    def test_rejects_localhost(self) -> None:
        with pytest.raises(WebsiteNormalizationError):
            normalize_website("http://localhost:3000")

    def test_rejects_localhost_subdomain(self) -> None:
        with pytest.raises(WebsiteNormalizationError):
            normalize_website("http://app.localhost")

    @pytest.mark.parametrize(
        "raw",
        [
            "http://192.168.1.10",
            "http://8.8.8.8",
            "http://[::1]",
        ],
    )
    def test_rejects_ip_addresses(self, raw: str) -> None:
        with pytest.raises(WebsiteNormalizationError):
            normalize_website(raw)

    @pytest.mark.parametrize(
        "raw",
        [
            "not a domain!!",
            "http://",
            "http://exa_mple.com",
            "http://-example.com",
        ],
    )
    def test_rejects_malformed_domains(self, raw: str) -> None:
        with pytest.raises(WebsiteNormalizationError):
            normalize_website(raw)

    @pytest.mark.parametrize(
        "raw",
        [
            "http://intranet",
            "http://fileserver.local",
            "http://printer.internal",
            "http://server.lan",
        ],
    )
    def test_rejects_private_internal_hostnames(self, raw: str) -> None:
        with pytest.raises(WebsiteNormalizationError):
            normalize_website(raw)

    def test_idna_encodes_non_ascii_hosts(self) -> None:
        assert normalize_website("https://xn--exmple-cua.com") == "xn--exmple-cua.com"
        assert normalize_website("café.example.com") == "xn--caf-dma.example.com"
