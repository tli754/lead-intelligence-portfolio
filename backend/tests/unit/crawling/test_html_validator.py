"""Unit tests for `domain/html_validator.py` — pure, no I/O."""

from pathlib import Path

import pytest

from app.modules.crawling.domain.config import CrawlConfig
from app.modules.crawling.domain.exceptions import EmptyResponseError, NonHtmlResponseError
from app.modules.crawling.domain.html_validator import (
    classify_blocked_or_challenge,
    validate_and_decode,
)

FIXTURES_DIR = Path(__file__).resolve().parents[3].parent / "fixtures" / "crawling"


def _read_bytes(name: str) -> bytes:
    return (FIXTURES_DIR / name).read_bytes()


class TestValidHtml:
    def test_valid_html_decodes_cleanly(self) -> None:
        raw = _read_bytes("page-homepage.html")
        result = validate_and_decode(raw, "text/html; charset=utf-8", CrawlConfig())

        assert "<h1>" in result.html
        assert result.decode_warnings == []
        assert result.truncated is False


class TestMalformedHtml:
    def test_malformed_html_still_decodes(self) -> None:
        raw = _read_bytes("page-malformed.html")
        result = validate_and_decode(raw, "text/html", CrawlConfig())

        assert "Missing closing tags" in result.html


class TestEmptyResponse:
    def test_empty_body_raises(self) -> None:
        with pytest.raises(EmptyResponseError):
            validate_and_decode(b"", "text/html", CrawlConfig())


class TestBinarySignature:
    def test_png_magic_bytes_rejected_even_with_html_content_type(self) -> None:
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
        with pytest.raises(NonHtmlResponseError):
            validate_and_decode(png_bytes, "text/html", CrawlConfig())


class TestIncorrectContentType:
    def test_real_image_content_type_rejected(self) -> None:
        with pytest.raises(NonHtmlResponseError):
            validate_and_decode(b"not actually an image", "image/png", CrawlConfig())

    def test_pdf_content_type_rejected(self) -> None:
        with pytest.raises(NonHtmlResponseError):
            validate_and_decode(b"%PDF-1.4 ...", "application/pdf", CrawlConfig())


class TestEncodingDetection:
    def test_non_utf8_bytes_decoded_via_replace_without_crashing(self) -> None:
        raw = _read_bytes("page-non-utf8.html")
        result = validate_and_decode(raw, "text/html; charset=windows-1252", CrawlConfig())

        assert "Bienvenue" in result.html
        assert result.encoding == "windows-1252"

    def test_unknown_charset_falls_back_to_utf8_replace(self) -> None:
        raw = "café".encode()
        result = validate_and_decode(raw, "text/html; charset=made-up-charset", CrawlConfig())

        assert result.decode_warnings != []
        assert result.html  # never crashes, always produces *something*


class TestTruncatedContent:
    def test_truncated_multibyte_sequence_is_flagged_not_raised(self) -> None:
        raw = _read_bytes("page-large.html")
        # Cut the buffer in the middle of a multi-byte UTF-8 character
        # (the fixture is full of accented characters like "café").
        cut_index = raw.index("é".encode()) + 1
        truncated_raw = raw[:cut_index]

        result = validate_and_decode(truncated_raw, "text/html; charset=utf-8", CrawlConfig())

        assert result.truncated is True
        assert result.decode_warnings != []
        assert result.html  # never raises


class TestChallengePageClassification:
    def test_cloudflare_challenge(self) -> None:
        html = _read_bytes("page-cloudflare-challenge.html").decode("utf-8")
        result = classify_blocked_or_challenge(html)

        assert result is not None
        assert result.classification == "cloudflare_challenge"
        assert result.rule_id == "challenge:cloudflare"

    def test_access_denied(self) -> None:
        html = _read_bytes("page-access-denied.html").decode("utf-8")
        result = classify_blocked_or_challenge(html)

        assert result is not None
        assert result.classification == "access_denied"

    def test_password_protected_storefront(self) -> None:
        html = _read_bytes("page-password-storefront.html").decode("utf-8")
        result = classify_blocked_or_challenge(html)

        assert result is not None
        assert result.classification == "password_protected_storefront"

    def test_ordinary_page_is_not_classified(self) -> None:
        html = _read_bytes("page-homepage.html").decode("utf-8")
        assert classify_blocked_or_challenge(html) is None

    def test_classification_is_deterministic(self) -> None:
        html = _read_bytes("page-cloudflare-challenge.html").decode("utf-8")
        first = classify_blocked_or_challenge(html)
        second = classify_blocked_or_challenge(html)
        assert first == second
