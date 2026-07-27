"""Shared fixtures for the discovery-module integration tests.

No real MongoDB and no real HTTP — the Company module (`modules/companies`)
*is* available in this worktree (confirmed by direct inspection), but
these tests still use fakes throughout for speed/determinism, the same
way `modules/imports`'s integration tests do. No shared `app.main.app`
either: the discovery router is deliberately not registered there, so
these tests build their own minimal FastAPI app with just this router.
"""

from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.modules.companies.domain.enums import ProcessingStatus
from app.modules.discovery.api.router import (
    get_company_discovery_gateway,
    get_discovery_repository,
    get_http_discovery_client,
    router,
)
from app.modules.discovery.domain.exceptions import (
    CompanyNotFoundForDiscoveryError,
    DisallowedHostError,
    TimeoutFetchError,
)
from app.modules.discovery.domain.gateway import CompanyDiscoveryGateway
from app.modules.discovery.domain.http_client import (
    FetchResult,
    HomepageResolutionResult,
    HttpDiscoveryClient,
)
from app.modules.discovery.domain.models import DiscoveredUrl, DiscoveryRun
from app.modules.discovery.domain.repository import DiscoveredUrlPage, DiscoveryRepository


class FakeCompanyDiscoveryGateway(CompanyDiscoveryGateway):
    def __init__(self, *, domains: dict[str, str] | None = None) -> None:
        self._domains = dict(domains or {"company-1": "example.com"})
        self.status_updates: list[tuple[str, ProcessingStatus]] = []
        self.latest_run_updates: list[tuple[str, str]] = []

    async def get_company_domain(self, company_id: str) -> str:
        try:
            return self._domains[company_id]
        except KeyError as error:
            raise CompanyNotFoundForDiscoveryError(company_id) from error

    async def update_processing_status(self, company_id: str, status: ProcessingStatus) -> None:
        self.status_updates.append((company_id, status))

    async def update_latest_discovery_run(self, company_id: str, discovery_run_id: str) -> None:
        self.latest_run_updates.append((company_id, discovery_run_id))


