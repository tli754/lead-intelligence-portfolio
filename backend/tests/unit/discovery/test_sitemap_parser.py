import gzip
from pathlib import Path

from app.modules.discovery.domain.config import DiscoveryConfig
from app.modules.discovery.domain.sitemap_parser import parse_sitemap_document

FIXTURES_DIR = Path(__file__).resolve().parents[4] / "fixtures" / "discovery"


def _load_bytes(name: str) -> bytes:
    return (FIXTURES_DIR / name).read_bytes()


ROOT_DOMAIN = "summitoutfitters.example.com"


def _parse(
    name: str, *, content_type: str = "application/xml", config: DiscoveryConfig | None = None
):
    return parse_sitemap_document(
        _load_bytes(name),
        content_type=content_type,
        source_sitemap_url=f"https://{ROOT_DOMAIN}/{name}",
        root_domain=ROOT_DOMAIN,
        config=config or DiscoveryConfig(),
    )


class TestNormalUrlSet:
    def test_parses_urls(self) -> None:
        result = _parse("sitemap-basic.xml")
        assert result.is_index is False
        assert result.format == "xml"
        urls = {entry.normalized_url for entry in result.url_entries}
        assert "https://summitoutfitters.example.com/about-us" in urls
        assert result.total_url_count == 3

    def test_captures_lastmod(self) -> None:
        result = _parse("sitemap-basic.xml")
        about = next(e for e in result.url_entries if e.normalized_url.endswith("/about-us"))
        assert about.lastmod == "2024-01-15"


class TestSitemapIndex:
    def test_parses_index(self) -> None:
        result = _parse("sitemap-index.xml")
        assert result.is_index is True
        assert result.format == "xml_index"
        assert result.nested_sitemap_urls == [
            "https://summitoutfitters.example.com/sitemap-pages.xml",
            "https://summitoutfitters.example.com/sitemap-products.xml",
        ]

    def test_nested_index(self) -> None:
        result = _parse("sitemap-nested.xml")
        assert result.is_index is True
        assert result.nested_sitemap_urls == [
            "https://summitoutfitters.example.com/sitemap-index-2.xml"
        ]


class TestNamespaceHandling:
    def test_default_sitemap_namespace_is_tolerated(self) -> None:
        # sitemap-basic.xml declares the standard sitemaps.org namespace;
        # a namespace-unaware parser would fail to find <loc>.
        result = _parse("sitemap-basic.xml")
        assert len(result.url_entries) == 3


class TestGzipSitemap:
    def test_gzip_compressed_sitemap_is_decompressed(self) -> None:
        raw_xml = _load_bytes("sitemap-basic.xml")
        gzipped = gzip.compress(raw_xml)
        result = parse_sitemap_document(
            gzipped,
            content_type="application/gzip",
            source_sitemap_url="https://summitoutfitters.example.com/sitemap.xml.gz",
            root_domain=ROOT_DOMAIN,
            config=DiscoveryConfig(),
        )
        assert result.is_index is False
        assert len(result.url_entries) == 3

    def test_oversized_decompressed_payload_is_rejected(self) -> None:
        raw_xml = _load_bytes("sitemap-products-large.xml")
        gzipped = gzip.compress(raw_xml)
        tiny_config = DiscoveryConfig(max_response_size_bytes=100)
        result = parse_sitemap_document(
            gzipped,
            content_type="application/gzip",
            source_sitemap_url="https://summitoutfitters.example.com/sitemap.xml.gz",
            root_domain=ROOT_DOMAIN,
            config=tiny_config,
        )
        assert result.url_entries == []
        assert any("decompress" in warning for warning in result.warnings)


class TestDuplicateSitemapEntries:
    def test_duplicate_loc_entries_both_retained_by_parser(self) -> None:
        # De-duplication across the whole run happens in reconciliation,
        # not in a single document's parse — the parser reports exactly
        # what the document says.
        xml = b"""<?xml version="1.0"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <url><loc>https://summitoutfitters.example.com/about-us</loc></url>
        <url><loc>https://summitoutfitters.example.com/about-us</loc></url>
        </urlset>"""
        result = parse_sitemap_document(
            xml,
            content_type="application/xml",
            source_sitemap_url="https://summitoutfitters.example.com/sitemap.xml",
            root_domain=ROOT_DOMAIN,
            config=DiscoveryConfig(),
        )
        assert len(result.url_entries) == 2


