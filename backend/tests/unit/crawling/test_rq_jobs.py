"""Tests for `backend/app/modules/crawling/infrastructure/rq_jobs.py`'s
`_build_service` composition (Task 017 / AC-09). No real Redis, no real
MongoDB — `get_database` is monkeypatched to a stub double that only
needs to support `__getitem__` (every `Mongo*Repository.__init__` does
nothing more than store `database[collection_name]`; no connection is
ever attempted at construction time). This is a smoke test of the
composition only, not `asyncio.run`'s actual execution path against real
network I/O — that is already covered by the existing fakes-based
service suite (`test_website_crawl_service.py`, per AC-04/AC-06).
"""

from app.modules.crawling.application.website_crawl_service import WebsiteCrawlService
from app.modules.crawling.infrastructure import rq_jobs
from app.modules.crawling.infrastructure.company_service_gateway import CompanyServiceCrawlGateway
from app.modules.crawling.infrastructure.discovery_repository_gateway import (
    DiscoveryRepositoryCrawlGateway,
)
from app.modules.crawling.infrastructure.http_robots_policy_gateway import HttpRobotsPolicyGateway
from app.modules.crawling.infrastructure.httpx_page_fetcher import HttpxPageFetcher
from app.modules.crawling.infrastructure.local_filesystem_content_storage import (
    LocalFilesystemContentStorage,
)
from app.modules.crawling.infrastructure.mongo_crawl_repository import MongoCrawlRepository


class _StubCollection:
    """A placeholder object standing in for an `AsyncIOMotorCollection` —
    never called during `_build_service`, only stored for later use."""


class _StubDatabase:
    """A placeholder standing in for an `AsyncIOMotorDatabase` — supports
    only the `__getitem__` every `Mongo*Repository.__init__` needs."""

    def __getitem__(self, name: str) -> _StubCollection:
        return _StubCollection()


def test_build_service_composes_real_adapters(monkeypatch) -> None:
    monkeypatch.setattr(rq_jobs, "get_database", lambda: _StubDatabase())

    service = rq_jobs._build_service()

    assert isinstance(service, WebsiteCrawlService)
    assert isinstance(service._company_gateway, CompanyServiceCrawlGateway)
    assert isinstance(service._discovery_gateway, DiscoveryRepositoryCrawlGateway)
    assert isinstance(service._robots_gateway, HttpRobotsPolicyGateway)
    assert isinstance(service._repository, MongoCrawlRepository)
    assert isinstance(service._page_fetcher, HttpxPageFetcher)
    assert isinstance(service._content_storage, LocalFilesystemContentStorage)
