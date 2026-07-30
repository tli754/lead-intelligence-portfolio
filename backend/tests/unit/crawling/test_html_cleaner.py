"""Unit tests for `domain/html_cleaner.py` — pure, no I/O."""

from pathlib import Path

from app.modules.crawling.domain.html_cleaner import CLEANING_RULES_VERSION, clean_html

FIXTURES_DIR = Path(__file__).resolve().parents[3].parent / "fixtures" / "crawling"


def _read(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


class TestRemovesScripts:
    def test_no_script_bodies_remain(self) -> None:
        result = clean_html(_read("page-heavy-scripts.html"))

        assert "console.log" not in result.html
        assert "dataLayer" not in result.html
        assert "noisy script line" not in result.html

    def test_analytics_script_bodies_stripped_but_src_retained_for_signals(self) -> None:
        # The tag/`src` attribute is retained (not deleted outright) so
        # `domain/metadata_extractor.py` can still detect known analytics
        # hosts as technology signals from cleaned HTML — only the
        # executable body is ever stripped, uniformly for every script.
        result = clean_html(_read("page-heavy-scripts.html"))

        assert "google-analytics.com" in result.html
        assert "gtag(" not in result.html
        assert "fbq(" not in result.html


class TestRemovesStyles:
    def test_style_contents_removed(self) -> None:
        result = clean_html(_read("page-homepage.html"))
        assert "font-family" not in result.html


class TestRemovesEventHandlers:
    def test_on_star_attributes_stripped(self) -> None:
        result = clean_html(_read("page-heavy-scripts.html"))

        assert "onclick" not in result.html
        assert "onmouseover" not in result.html
        assert "onload" not in result.html


class TestRemovesTrackingPayloads:
    def test_tracking_pixel_image_removed(self) -> None:
        result = clean_html(_read("page-heavy-scripts.html"))
        assert "pixel.gif" not in result.html

    def test_nonce_and_integrity_stripped(self) -> None:
        result = clean_html(_read("page-heavy-scripts.html"))
        assert "nonce=" not in result.html
        assert "integrity=" not in result.html

    def test_comments_stripped(self) -> None:
        result = clean_html("<p>hello<!-- tracking comment --></p>")
        assert "tracking comment" not in result.html


class TestPreservesHeadings:
    def test_headings_preserved(self) -> None:
        result = clean_html(_read("page-homepage.html"))
        assert "<h1>" in result.html
        assert "Gear built for the trail" in result.html


class TestPreservesForms:
    def test_form_fields_preserved(self) -> None:
        result = clean_html(_read("page-wholesale.html"))
        assert "<form" in result.html
        assert "<label" in result.html
        assert "<select" in result.html
        assert "<button" in result.html


class TestPreservesLinks:
    def test_hrefs_preserved(self) -> None:
        result = clean_html(_read("page-homepage.html"))
        assert 'href="/wholesale"' in result.html
        assert 'href="/shipping"' in result.html


class TestPreservesTables:
    def test_table_rows_preserved(self) -> None:
        result = clean_html(_read("page-homepage.html"))
        assert "<table>" in result.html
        assert "Trailblazer Tent" in result.html
        assert "$199" in result.html


class TestPreservesImageAltText:
    def test_alt_text_preserved(self) -> None:
        result = clean_html(_read("page-homepage.html"))
        assert 'alt="Two-person tent pitched on a mountainside"' in result.html


class TestStructuredDataPreservedSeparately:
    def test_ld_json_kept_and_captured_separately(self) -> None:
        html = (
            '<html><body><script type="application/ld+json">{"@type": "Product"}</script>'
            "</body></html>"
        )
        result = clean_html(html)

        assert result.structured_data == ['{"@type": "Product"}']
        assert '{"@type": "Product"}' in result.html


class TestNoscriptAndSvgSuppressed:
    def test_noscript_removed(self) -> None:
        result = clean_html(_read("page-heavy-scripts.html"))
        assert "enable JavaScript" not in result.html

    def test_svg_subtree_removed(self) -> None:
        html = '<div><svg><path d="M0 0"/><circle r="5"/></svg><p>Visible text</p></div>'
        result = clean_html(html)

        assert "<svg" not in result.html
        assert "<path" not in result.html
        assert "Visible text" in result.html


class TestDeterministicOutput:
    def test_running_twice_is_byte_identical(self) -> None:
        raw = _read("page-heavy-scripts.html")
        first = clean_html(raw)
        second = clean_html(raw)
        assert first.html == second.html


class TestRulesVersion:
    def test_rules_version_is_recorded(self) -> None:
        result = clean_html("<p>hi</p>")
        assert result.rules_version == CLEANING_RULES_VERSION
