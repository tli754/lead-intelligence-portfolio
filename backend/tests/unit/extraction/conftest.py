"""Shared fixtures/helpers for extraction-module unit tests. No MongoDB, no network."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.modules.discovery.domain.enums import PageType
from app.modules.extraction.domain.extractor import PageContext

FIXTURES_DIR = Path(__file__).resolve().parents[4] / "fixtures" / "extraction"


def read_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def make_page_context(
    *,
    html: str,
    page_type: PageType = PageType.HOMEPAGE,
    page_id: str = "page-1",
    company_id: str = "company-1",
    source_url: str = "https://example-shop.com/",
    normalized_url: str | None = None,
    extracted_text: str | None = None,
    page_metadata: dict | None = None,
    raw_technology_signals: dict | None = None,
    fetched_at: datetime | None = None,
) -> PageContext:
    """Builds a `PageContext` directly from raw HTML — `extracted_text`
    defaults to a naive tag-stripped rendering (good enough for pattern-
    matching tests; extractors never assume real crawling output beyond
    what `PageContext` itself declares)."""
    import re

    text = extracted_text
    if text is None:
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()

    return PageContext(
        page_id=page_id,
        company_id=company_id,
        source_url=source_url,
        normalized_url=normalized_url or source_url,
        page_type=page_type,
        cleaned_html=html,
        extracted_text=text,
        page_metadata=page_metadata or {},
        raw_technology_signals=raw_technology_signals or {},
        fetched_at=fetched_at or datetime(2026, 7, 26, tzinfo=UTC),
        content_hashes={},
    )


@pytest.fixture
def page_context_factory():
    return make_page_context
