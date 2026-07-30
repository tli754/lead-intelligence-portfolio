"""Shared fixtures for the crawling-module integration tests.

No real MongoDB and no real network — matching
`backend/tests/integration/discovery/conftest.py`'s exact style. A
locally-scoped `FastAPI()` app contains only this module's router, never
the shared `app.main.app` (the crawling router is deliberately not
registered there — see the contract's Dependencies section).

The real-MongoDB test (`test_mongo_crawl_repository.py`) does not use any
fixture defined here — it uses the inherited root `test_database`/
`motor_client` fixtures plus its own module-local autouse cleanup
fixture, kept deliberately out of this file so the fakes-based tests in
this same directory stay free of any real-MongoDB dependency.
"""

from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.modules.companies.domain.enums import ProcessingStatus
from app.modules.crawling.api.router import (
    get_company_crawl_gateway,
    get_content_storage,
    get_crawl_queue,
    get_crawl_repository,
    get_discovery_crawl_gateway,
    get_page_fetcher,
    get_robots_policy_gateway,
    router,
)
from app.modules.crawling.application.website_crawl_service import WebsiteCrawlService
from app.modules.crawling.domain.content_storage import ContentStorage, NonRawContentKind
from app.modules.crawling.domain.exceptions import (
    CompanyNotFoundForCrawlError,
    DiscoveryRunNotFoundForCrawlError,
)
from app.modules.crawling.domain.gateway import (
    CompanyCrawlGateway,
    DiscoveryCrawlGateway,
    RobotsPolicyGateway,
)
from app.modules.crawling.domain.models import (
    ContentReference,
    CrawledPage,
    CrawlRun,
    CrawlTarget,
)
from app.modules.crawling.domain.page_fetcher import (
    BrowserPageFetcher,
    PageFetcher,
    PageFetchRequest,
    PageFetchResult,
    RenderedPageResult,
)
from app.modules.crawling.domain.repository import (
    CrawledPagePage,
    CrawlRepository,
    CrawlRunPage,
    CrawlTargetPage,
)
from app.modules.crawling.domain.robots_policy import Outcome as RobotsOutcome
from app.modules.crawling.domain.robots_policy import RobotsPolicyEvaluation
from app.modules.crawling.domain.robots_policy import Source as RobotsSource
from app.modules.discovery.domain.enums import DiscoveryPriority, DiscoverySource, PageType
from app.modules.discovery.domain.models import DiscoveredUrl, DiscoveryRun

# --- Test-data builders -----------------------------------------------------------


def make_discovered_url(
    *,
    discovery_run_id: str,
    company_id: str = "company-1",
    url: str,
    normalized_url: str | None = None,
    page_type: PageType = PageType.UNKNOWN,
    priority: DiscoveryPriority = DiscoveryPriority.PRIORITY_2,
    depth: int = 1,
    discovery_sources: list[DiscoverySource] | None = None,
) -> DiscoveredUrl:
    now = datetime.now(UTC)
    return DiscoveredUrl(
        discovery_run_id=discovery_run_id,
        company_id=company_id,
        url=url,
        normalized_url=normalized_url or url,
        page_type=page_type,
        page_type_confidence=90,
        priority=priority,
        discovery_sources=discovery_sources or [DiscoverySource.BODY_LINK],
        depth=depth,
        is_same_domain=True,
        first_discovered_at=now,
        last_discovered_at=now,
    )


def make_discovery_run(*, discovery_run_id: str, company_id: str = "company-1") -> DiscoveryRun:
    now = datetime.now(UTC)
    return DiscoveryRun(
        discovery_run_id=discovery_run_id,
        company_id=company_id,
        root_domain="example.com",
        homepage_url="https://example.com/",
        created_at=now,
        updated_at=now,
    )


# --- Fakes -------------------------------------------------------------------------


class FakeCompanyCrawlGateway(CompanyCrawlGateway):
    def __init__(self, *, known_company_ids: set[str] | None = None) -> None:
        self._known = set(known_company_ids or {"company-1"})
        self.status_updates: list[tuple[str, ProcessingStatus]] = []
        self.latest_run_updates: list[tuple[str, str]] = []

    async def update_processing_status(self, company_id: str, status: ProcessingStatus) -> None:
        if company_id not in self._known:
            raise CompanyNotFoundForCrawlError(company_id)
        self.status_updates.append((company_id, status))

    async def update_latest_crawl_run(self, company_id: str, crawl_run_id: str) -> None:
        self.latest_run_updates.append((company_id, crawl_run_id))


