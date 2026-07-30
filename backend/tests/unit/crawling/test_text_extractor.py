"""Unit tests for `domain/text_extractor.py` — pure, no I/O."""

from app.modules.crawling.domain.html_cleaner import clean_html
from app.modules.crawling.domain.text_extractor import extract_text


class TestHeadingsListsTables:
    def test_headings_paragraphs_lists_and_tables_preserved_in_order(self) -> None:
        html = (
            "<h1>Title</h1><p>Intro paragraph.</p>"
            "<ul><li>First item</li><li>Second item</li></ul>"
            "<table><tr><td>Cell one</td><td>Cell two</td></tr></table>"
        )
        result = extract_text(html)

        assert result.text.splitlines() == [
            "Title",
            "Intro paragraph.",
            "First item",
            "Second item",
            "Cell one",
            "Cell two",
        ]


class TestImageAltText:
    def test_meaningful_alt_text_included(self) -> None:
        html = '<img src="/a.jpg" alt="A scenic mountain trail at sunrise">'
        result = extract_text(html)
        assert "A scenic mountain trail at sunrise" in result.text

    def test_trivial_alt_text_excluded(self) -> None:
        html = '<img src="/a.jpg" alt="">'
        result = extract_text(html)
        assert result.text == ""


class TestScriptAndStyleExcluded:
    def test_script_and_style_text_never_extracted(self) -> None:
        html = "<script>var x = 'secret';</script><style>.a{color:red}</style><p>Visible</p>"
        result = extract_text(html)
        assert "secret" not in result.text
        assert "color" not in result.text
        assert result.text == "Visible"


class TestWhitespaceNormalization:
    def test_internal_whitespace_collapsed(self) -> None:
        html = "<p>Line one\n\n   with   extra   spaces</p>"
        result = extract_text(html)
        assert result.text == "Line one with extra spaces"


class TestTruncation:
    def test_long_text_truncated_at_exact_cap(self) -> None:
        html = "<p>" + ("a" * 1000) + "</p>"
        result = extract_text(html, max_length=100)

        assert len(result.text) == 100
        assert result.truncated is True

    def test_short_text_is_not_truncated(self) -> None:
        html = "<p>short</p>"
        result = extract_text(html, max_length=100)
        assert result.truncated is False


class TestRepeatedBoilerplateReduction:
    def test_repeated_nav_blocks_reduced(self) -> None:
        html = "".join("<li>Home</li>" for _ in range(10)) + "<p>Unique content</p>"
        result = extract_text(f"<ul>{html}</ul>")

        assert result.text.count("Home") == 2
        assert "Unique content" in result.text


class TestDeterministicOnCleanedHtml:
    def test_extraction_over_cleaned_html_preserves_order(self) -> None:
        raw = "<html><body><h1>Trailblazer Tent</h1><p>A rugged two-person tent.</p></body></html>"
        cleaned = clean_html(raw)
        result = extract_text(cleaned.html)

        assert result.text.splitlines() == ["Trailblazer Tent", "A rugged two-person tent."]
