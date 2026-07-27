import pytest

from app.modules.discovery.domain.url_normalizer import extract_hostname, normalize_discovered_url


class TestNormalizeDiscoveredUrl:
    def test_absolute_https_url(self) -> None:
        result = normalize_discovered_url("https://Example.com/Path")
        assert result.is_valid is True
        assert result.normalized_url == "https://example.com/Path"

    def test_relative_url_resolved_against_source_page(self) -> None:
        result = normalize_discovered_url(
            "/about", source_page_url="https://example.com/some/page"
        )
        assert result.is_valid is True
        assert result.normalized_url == "https://example.com/about"

    def test_fragments_removed(self) -> None:
        result = normalize_discovered_url("https://example.com/page#section-2")
        assert result.normalized_url == "https://example.com/page"

    def test_default_ports_removed(self) -> None:
        assert normalize_discovered_url("http://example.com:80/x").normalized_url == (
            "http://example.com/x"
        )
        assert normalize_discovered_url("https://example.com:443/x").normalized_url == (
            "https://example.com/x"
        )

    def test_non_default_port_is_retained(self) -> None:
        result = normalize_discovered_url("https://example.com:8443/x")
        assert result.normalized_url == "https://example.com:8443/x"

    def test_tracking_parameters_removed(self) -> None:
        result = normalize_discovered_url(
            "https://example.com/x?utm_source=news&utm_medium=email&gclid=abc&fbclid=def&real=1",
            retain_query=True,
        )
        assert result.normalized_url == "https://example.com/x?real=1"

    def test_retained_query_parameters_are_sorted(self) -> None:
        result = normalize_discovered_url(
            "https://example.com/x?zeta=1&alpha=2&beta=3", retain_query=True
        )
        assert result.normalized_url == "https://example.com/x?alpha=2&beta=3&zeta=1"

    def test_query_dropped_by_default(self) -> None:
        result = normalize_discovered_url("https://example.com/x?a=1")
        assert result.normalized_url == "https://example.com/x"

    def test_www_is_preserved_not_stripped(self) -> None:
        # Unlike modules/imports's website_normalizer, this normalizer does
        # NOT strip a leading www — discovery treats it as a distinct,
        # meaningful subdomain (homepage resolution tries both explicitly).
        result = normalize_discovered_url("https://www.example.com/")
        assert result.normalized_url == "https://www.example.com/"

    def test_meaningful_subdomains_preserved(self) -> None:
        result = normalize_discovered_url("https://shop.example.com/x")
        assert result.normalized_url == "https://shop.example.com/x"

    def test_internationalized_domain_is_idna_encoded(self) -> None:
        result = normalize_discovered_url("https://café.example.com/x")
        assert result.is_valid is True
        assert result.normalized_url == "https://xn--caf-dma.example.com/x"

    def test_trailing_slash_removed_except_root(self) -> None:
        assert normalize_discovered_url("https://example.com/path/").normalized_url == (
            "https://example.com/path"
        )
        assert normalize_discovered_url("https://example.com/").normalized_url == (
            "https://example.com/"
        )

    def test_repeated_slashes_collapsed(self) -> None:
        result = normalize_discovered_url("https://example.com//a//b")
        assert result.normalized_url == "https://example.com/a/b"

    @pytest.mark.parametrize("raw", ["not a url!!", "http://", "https://exa mple.com"])
    def test_malformed_url_rejected(self, raw: str) -> None:
        result = normalize_discovered_url(raw)
        assert result.is_valid is False
        assert result.rejection_reason is not None

    def test_localhost_rejected(self) -> None:
        result = normalize_discovered_url("http://localhost:3000/")
        assert result.is_valid is False

    def test_private_ipv4_rejected(self) -> None:
        result = normalize_discovered_url("http://192.168.1.1/")
        assert result.is_valid is False

    def test_private_ipv6_rejected(self) -> None:
        result = normalize_discovered_url("http://[fc00::1]/")
        assert result.is_valid is False

    def test_credentials_rejected(self) -> None:
        result = normalize_discovered_url("https://user:pass@example.com/")
        assert result.is_valid is False
        assert result.rejection_reason is not None
        assert "credentials" in result.rejection_reason

    @pytest.mark.parametrize(
        "raw",
        [
            "javascript:alert(1)",
            "mailto:test@example.com",
            "tel:+15551234567",
            "data:text/plain;base64,SGVsbG8=",
            "file:///etc/passwd",
            "ftp://example.com/file",
        ],
    )
    def test_unsupported_schemes_rejected(self, raw: str) -> None:
        result = normalize_discovered_url(raw)
        assert result.is_valid is False


class TestExtractHostname:
    def test_extracts_lowercase_hostname(self) -> None:
        assert extract_hostname("https://Example.com/path") == "example.com"

    def test_returns_none_for_missing_host(self) -> None:
        assert extract_hostname("not-a-url") is None
