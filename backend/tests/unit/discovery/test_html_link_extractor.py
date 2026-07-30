from pathlib import Path

from app.modules.discovery.domain.enums import DiscoverySource
from app.modules.discovery.domain.html_link_extractor import extract_links

FIXTURES_DIR = Path(__file__).resolve().parents[4] / "fixtures" / "discovery"


def _load(name: str) -> str:
    return (FIXTURES_DIR / name).read_text()


class TestExtractLinksBasic:
    def test_extracts_body_links_and_canonical(self) -> None:
        result = extract_links(_load("homepage-basic.html"), source_url="https://example.com/")

        urls = {link.resolved_url for link in result.links}
        assert "https://example.com/about-us" in urls
        assert "https://example.com/contact-us" in urls
        assert result.canonical_url == "https://summitoutfitters.example.com/"


class TestExtractLinksNavigationAndFooter:
    def test_navigation_links(self) -> None:
        result = extract_links(
            _load("homepage-navigation-footer.html"), source_url="https://example.com/"
        )
        about = next(link for link in result.links if link.resolved_url.endswith("/about-us"))
        assert DiscoverySource.NAVIGATION in about.sources

    def test_footer_links(self) -> None:
        result = extract_links(
            _load("homepage-navigation-footer.html"), source_url="https://example.com/"
        )
        returns = next(
            link for link in result.links if link.resolved_url.endswith("/returns-and-exchanges")
        )
        assert DiscoverySource.FOOTER in returns.sources

    def test_relative_links_resolved_against_source(self) -> None:
        result = extract_links(
            _load("homepage-navigation-footer.html"), source_url="https://example.com/"
        )
        urls = {link.resolved_url for link in result.links}
        assert "https://example.com/products/trail-jacket" in urls

    def test_canonical_and_alternate(self) -> None:
        result = extract_links(
            _load("homepage-navigation-footer.html"), source_url="https://example.com/"
        )
        assert result.canonical_url == "https://summitoutfitters.example.com/"
        assert "https://summitoutfitters.example.com/fr" in result.alternate_urls

    def test_external_link_is_still_extracted(self) -> None:
        # Off-domain exclusion happens later (priority assignment), not here.
        result = extract_links(
            _load("homepage-navigation-footer.html"), source_url="https://example.com/"
        )
        urls = {link.resolved_url for link in result.links}
        assert "https://www.instagram.com/summitoutfitters" in urls


class TestExtractLinksMalformedHtml:
    def test_tolerates_malformed_markup(self) -> None:
        result = extract_links(_load("homepage-malformed.html"), source_url="https://example.com/")
        urls = {link.resolved_url for link in result.links}
        assert "https://example.com/about-us" in urls
        assert "https://example.com/contact-us" in urls
        assert "https://example.com/careers" in urls
        assert "https://example.com/faq" in urls


class TestExtractLinksDuplicatesAndIgnored:
    def test_duplicate_links_are_merged(self) -> None:
        result = extract_links(
            _load("homepage-duplicate-links.html"), source_url="https://example.com/"
        )
        about_links = [link for link in result.links if link.resolved_url.endswith("/about-us")]
        assert len(about_links) == 1
        merged = about_links[0]
        assert DiscoverySource.NAVIGATION in merged.sources
        assert DiscoverySource.FOOTER in merged.sources
        assert DiscoverySource.BODY_LINK in merged.sources
        assert "About Us" in merged.anchor_texts
        assert "about us" in merged.anchor_texts
        assert "About" in merged.anchor_texts

    def test_empty_href_ignored(self) -> None:
        result = extract_links(
            _load("homepage-duplicate-links.html"), source_url="https://example.com/"
        )
        assert all(link.resolved_url for link in result.links)

    def test_mailto_and_tel_ignored(self) -> None:
        result = extract_links(
            _load("homepage-duplicate-links.html"), source_url="https://example.com/"
        )
        urls = {link.resolved_url for link in result.links}
        assert not any(url.startswith("mailto:") for url in urls)
        assert not any(url.startswith("tel:") for url in urls)
        assert len(result.links) == 1  # only /about-us survives