class FakeDiscoveryCrawlGateway(DiscoveryCrawlGateway):
    def __init__(
        self,
        *,
        discovery_run: DiscoveryRun | None = None,
        discovered_urls: list[DiscoveredUrl] | None = None,
    ) -> None:
        self._run = discovery_run
        self._urls = discovered_urls or []

    async def get_discovery_run(self, discovery_run_id: str) -> DiscoveryRun:
        if self._run is None or self._run.discovery_run_id != discovery_run_id:
            raise DiscoveryRunNotFoundForCrawlError(discovery_run_id)
        return self._run

    async def list_discovered_urls(
        self,
        discovery_run_id: str,
        *,
        priorities: list[DiscoveryPriority] | None = None,
        page_types: list[PageType] | None = None,
        include_excluded: bool = False,
    ) -> list[DiscoveredUrl]:
        results = [url for url in self._urls if url.discovery_run_id == discovery_run_id]
        if not include_excluded:
            results = [url for url in results if url.priority != DiscoveryPriority.EXCLUDED]
        if priorities is not None:
            results = [url for url in results if url.priority in priorities]
        if page_types is not None:
            results = [url for url in results if url.page_type in page_types]
        return results


class FakeRobotsPolicyGateway(RobotsPolicyGateway):
    def __init__(
        self,
        *,
        default_outcome: RobotsOutcome = "allowed",
        disallowed_path_markers: set[str] | None = None,
        crawl_delay: float | None = None,
    ) -> None:
        self._default_outcome: RobotsOutcome = default_outcome
        self._disallowed_path_markers = disallowed_path_markers or set()
        self._crawl_delay = crawl_delay
        self.requested_urls: list[str] = []

    async def get_policy(
        self, company_id: str, url: str, user_agent: str
    ) -> RobotsPolicyEvaluation:
        self.requested_urls.append(url)
        outcome: RobotsOutcome
        if any(marker in url for marker in self._disallowed_path_markers):
            outcome = "disallowed"
        else:
            outcome = self._default_outcome
        source: RobotsSource = "unknown_default" if outcome == "unknown" else "robots_txt"
        return RobotsPolicyEvaluation(
            outcome=outcome, crawl_delay=self._crawl_delay, matched_rule=None, source=source
        )


class FakePageFetcher(PageFetcher):
    """Configurable canned-response fake — no real network access.

    `responses` maps a URL to either a `PageFetchResult` or an
    `Exception` instance to raise. `call_log` records every request in
    order, for assertions about fetch order/pacing.
    """

    def __init__(self, responses: dict[str, PageFetchResult | Exception] | None = None) -> None:
        self._responses = responses or {}
        self.call_log: list[PageFetchRequest] = []

    def set_response(self, url: str, response: PageFetchResult | Exception) -> None:
        self._responses[url] = response

    async def fetch_page(self, request: PageFetchRequest) -> PageFetchResult:
        self.call_log.append(request)
        response = self._responses.get(request.url)
        if response is None:
            raise AssertionError(f"FakePageFetcher has no configured response for {request.url!r}")
        if isinstance(response, Exception):
            raise response
        return response


class FakeBrowserPageFetcher(BrowserPageFetcher):
    def __init__(
        self,
        *,
        succeed: bool = True,
        html: str = "<html><body>rendered</body></html>",
        error: str | None = None,
        raise_exception: bool = False,
    ) -> None:
        self._succeed = succeed
        self._html = html
        self._error = error
        self._raise_exception = raise_exception
        self.calls: list[str] = []

    async def fetch_rendered_page(self, request: PageFetchRequest) -> RenderedPageResult:
        self.calls.append(request.url)
        if self._raise_exception:
            raise RuntimeError("simulated browser crash")
        return RenderedPageResult(
            html=self._html if self._succeed else None,
            final_url=request.url,
            duration_ms=10,
            succeeded=self._succeed,
            error=self._error,
        )