class TestRecursionLoop:
    def test_self_referencing_index_entry_is_returned_but_not_followed_here(self) -> None:
        # Loop prevention (visited-set tracking across recursive fetches)
        # is the *application service's* job, not this single-document
        # parser's — it just reports whatever <sitemap> entries exist.
        xml = b"""<?xml version="1.0"?>
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <sitemap><loc>https://summitoutfitters.example.com/sitemap-index.xml</loc></sitemap>
        </sitemapindex>"""
        result = parse_sitemap_document(
            xml,
            content_type="application/xml",
            source_sitemap_url="https://summitoutfitters.example.com/sitemap-index.xml",
            root_domain=ROOT_DOMAIN,
            config=DiscoveryConfig(),
        )
        assert result.nested_sitemap_urls == ["https://summitoutfitters.example.com/sitemap-index.xml"]


class TestOffDomainUrls:
    def test_off_domain_url_entries_rejected(self) -> None:
        xml = b"""<?xml version="1.0"?>
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <url><loc>https://summitoutfitters.example.com/about-us</loc></url>
        <url><loc>https://evil.example.net/hack</loc></url>
        </urlset>"""
        result = parse_sitemap_document(
            xml,
            content_type="application/xml",
            source_sitemap_url="https://summitoutfitters.example.com/sitemap.xml",
            root_domain=ROOT_DOMAIN,
            config=DiscoveryConfig(),
        )
        urls = {entry.normalized_url for entry in result.url_entries}
        assert urls == {"https://summitoutfitters.example.com/about-us"}
        assert result.total_url_count == 1

    def test_off_domain_nested_sitemap_rejected(self) -> None:
        xml = b"""<?xml version="1.0"?>
        <sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <sitemap><loc>https://evil.example.net/sitemap.xml</loc></sitemap>
        </sitemapindex>"""
        result = parse_sitemap_document(
            xml,
            content_type="application/xml",
            source_sitemap_url="https://summitoutfitters.example.com/sitemap-index.xml",
            root_domain=ROOT_DOMAIN,
            config=DiscoveryConfig(),
        )
        assert result.nested_sitemap_urls == []
        assert any("off-domain" in warning for warning in result.warnings)


class TestMaximumUrlLimit:
    def test_large_product_sitemap_is_sampled(self) -> None:
        result = _parse("sitemap-products-large.xml")
        assert result.total_url_count == 300
        assert result.product_sitemap_detected is True
        assert len(result.url_entries) == DiscoveryConfig().sitemap_sample_size
        assert any("sampled" in warning for warning in result.warnings)

    def test_configurable_sample_size(self) -> None:
        result = _parse(
            "sitemap-products-large.xml", config=DiscoveryConfig(sitemap_sample_size=10)
        )
        assert len(result.url_entries) == 10
        assert result.total_url_count == 300


class TestMalformedSitemap:
    def test_malformed_xml_reported_as_warning_not_exception(self) -> None:
        result = _parse("sitemap-malformed.xml")
        assert result.url_entries == []
        assert result.is_index is False
        assert any("malformed" in warning.lower() for warning in result.warnings)


class TestPlainTextSitemap:
    def test_plain_text_url_list(self) -> None:
        text = (
            b"https://summitoutfitters.example.com/about-us\n"
            b"https://summitoutfitters.example.com/contact-us\n"
            b"# a comment line\n"
            b"\n"
        )
        result = parse_sitemap_document(
            text,
            content_type="text/plain",
            source_sitemap_url="https://summitoutfitters.example.com/sitemap.txt",
            root_domain=ROOT_DOMAIN,
            config=DiscoveryConfig(),
        )
        assert result.format == "plain_text"
        urls = {entry.normalized_url for entry in result.url_entries}
        assert urls == {
            "https://summitoutfitters.example.com/about-us",
            "https://summitoutfitters.example.com/contact-us",
        }
