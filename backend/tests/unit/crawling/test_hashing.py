"""Unit tests for `domain/hashing.py` — pure, no I/O."""

from pathlib import Path

from app.modules.crawling.domain.hashing import compute_content_hashes, is_materially_unchanged
from app.modules.crawling.domain.html_cleaner import clean_html
from app.modules.crawling.domain.text_extractor import extract_text

FIXTURES_DIR = Path(__file__).resolve().parents[3].parent / "fixtures" / "crawling"


def _hashes_for_fixture(name: str):
    raw = (FIXTURES_DIR / name).read_bytes()
    cleaned = clean_html(raw.decode("utf-8"))
    text = extract_text(cleaned.html)
    return compute_content_hashes(raw, cleaned.html, text.text)


class TestIdenticalRawContent:
    def test_identical_bytes_produce_identical_hashes(self) -> None:
        raw = (FIXTURES_DIR / "page-homepage.html").read_bytes()
        cleaned = clean_html(raw.decode("utf-8"))
        text = extract_text(cleaned.html)

        first = compute_content_hashes(raw, cleaned.html, text.text)
        second = compute_content_hashes(raw, cleaned.html, text.text)

        assert first == second


class TestWhitespaceDifferences:
    def test_whitespace_only_difference_yields_same_structural_hash(self) -> None:
        cleaned_a = clean_html("<h1>Title</h1><p>Hello   world</p>")
        cleaned_b = clean_html("<h1>Title</h1>\n\n<p>Hello world</p>")
        text_a = extract_text(cleaned_a.html)
        text_b = extract_text(cleaned_b.html)

        hashes_a = compute_content_hashes(b"a", cleaned_a.html, text_a.text)
        hashes_b = compute_content_hashes(b"b", cleaned_b.html, text_b.text)

        assert hashes_a.structural_hash == hashes_b.structural_hash


class TestDynamicNoiseMarkedUnchanged:
    def test_dynamic_noise_marked_unchanged(self) -> None:
        previous = _hashes_for_fixture("page-dynamic-content-v1.html")
        current = _hashes_for_fixture("page-dynamic-content-v2.html")

        assert previous.raw_content_sha256 != current.raw_content_sha256
        assert previous.structural_hash == current.structural_hash
        assert is_materially_unchanged(previous, current) is True


class TestMeaningfulChangeDetected:
    def test_meaningful_change_detected(self) -> None:
        noise_pair_a = _hashes_for_fixture("page-dynamic-content-v1.html")
        noise_pair_b = _hashes_for_fixture("page-dynamic-content-v2.html")
        meaningful_change = _hashes_for_fixture("page-meaningful-change.html")

        assert noise_pair_a.structural_hash == noise_pair_b.structural_hash
        assert noise_pair_b.structural_hash != meaningful_change.structural_hash
        assert is_materially_unchanged(noise_pair_b, meaningful_change) is False


class TestHttp304Linkage:
    def test_previous_page_hashes_reused_when_conditional_304(self) -> None:
        # A 304 response carries no body — the crawl service reuses the
        # previous page's hashes wholesale rather than recomputing them.
        # This module doesn't fetch, so this just documents the contract:
        # identical `ContentHashes` objects are considered unchanged.
        previous = _hashes_for_fixture("page-homepage.html")
        assert is_materially_unchanged(previous, previous) is True
