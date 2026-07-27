"""Unit tests for pure parsing functions (no I/O, no MongoDB)."""

from datetime import date
from pathlib import Path

from app.domains.companies.parsing import (
    detect_format,
    normalize_domain,
    parse_domain_list,
    parse_storeleads_html,
)

FIXTURE_PATH = Path(__file__).parents[2] / "fixtures" / "storeleads_sample.html"


# --- normalize_domain -------------------------------------------------


def test_normalize_domain_lowercases_and_trims() -> None:
    assert normalize_domain("  Example.COM  ") == "example.com"


def test_normalize_domain_strips_scheme() -> None:
    assert normalize_domain("https://example.com") == "example.com"
    assert normalize_domain("http://example.com") == "example.com"


def test_normalize_domain_strips_path_and_query() -> None:
    assert normalize_domain("example.com/some/path?x=1") == "example.com"


def test_normalize_domain_strips_trailing_dot() -> None:
    assert normalize_domain("example.com.") == "example.com"


def test_normalize_domain_keeps_leading_www() -> None:
    assert normalize_domain("www.example.com") == "www.example.com"


def test_normalize_domain_rejects_invalid_hostname() -> None:
    assert normalize_domain("not a domain!!") is None
    assert normalize_domain("") is None
    assert normalize_domain("nodothere") is None


# --- detect_format ------------------------------------------------------


def test_detect_format() -> None:
    """AC-10."""
    assert detect_format("example.com\nother.com") == "domain_list"
    html = '<vaadin-grid-cell-content slot="x"><div class="default">example.com</div>'
    assert detect_format(html) == "storeleads_html"


# --- parse_domain_list ---------------------------------------------------


def test_parse_domain_list_valid_lines() -> None:
    result = parse_domain_list("example.com\nother.com")
    assert [row.domain for row in result.rows] == ["example.com", "other.com"]
    assert result.skipped_duplicate_in_paste == []
    assert result.skipped_invalid == []


def test_parse_domain_list_skips_blank_lines() -> None:
    result = parse_domain_list("example.com\n\n   \nother.com")
    assert [row.domain for row in result.rows] == ["example.com", "other.com"]


def test_parse_domain_list_skips_invalid_with_reason() -> None:
    """AC-08."""
    result = parse_domain_list("example.com\nnot a domain!!\nother.com")
    assert [row.domain for row in result.rows] == ["example.com", "other.com"]
    assert len(result.skipped_invalid) == 1
    assert result.skipped_invalid[0].raw_value == "not a domain!!"
    assert result.skipped_invalid[0].reason == "not a valid domain"


def test_parse_domain_list_normalizes_scheme_and_path() -> None:
    result = parse_domain_list("https://Example.com/foo/bar")
    assert [row.domain for row in result.rows] == ["example.com"]


def test_parse_domain_list_reports_in_paste_duplicates() -> None:
    """AC-04: duplicate keeps the first occurrence, records the rest."""
    result = parse_domain_list("example.com\nEXAMPLE.com\nhttps://example.com/")
    assert [row.domain for row in result.rows] == ["example.com"]
    assert result.skipped_duplicate_in_paste == ["example.com", "example.com"]


# --- parse_storeleads_html (fixture-based) -------------------------------


def test_parse_storeleads_html_known_row() -> None:
    """AC-06."""
    raw_html = FIXTURE_PATH.read_text()

    result = parse_storeleads_html(raw_html)

    efilive = next(row for row in result.rows if row.domain == "www.efilive.com")
    assert efilive.url == "https://www.efilive.com"
    assert efilive.estimated_sales_yearly_usd == 5100094.68
    assert efilive.source_created_at == date(2016, 12, 30)
    assert efilive.emails == []
    assert efilive.phones == ["+64 9-534 1188", "+1 661-775-5620"]

    stihlshop = next(row for row in result.rows if row.domain == "www.stihlshop.co.nz")
    assert len(stihlshop.emails) == 4
    assert len(stihlshop.phones) == 2


def test_parse_storeleads_html_extracts_exact_row_count() -> None:
    raw_html = FIXTURE_PATH.read_text()

    result = parse_storeleads_html(raw_html)

    assert len(result.rows) == 43
    assert result.skipped_duplicate_in_paste == []
    assert result.skipped_invalid == []


def test_platform_version_never_captured() -> None:
    """AC-07: no row's parsed output contains a platform-version-like field."""
    raw_html = FIXTURE_PATH.read_text()

    result = parse_storeleads_html(raw_html)

    for row in result.rows:
        assert not hasattr(row, "platform_version")
        assert "platform_version" not in row._asdict()