class RaisingBrowserPageFetcher(BrowserPageFetcher):
    """A fetcher that always raises — used to prove `detect_only` never calls it."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def fetch_rendered_page(self, request: PageFetchRequest) -> RenderedPageResult:
        self.calls.append(request.url)
        raise AssertionError("BrowserPageFetcher must never be called under detect_only")


def _make_page_key(crawl_run_id: str, normalized_url: str) -> tuple[str, str]:
    return (crawl_run_id, normalized_url)


class FakeCrawlRepository(CrawlRepository):
    """A full in-memory `CrawlRepository`, including optimistic-
    concurrency and upsert-by-`(crawl_run_id, normalized_url)` semantics —
    mirroring `MongoCrawlRepository`'s real behavior closely enough for
    service-level tests."""

    def __init__(self) -> None:
        self.runs: dict[str, CrawlRun] = {}
        self.targets: dict[str, CrawlTarget] = {}
        self.pages: dict[str, CrawledPage] = {}

    # --- Runs ---
    async def create_run(self, run: CrawlRun) -> CrawlRun:
        self.runs[run.crawl_run_id] = run
        return run

    async def update_run(self, run: CrawlRun) -> CrawlRun | None:
        existing = self.runs.get(run.crawl_run_id)
        if existing is None or existing.document_version != run.document_version:
            return None
        updated = run.model_copy(update={"document_version": run.document_version + 1})
        self.runs[run.crawl_run_id] = updated
        return updated

    async def get_run(self, crawl_run_id: str) -> CrawlRun | None:
        return self.runs.get(crawl_run_id)

    async def list_runs_by_company(
        self, company_id: str, *, page: int = 1, page_size: int = 20
    ) -> CrawlRunPage:
        items = sorted(
            (run for run in self.runs.values() if run.company_id == company_id),
            key=lambda run: run.created_at,
            reverse=True,
        )
        start = (page - 1) * page_size
        return CrawlRunPage(items=items[start : start + page_size], total=len(items))

    async def list_runs(
        self,
        *,
        status=None,
        page: int = 1,
        page_size: int = 20,
    ) -> CrawlRunPage:
        items = sorted(self.runs.values(), key=lambda run: run.created_at, reverse=True)
        if status is not None:
            items = [run for run in items if run.status == status]
        total = len(items)
        start = (page - 1) * page_size
        return CrawlRunPage(items=items[start : start + page_size], total=total)

    async def find_active_run(self, company_id: str, idempotency_key: str) -> CrawlRun | None:
        for run in self.runs.values():
            if (
                run.company_id == company_id
                and run.idempotency_key == idempotency_key
                and run.status.value in ("queued", "running")
            ):
                return run
        return None

    async def mark_run_cancelled(self, crawl_run_id: str) -> CrawlRun | None:
        run = self.runs.get(crawl_run_id)
        if run is None:
            return None
        from app.modules.crawling.domain.enums import CrawlStatus

        updated = run.model_copy(
            update={"status": CrawlStatus.CANCELLED, "document_version": run.document_version + 1}
        )
        self.runs[crawl_run_id] = updated
        return updated

    # --- Targets ---
    async def save_target(self, target: CrawlTarget) -> CrawlTarget:
        key = _make_page_key(target.crawl_run_id, target.normalized_url)
        for existing_id, existing in list(self.targets.items()):
            if _make_page_key(existing.crawl_run_id, existing.normalized_url) == key:
                del self.targets[existing_id]
        self.targets[target.crawl_target_id] = target
        return target

    async def update_target(self, target: CrawlTarget) -> CrawlTarget | None:
        existing = self.targets.get(target.crawl_target_id)
        if existing is None or existing.document_version != target.document_version:
            return None
        updated = target.model_copy(update={"document_version": target.document_version + 1})
        self.targets[target.crawl_target_id] = updated
        return updated

    async def find_target_by_url(
        self, crawl_run_id: str, normalized_url: str
    ) -> CrawlTarget | None:
        for target in self.targets.values():
            if target.crawl_run_id == crawl_run_id and target.normalized_url == normalized_url:
                return target
        return None

    async def list_targets_by_run(
        self,
        crawl_run_id: str,
        *,
        status=None,
        page_type=None,
        priority=None,
        fetch_mode=None,
        page: int = 1,
        page_size: int = 20,
    ) -> CrawlTargetPage:
        items = [t for t in self.targets.values() if t.crawl_run_id == crawl_run_id]
        if status is not None:
            items = [t for t in items if t.status == status]
        if page_type is not None:
            items = [t for t in items if t.page_type == page_type]
        if priority is not None:
            items = [t for t in items if t.priority == priority]
        if fetch_mode is not None:
            items = [t for t in items if t.fetch_mode == fetch_mode]
        start = (page - 1) * page_size
        return CrawlTargetPage(items=items[start : start + page_size], total=len(items))

    # --- Pages ---
    async def save_page(self, page: CrawledPage) -> CrawledPage:
        key = _make_page_key(page.crawl_run_id, page.normalized_url)
        for existing_id, existing in list(self.pages.items()):
            if _make_page_key(existing.crawl_run_id, existing.normalized_url) == key:
                del self.pages[existing_id]
        self.pages[page.page_id] = page
        return page

    async def get_page(self, page_id: str) -> CrawledPage | None:
        return self.pages.get(page_id)

    async def list_pages_by_run(
        self,
        crawl_run_id: str,
        *,
        status=None,
        page_type=None,
        priority=None,
        fetch_mode=None,
        browser_required=None,
        include_failed: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> CrawledPagePage:
        from app.modules.crawling.domain.enums import PageFetchStatus

        items = [p for p in self.pages.values() if p.crawl_run_id == crawl_run_id]
        if status is not None:
            items = [p for p in items if p.fetch_status == status]
        elif not include_failed:
            items = [p for p in items if p.fetch_status != PageFetchStatus.FAILED]
        if page_type is not None:
            items = [p for p in items if p.page_type == page_type]
        if priority is not None:
            items = [p for p in items if p.priority == priority]
        if fetch_mode is not None:
            items = [p for p in items if p.fetch_mode == fetch_mode]
        if browser_required is True:
            items = [p for p in items if p.browser_fallback_reason is not None]
        elif browser_required is False:
            items = [p for p in items if p.browser_fallback_reason is None]
        start = (page - 1) * page_size
        return CrawledPagePage(items=items[start : start + page_size], total=len(items))

    async def get_latest_page_by_normalized_url(
        self, company_id: str, normalized_url: str
    ) -> CrawledPage | None:
        candidates = [
            p
            for p in self.pages.values()
            if p.company_id == company_id and p.normalized_url == normalized_url
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.fetched_at or datetime.min.replace(tzinfo=UTC))


class FakeContentStorage(ContentStorage):
    def __init__(self, *, fail_kinds: set[str] | None = None) -> None:
        self._store: dict[str, bytes] = {}
        self._fail_kinds = fail_kinds or set()

    async def store_raw_content(
        self, *, company_id, crawl_run_id, page_id, content: bytes, expected_sha256: str
    ) -> ContentReference:
        if "raw" in self._fail_kinds:
            raise RuntimeError("simulated raw storage failure")
        reference_id = str(uuid4())
        self._store[reference_id] = content
        return ContentReference(
            reference_id=reference_id,
            company_id=company_id,
            crawl_run_id=crawl_run_id,
            page_id=page_id,
            kind="raw",
        )

    async def store_cleaned_content(
        self,
        *,
        company_id,
        crawl_run_id,
        page_id,
        content: str,
        kind: NonRawContentKind,
        expected_sha256: str,
    ) -> ContentReference:
        if kind in self._fail_kinds:
            raise RuntimeError(f"simulated {kind} storage failure")
        reference_id = str(uuid4())
        self._store[reference_id] = content.encode("utf-8")
        return ContentReference(
            reference_id=reference_id,
            company_id=company_id,
            crawl_run_id=crawl_run_id,
            page_id=page_id,
            kind=kind,
        )

    async def load_content(self, reference: ContentReference) -> bytes:
        return self._store[reference.reference_id]

    async def delete_content(self, reference: ContentReference) -> None:
        self._store.pop(reference.reference_id, None)


# --- Pytest fixtures ----------------------------------------------------------------


@pytest.fixture
def company_gateway() -> FakeCompanyCrawlGateway:
    return FakeCompanyCrawlGateway()


@pytest.fixture
def discovery_gateway() -> FakeDiscoveryCrawlGateway:
    return FakeDiscoveryCrawlGateway(
        discovery_run=make_discovery_run(discovery_run_id="discovery-1")
    )


@pytest.fixture
def robots_gateway() -> FakeRobotsPolicyGateway:
    return FakeRobotsPolicyGateway()


@pytest.fixture
def crawl_repository() -> FakeCrawlRepository:
    return FakeCrawlRepository()


@pytest.fixture
def page_fetcher() -> FakePageFetcher:
    return FakePageFetcher()


@pytest.fixture
def content_storage() -> FakeContentStorage:
    return FakeContentStorage()


@pytest.fixture
def crawl_service(
    company_gateway: FakeCompanyCrawlGateway,
    discovery_gateway: FakeDiscoveryCrawlGateway,
    robots_gateway: FakeRobotsPolicyGateway,
    crawl_repository: FakeCrawlRepository,
    page_fetcher: FakePageFetcher,
    content_storage: FakeContentStorage,
) -> WebsiteCrawlService:
    """A `WebsiteCrawlService` built from the exact same fakes the `client`
    fixture's app is wired to (via `app.dependency_overrides`). Since
    Task 017, the HTTP router only calls `enqueue_crawl_run`/
    `enqueue_retry` — tests that need a *completed* run (e.g. to assert
    on response serialization) call `execute_crawl_run`/`retry_failed`
    on this fixture directly afterward, exactly mirroring what a real
    RQ worker does via `infrastructure/rq_jobs.py`'s job wrappers."""
    return WebsiteCrawlService(
        company_gateway=company_gateway,
        discovery_gateway=discovery_gateway,
        robots_gateway=robots_gateway,
        repository=crawl_repository,
        page_fetcher=page_fetcher,
        content_storage=content_storage,
    )