class FakeDiscoveryRepository(DiscoveryRepository):
    def __init__(self) -> None:
        self._runs: dict[str, DiscoveryRun] = {}
        self._urls: dict[str, DiscoveredUrl] = {}

    async def create_run(self, run: DiscoveryRun) -> DiscoveryRun:
        self._runs[run.discovery_run_id] = run
        return run

    async def update_run(self, run: DiscoveryRun) -> DiscoveryRun | None:
        if run.discovery_run_id not in self._runs:
            return None
        self._runs[run.discovery_run_id] = run
        return run

    async def get_run(self, discovery_run_id: str) -> DiscoveryRun | None:
        return self._runs.get(discovery_run_id)

    async def get_latest_run_for_company(self, company_id: str) -> DiscoveryRun | None:
        candidates = [run for run in self._runs.values() if run.company_id == company_id]
        if not candidates:
            return None
        return max(candidates, key=lambda run: run.created_at)

    async def save_discovered_urls(self, urls: list[DiscoveredUrl]) -> list[DiscoveredUrl]:
        for url in urls:
            self._urls[url.discovered_url_id] = url
        return urls

    async def find_existing_url(
        self, discovery_run_id: str, normalized_url: str
    ) -> DiscoveredUrl | None:
        for url in self._urls.values():
            if url.discovery_run_id == discovery_run_id and url.normalized_url == normalized_url:
                return url
        return None

    async def list_discovered_urls(
        self,
        discovery_run_id: str,
        *,
        priority=None,
        page_type=None,
        source=None,
        include_excluded: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> DiscoveredUrlPage:
        items = [url for url in self._urls.values() if url.discovery_run_id == discovery_run_id]
        if priority is not None:
            items = [url for url in items if url.priority.value == priority]
        elif not include_excluded:
            items = [url for url in items if url.priority.value != "excluded"]
        if page_type is not None:
            items = [url for url in items if url.page_type == page_type]
        if source is not None:
            items = [url for url in items if source in url.discovery_sources]

        total = len(items)
        start = (page - 1) * page_size
        return DiscoveredUrlPage(items=items[start : start + page_size], total=total)


class FakeHttpDiscoveryClient(HttpDiscoveryClient):
    """Fully configurable canned-response fake — no real network access."""

    def __init__(
        self,
        *,
        homepage_success: bool = True,
        homepage_url: str = "https://example.com",
        homepage_html: str = "<html><body><a href='/about'>About</a></body></html>",
        homepage_failure_reason: str = "simulated homepage failure",
        robots_text: str | None = "Sitemap: https://example.com/sitemap.xml",
        robots_raises: bool = False,
        sitemaps: dict[str, bytes] | None = None,
        failing_sitemap_urls: set[str] | None = None,
    ) -> None:
        self._homepage_success = homepage_success
        self._homepage_url = homepage_url
        self._homepage_html = homepage_html
        self._homepage_failure_reason = homepage_failure_reason
        self._robots_text = robots_text
        self._robots_raises = robots_raises
        self._sitemaps = sitemaps or {}
        self._failing_sitemap_urls = failing_sitemap_urls or set()

    async def resolve_homepage(self, candidates: list[str]) -> HomepageResolutionResult:
        if not self._homepage_success:
            return HomepageResolutionResult(
                success=False,
                failure_reason=self._homepage_failure_reason,
                attempted_candidates=candidates,
            )
        return HomepageResolutionResult(
            success=True,
            homepage_url=self._homepage_url,
            html=self._homepage_html,
            attempted_candidates=candidates[:1],
        )

    async def fetch_html(self, url: str) -> FetchResult:
        raise NotImplementedError("not exercised via this fake outside resolve_homepage")

    async def fetch_text(self, url: str) -> FetchResult:
        if self._robots_raises:
            raise TimeoutFetchError(url)
        return FetchResult(
            status_code=200,
            content_type="text/plain",
            body=(self._robots_text or "").encode(),
            final_url=url,
        )

    async def fetch_binary(self, url: str) -> FetchResult:
        if url in self._failing_sitemap_urls:
            raise TimeoutFetchError(url)
        if url in self._sitemaps:
            return FetchResult(
                status_code=200,
                content_type="application/xml",
                body=self._sitemaps[url],
                final_url=url,
            )
        raise DisallowedHostError(url, reason="sitemap not configured in fake")


def _build_app(
    *,
    company_gateway: CompanyDiscoveryGateway,
    discovery_repository: DiscoveryRepository,
    http_client: HttpDiscoveryClient,
) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_company_discovery_gateway] = lambda: company_gateway
    app.dependency_overrides[get_discovery_repository] = lambda: discovery_repository
    app.dependency_overrides[get_http_discovery_client] = lambda: http_client
    return app


@pytest.fixture
def company_gateway() -> FakeCompanyDiscoveryGateway:
    return FakeCompanyDiscoveryGateway()


@pytest.fixture
def discovery_repository() -> FakeDiscoveryRepository:
    return FakeDiscoveryRepository()


@pytest.fixture
def http_client() -> FakeHttpDiscoveryClient:
    return FakeHttpDiscoveryClient()


ClientFactory = Callable[
    [CompanyDiscoveryGateway, DiscoveryRepository, HttpDiscoveryClient],
    AbstractAsyncContextManager[AsyncClient],
]


@pytest.fixture
def client_factory() -> ClientFactory:
    @asynccontextmanager
    async def _factory(
        company_gateway: CompanyDiscoveryGateway,
        discovery_repository: DiscoveryRepository,
        http_client: HttpDiscoveryClient,
    ) -> AsyncGenerator[AsyncClient, None]:
        app = _build_app(
            company_gateway=company_gateway,
            discovery_repository=discovery_repository,
            http_client=http_client,
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
            yield test_client

    return _factory


@pytest.fixture
async def client(
    company_gateway: FakeCompanyDiscoveryGateway,
    discovery_repository: FakeDiscoveryRepository,
    http_client: FakeHttpDiscoveryClient,
    client_factory: ClientFactory,
) -> AsyncGenerator[AsyncClient, None]:
    async with client_factory(company_gateway, discovery_repository, http_client) as test_client:
        yield test_client
