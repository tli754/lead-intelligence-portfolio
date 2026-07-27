"""Unit tests for `domain/metadata_extractor.py` — pure, no I/O."""

from pathlib import Path

from app.modules.crawling.domain.html_cleaner import clean_html
from app.modules.crawling.domain.metadata_extractor import extract_page_metadata

FIXTURES_DIR = Path(__file__).resolve().parents[3].parent / "fixtures" / "crawling"


def _cleaned(name: str) -> str:
    raw = (FIXTURES_DIR / name).read_text(encoding="utf-8")
    return clean_html(raw).html


def _metadata(name: str):
    cleaned = _cleaned(name)
    return extract_page_metadata(
        cleaned, raw_html_size=1000, cleaned_html_size=len(cleaned), extracted_text_length=100
    )


class TestHomepageMetadata:
    def test_title(self) -> None:
        assert _metadata("page-homepage.html").title == "Acme Outdoor Gear — Home"

    def test_description(self) -> None:
        metadata = _metadata("page-homepage.html")
        assert "wholesale" in (metadata.meta_description or "").lower()

    def test_canonical(self) -> None:
        assert _metadata("page-homepage.html").canonical_url == "https://acme-outdoor.example.com/"

    def test_language(self) -> None:
        assert _metadata("page-homepage.html").language == "en-GB"

    def test_robots_meta(self) -> None:
        assert _metadata("page-homepage.html").robots_meta == "index, follow"

    def test_og_metadata(self) -> None:
        metadata = _metadata("page-homepage.html")
        assert metadata.og_site_name == "Acme Outdoor Gear"
        assert metadata.og_title == "Acme Outdoor Gear — Home"

    def test_generator(self) -> None:
        assert _metadata("page-homepage.html").generator == "Shopify"

    def test_shopify_detected_as_commerce_platform(self) -> None:
        metadata = _metadata("page-homepage.html")
        assert "shopify" in metadata.technology_signals["commerce_platform_markers"]

    def test_script_source_hosts_captured(self) -> None:
        metadata = _metadata("page-homepage.html")
        assert "cdn.shopify.com" in metadata.technology_signals["script_source_hosts"]
        assert "www.googletagmanager.com" in metadata.technology_signals["script_source_hosts"]

    def test_analytics_marker_detected(self) -> None:
        metadata = _metadata("page-homepage.html")
        assert "google-tag-manager" in metadata.technology_signals["analytics_markers"]

    def test_sizes_and_lengths_recorded(self) -> None:
        cleaned = _cleaned("page-homepage.html")
        metadata = extract_page_metadata(
            cleaned, raw_html_size=1234, cleaned_html_size=len(cleaned), extracted_text_length=99
        )
        assert metadata.html_size_bytes == 1234
        assert metadata.cleaned_html_size_bytes == len(cleaned)
        assert metadata.extracted_text_length == 99

    def test_module_has_zero_coupling_to_the_companies_module(self) -> None:
        import inspect

        import app.modules.crawling.domain.metadata_extractor as module

        assert "app.modules.companies" not in inspect.getsource(module)


class TestFrameworkMarkers:
    def test_react_shell_detected(self) -> None:
        metadata = _metadata("page-react-shell.html")
        assert "react" in metadata.technology_signals["framework_markers"]

    def test_nextjs_shell_detected(self) -> None:
        metadata = _metadata("page-next-shell.html")
        assert "nextjs" in metadata.technology_signals["framework_markers"]

    def test_vue_shell_detected(self) -> None:
        metadata = _metadata("page-vue-shell.html")
        assert "vue" in metadata.technology_signals["framework_markers"]