class NoOpQueue:
    """A `get_crawl_queue` override for tests in this directory that don't
    care about *what* gets enqueued (only about HTTP response shape or
    service-level behavior) — records calls without ever touching a real
    Redis connection. `test_router_rq_enqueue.py` uses its own
    locally-defined `FakeQueue` instead, where the enqueue call's exact
    arguments are the thing under test."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def enqueue_call(self, **kwargs) -> None:
        self.calls.append(kwargs)


def _build_app(
    *,
    company_gateway: CompanyCrawlGateway,
    discovery_gateway: DiscoveryCrawlGateway,
    robots_gateway: RobotsPolicyGateway,
    crawl_repository: CrawlRepository,
    page_fetcher: PageFetcher,
    content_storage: ContentStorage,
    queue: object | None = None,
) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_company_crawl_gateway] = lambda: company_gateway
    app.dependency_overrides[get_discovery_crawl_gateway] = lambda: discovery_gateway
    app.dependency_overrides[get_robots_policy_gateway] = lambda: robots_gateway
    app.dependency_overrides[get_crawl_repository] = lambda: crawl_repository
    app.dependency_overrides[get_page_fetcher] = lambda: page_fetcher
    app.dependency_overrides[get_content_storage] = lambda: content_storage
    app.dependency_overrides[get_crawl_queue] = lambda: queue if queue is not None else NoOpQueue()
    return app


ClientFactory = Callable[..., AbstractAsyncContextManager[AsyncClient]]


@pytest.fixture
def client_factory() -> ClientFactory:
    @asynccontextmanager
    async def _factory(
        *,
        company_gateway: CompanyCrawlGateway,
        discovery_gateway: DiscoveryCrawlGateway,
        robots_gateway: RobotsPolicyGateway,
        crawl_repository: CrawlRepository,
        page_fetcher: PageFetcher,
        content_storage: ContentStorage,
        queue: object | None = None,
    ) -> AsyncGenerator[AsyncClient, None]:
        app = _build_app(
            company_gateway=company_gateway,
            discovery_gateway=discovery_gateway,
            robots_gateway=robots_gateway,
            crawl_repository=crawl_repository,
            page_fetcher=page_fetcher,
            content_storage=content_storage,
            queue=queue,
        )
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
            yield test_client

    return _factory


@pytest.fixture
async def client(
    company_gateway: FakeCompanyCrawlGateway,
    discovery_gateway: FakeDiscoveryCrawlGateway,
    robots_gateway: FakeRobotsPolicyGateway,
    crawl_repository: FakeCrawlRepository,
    page_fetcher: FakePageFetcher,
    content_storage: FakeContentStorage,
    client_factory: ClientFactory,
) -> AsyncGenerator[AsyncClient, None]:
    async with client_factory(
        company_gateway=company_gateway,
        discovery_gateway=discovery_gateway,
        robots_gateway=robots_gateway,
        crawl_repository=crawl_repository,
        page_fetcher=page_fetcher,
        content_storage=content_storage,
    ) as test_client:
        yield test_client
