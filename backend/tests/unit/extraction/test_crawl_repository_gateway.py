"""Unit tests for `CrawlRepositoryExtractionGateway`'s unchanged-page-
resolution logic (AC-31's unit half), against a fake `CrawlRepository`/
`ContentStorage` pair — no real MongoDB, no real filesystem."""

from datetime import UTC, datetime
from typing import Any

import pytest

from app.modules.crawling.domain.content_storage import ContentStorage
from app.modules.crawling.domain.enums import FetchMode, PageFetchStatus
from app.modules.crawling.domain.models import ContentReference, CrawledPage, CrawlRun
from app.modules.crawling.domain.repository import CrawledPagePage, CrawlRepository
from app.modules.discovery.domain.enums import DiscoveryPriority, PageType
from app.modules.extraction.domain.exceptions import CrawlRunNotFoundForExtractionError
from app.modules.extraction.infrastructure.crawl_repository_gateway import (
    CrawlRepositoryExtractionGateway,
)

NOW = datetime(2026, 7, 26, tzinfo=UTC)


class FakeCrawlRepository(CrawlRepository):
    def __init__(self, *, pages: dict[str, CrawledPage] | None = None, run: CrawlRun | None = None):
        self.pages = pages or {}
        self.run = run

    async def create_run(self, run):
        raise NotImplementedError

    async def update_run(self, run):
        raise NotImplementedError

    async def get_run(self, crawl_run_id):
        if self.run is not None and self.run.crawl_run_id == crawl_run_id:
            return self.run
        return None

    async def list_runs_by_company(self, company_id, *, page=1, page_size=20):
        raise NotImplementedError

    async def list_runs(self, *, status=None, page=1, page_size=20):
        raise NotImplementedError

    async def find_active_run(self, company_id, idempotency_key):
        raise NotImplementedError

    async def mark_run_cancelled(self, crawl_run_id):
        raise NotImplementedError

    async def save_target(self, target):
        raise NotImplementedError

    async def update_target(self, target):
        raise NotImplementedError

    async def find_target_by_url(self, crawl_run_id, normalized_url):
        raise NotImplementedError

    async def list_targets_by_run(self, crawl_run_id, **kwargs):
        raise NotImplementedError

    async def save_page(self, page):
        raise NotImplementedError

    async def get_page(self, page_id):
        return self.pages.get(page_id)

    async def list_pages_by_run(
        self,
        crawl_run_id,
        *,
        status=None,
        page_type=None,
        priority=None,
        fetch_mode=None,
        browser_required=None,
        include_failed=False,
        page=1,
        page_size=20,
    ):
        items = [p for p in self.pages.values() if p.crawl_run_id == crawl_run_id]
        return CrawledPagePage(items=items, total=len(items))

    async def get_latest_page_by_normalized_url(self, company_id, normalized_url):
        raise NotImplementedError


class FakeContentStorage(ContentStorage):
    def __init__(self, store: dict[str, bytes] | None = None):
        self._store = store or {}

    async def store_raw_content(self, **kwargs):
        raise NotImplementedError

    async def store_cleaned_content(self, **kwargs):
        raise NotImplementedError

    async def load_content(self, reference: ContentReference) -> bytes:
        return self._store[reference.reference_id]

    async def delete_content(self, reference):
        raise NotImplementedError


def _page(**overrides: Any) -> CrawledPage:
    defaults: dict[str, Any] = dict(
        page_id="page-1",
        crawl_run_id="run-1",
        company_id="company-1",
        discovery_run_id="discovery-1",
        original_url="https://example.com/",
        normalized_url="https://example.com/",
        page_type=PageType.HOMEPAGE,
        priority=DiscoveryPriority.PRIORITY_1,
        fetch_mode=FetchMode.HTTP,
        fetch_status=PageFetchStatus.FETCHED,
        fetched_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    defaults.update(overrides)
    return CrawledPage(**defaults)


@pytest.mark.asyncio
async def test_get_crawl_run_raises_when_missing():
    gateway = CrawlRepositoryExtractionGateway(FakeCrawlRepository(), FakeContentStorage())
    with pytest.raises(CrawlRunNotFoundForExtractionError):
        await gateway.get_crawl_run("missing-run")


@pytest.mark.asyncio
async def test_load_page_content_returns_inline_cleaned_html():
    page = _page(cleaned_html="<p>hello</p>")
    repository = FakeCrawlRepository(pages={page.page_id: page})
    gateway = CrawlRepositoryExtractionGateway(repository, FakeContentStorage())

    content = await gateway.load_page_content(page.page_id, "cleaned")
    assert content == b"<p>hello</p>"


@pytest.mark.asyncio
async def test_unchanged_page_resolves_via_predecessor():
    predecessor = _page(
        page_id="predecessor",
        cleaned_html="<p>original content</p>",
        extracted_text="original content",
    )
    unchanged = _page(
        page_id="unchanged-page",
        fetch_status=PageFetchStatus.UNCHANGED,
        unchanged_from_page_id="predecessor",
        cleaned_html=None,
        extracted_text=None,
    )
    repository = FakeCrawlRepository(
        pages={predecessor.page_id: predecessor, unchanged.page_id: unchanged}
    )
    gateway = CrawlRepositoryExtractionGateway(repository, FakeContentStorage())

    content = await gateway.load_page_content(unchanged.page_id, "cleaned")
    assert content == b"<p>original content</p>"

    text_content = await gateway.load_page_content(unchanged.page_id, "text")
    assert text_content == b"original content"


@pytest.mark.asyncio
async def test_missing_page_returns_none():
    gateway = CrawlRepositoryExtractionGateway(FakeCrawlRepository(), FakeContentStorage())
    assert await gateway.load_page_content("missing", "cleaned") is None


@pytest.mark.asyncio
async def test_list_pages_filters_by_status_and_page_type():
    homepage = _page(
        page_id="p1", page_type=PageType.HOMEPAGE, fetch_status=PageFetchStatus.FETCHED
    )
    failed = _page(page_id="p2", page_type=PageType.ABOUT, fetch_status=PageFetchStatus.FAILED)
    repository = FakeCrawlRepository(pages={homepage.page_id: homepage, failed.page_id: failed})
    gateway = CrawlRepositoryExtractionGateway(repository, FakeContentStorage())

    all_pages = await gateway.list_pages("run-1")
    assert len(all_pages) == 2

    eligible = await gateway.list_pages("run-1", statuses=[PageFetchStatus.FETCHED])
    assert [p.page_id for p in eligible] == ["p1"]

    by_type = await gateway.list_pages("run-1", page_types=[PageType.ABOUT])
    assert [p.page_id for p in by_type] == ["p2"]
