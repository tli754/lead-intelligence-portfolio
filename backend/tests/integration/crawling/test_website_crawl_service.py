"""Integration tests for `WebsiteCrawlService`, using the fakes in
`conftest.py` — no real MongoDB, no real network."""

from pathlib import Path

from app.modules.companies.domain.enums import ProcessingStatus
from app.modules.crawling.application.website_crawl_service import WebsiteCrawlService
from app.modules.crawling.domain.config import CrawlConfig
from app.modules.crawling.domain.enums import BrowserPolicy, CrawlStatus, PageFetchStatus
from app.modules.crawling.domain.exceptions import DuplicateActiveCrawlRunError
from app.modules.crawling.domain.models import CrawledPage, CrawlRunOptions, HttpMetadata
from app.modules.crawling.domain.page_fetcher import FetchOutcome, PageFetchResult
from app.modules.discovery.domain.enums import DiscoveryPriority, DiscoverySource, PageType

from .conftest import (
    FakeBrowserPageFetcher,
    FakeCompanyCrawlGateway,
    FakeContentStorage,
    FakeCrawlRepository,
    FakeDiscoveryCrawlGateway,
    FakePageFetcher,
    FakeRobotsPolicyGateway,
    RaisingBrowserPageFetcher,
    make_discovered_url,
)

FIXTURES_DIR = Path(__file__).resolve().parents[3].parent / "fixtures" / "crawling"


def _read_text(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


HOMEPAGE_URL = "https://example.com/"
ABOUT_URL = "https://example.com/about-us"


def _http_result(
    body: bytes = b"<html><body><h1>Hello</h1><p>Welcome to our shop.</p></body></html>",
    *,
    status_code: int = 200,
    etag: str | None = None,
    last_modified: str | None = None,
    content_type: str = "text/html",
    final_url: str | None = None,
    outcome: FetchOutcome = "fetched",
) -> PageFetchResult:
    return PageFetchResult(
        status_code=status_code,
        http_metadata=HttpMetadata(
            status_code=status_code,
            content_type=content_type,
            etag=etag,
            last_modified=last_modified,
        ),
        body=body if outcome == "fetched" else None,
        final_url=final_url or HOMEPAGE_URL,
        outcome=outcome,
    )


def _service(
    *,
    company_gateway: FakeCompanyCrawlGateway,
    discovery_gateway: FakeDiscoveryCrawlGateway,
    robots_gateway: FakeRobotsPolicyGateway,
    crawl_repository: FakeCrawlRepository,
    page_fetcher: FakePageFetcher,
    content_storage: FakeContentStorage,
    browser_fetcher=None,
    config: CrawlConfig | None = None,
) -> WebsiteCrawlService:
    return WebsiteCrawlService(
        company_gateway=company_gateway,
        discovery_gateway=discovery_gateway,
        robots_gateway=robots_gateway,
        repository=crawl_repository,
        page_fetcher=page_fetcher,
        content_storage=content_storage,
        browser_fetcher=browser_fetcher,
        config=config or CrawlConfig(default_delay_s=0.0, min_delay_s=0.0),
    )


def _single_homepage_discovery(discovery_gateway: FakeDiscoveryCrawlGateway) -> None:
    discovery_gateway._urls.append(
        make_discovered_url(
            discovery_run_id="discovery-1",
            url=HOMEPAGE_URL,
            page_type=PageType.HOMEPAGE,
            priority=DiscoveryPriority.PRIORITY_1,
            depth=0,
            discovery_sources=[DiscoverySource.HOMEPAGE],
        )
    )


class TestSuccessfulRun:
    async def test_run_completes_and_persists_a_page(
        self,
        company_gateway: FakeCompanyCrawlGateway,
        discovery_gateway: FakeDiscoveryCrawlGateway,
        robots_gateway: FakeRobotsPolicyGateway,
        crawl_repository: FakeCrawlRepository,
        page_fetcher: FakePageFetcher,
        content_storage: FakeContentStorage,
    ) -> None:
        _single_homepage_discovery(discovery_gateway)
        page_fetcher.set_response(HOMEPAGE_URL, _http_result())
        service = _service(
            company_gateway=company_gateway,
            discovery_gateway=discovery_gateway,
            robots_gateway=robots_gateway,
            crawl_repository=crawl_repository,
            page_fetcher=page_fetcher,
            content_storage=content_storage,
        )

        run = await service.start_crawl_run("company-1", "discovery-1")

        assert run.status in (CrawlStatus.COMPLETED, CrawlStatus.COMPLETED_WITH_WARNINGS)
        assert run.summary.pages_fetched == 1
        assert len(crawl_repository.pages) == 1


class TestRobotsBlockedPageNeverFetched:
    async def test_robots_blocked_page_never_fetched(
        self,
        company_gateway: FakeCompanyCrawlGateway,
        discovery_gateway: FakeDiscoveryCrawlGateway,
        crawl_repository: FakeCrawlRepository,
        page_fetcher: FakePageFetcher,
        content_storage: FakeContentStorage,
    ) -> None:
        _single_homepage_discovery(discovery_gateway)
        robots_gateway = FakeRobotsPolicyGateway(disallowed_path_markers={"example.com"})
        service = _service(
            company_gateway=company_gateway,
            discovery_gateway=discovery_gateway,
            robots_gateway=robots_gateway,
            crawl_repository=crawl_repository,
            page_fetcher=page_fetcher,
            content_storage=content_storage,
        )

        run = await service.start_crawl_run("company-1", "discovery-1")

        assert page_fetcher.call_log == []
        assert run.summary.pages_blocked_by_robots == 1
        target = next(iter(crawl_repository.targets.values()))
        assert target.status == PageFetchStatus.BLOCKED_BY_ROBOTS


class TestMissingRobotsProceedsWithWarning:
    async def test_missing_robots_proceeds_with_warning(
        self,
        company_gateway: FakeCompanyCrawlGateway,
        discovery_gateway: FakeDiscoveryCrawlGateway,
        crawl_repository: FakeCrawlRepository,
        page_fetcher: FakePageFetcher,
        content_storage: FakeContentStorage,
    ) -> None:
        _single_homepage_discovery(discovery_gateway)
        robots_gateway = FakeRobotsPolicyGateway(default_outcome="unknown")
        page_fetcher.set_response(HOMEPAGE_URL, _http_result())
        service = _service(
            company_gateway=company_gateway,
            discovery_gateway=discovery_gateway,
            robots_gateway=robots_gateway,
            crawl_repository=crawl_repository,
            page_fetcher=page_fetcher,
            content_storage=content_storage,
        )

        run = await service.start_crawl_run("company-1", "discovery-1")

        assert len(page_fetcher.call_log) == 1
        assert run.summary.warnings >= 1
        assert any(w.code == "robots_policy_unknown" for w in run.warnings)


class TestConditionalUnchanged:
    async def test_conditional_etag_returns_unchanged(
        self,
        company_gateway: FakeCompanyCrawlGateway,
        discovery_gateway: FakeDiscoveryCrawlGateway,
        robots_gateway: FakeRobotsPolicyGateway,
        crawl_repository: FakeCrawlRepository,
        page_fetcher: FakePageFetcher,
        content_storage: FakeContentStorage,
    ) -> None:
        _single_homepage_discovery(discovery_gateway)
        page_fetcher.set_response(HOMEPAGE_URL, _http_result(etag='"v1"'))
        service = _service(
            company_gateway=company_gateway,
            discovery_gateway=discovery_gateway,
            robots_gateway=robots_gateway,
            crawl_repository=crawl_repository,
            page_fetcher=page_fetcher,
            content_storage=content_storage,
        )
        first_run = await service.start_crawl_run("company-1", "discovery-1")
        assert first_run.summary.pages_fetched == 1

        page_fetcher.set_response(HOMEPAGE_URL, _http_result(outcome="not_modified"))
        second_run = await service.start_crawl_run("company-1", "discovery-1")

        assert second_run.summary.pages_unchanged == 1
        pages = [
            p for p in crawl_repository.pages.values() if p.crawl_run_id == second_run.crawl_run_id
        ]
        assert pages[0].fetch_status == PageFetchStatus.UNCHANGED
        assert pages[0].unchanged_from_page_id is not None

    async def test_conditional_last_modified(
        self,
        company_gateway: FakeCompanyCrawlGateway,
        discovery_gateway: FakeDiscoveryCrawlGateway,
        robots_gateway: FakeRobotsPolicyGateway,
        crawl_repository: FakeCrawlRepository,
        page_fetcher: FakePageFetcher,
        content_storage: FakeContentStorage,
    ) -> None:
        _single_homepage_discovery(discovery_gateway)
        page_fetcher.set_response(
            HOMEPAGE_URL, _http_result(last_modified="Wed, 21 Oct 2015 07:28:00 GMT")
        )
        service = _service(
            company_gateway=company_gateway,
            discovery_gateway=discovery_gateway,
            robots_gateway=robots_gateway,
            crawl_repository=crawl_repository,
            page_fetcher=page_fetcher,
            content_storage=content_storage,
        )
        await service.start_crawl_run("company-1", "discovery-1")

        page_fetcher.set_response(HOMEPAGE_URL, _http_result(outcome="not_modified"))
        second_run = await service.start_crawl_run("company-1", "discovery-1")

        assert second_run.summary.pages_unchanged == 1

    async def test_conditional_unchanged_via_structural_hash(
        self,
        company_gateway: FakeCompanyCrawlGateway,
        discovery_gateway: FakeDiscoveryCrawlGateway,
        robots_gateway: FakeRobotsPolicyGateway,
        crawl_repository: FakeCrawlRepository,
        page_fetcher: FakePageFetcher,
        content_storage: FakeContentStorage,
    ) -> None:
        _single_homepage_discovery(discovery_gateway)
        page_fetcher.set_response(
            HOMEPAGE_URL,
            _http_result(
                body=b'<html><body><h1>Hello</h1><meta name="ts" content="111"></body></html>'
            ),
        )
        service = _service(
            company_gateway=company_gateway,
            discovery_gateway=discovery_gateway,
            robots_gateway=robots_gateway,
            crawl_repository=crawl_repository,
            page_fetcher=page_fetcher,
            content_storage=content_storage,
        )
        await service.start_crawl_run("company-1", "discovery-1")

        # A server that ignores conditional headers and always returns 200,
        # but only a dynamic marker changed.
        page_fetcher.set_response(
            HOMEPAGE_URL,
            _http_result(
                body=b'<html><body><h1>Hello</h1><meta name="ts" content="999"></body></html>'
            ),
        )
        second_run = await service.start_crawl_run("company-1", "discovery-1")

        assert second_run.summary.pages_unchanged == 1


class TestBrowserFallback:
    async def test_detect_only_never_fetches(
        self,
        company_gateway: FakeCompanyCrawlGateway,
        discovery_gateway: FakeDiscoveryCrawlGateway,
        robots_gateway: FakeRobotsPolicyGateway,
        crawl_repository: FakeCrawlRepository,
        page_fetcher: FakePageFetcher,
        content_storage: FakeContentStorage,
    ) -> None:
        _single_homepage_discovery(discovery_gateway)
        page_fetcher.set_response(
            HOMEPAGE_URL,
            _http_result(body=b'<html><body><div id="root"></div></body></html>'),
        )
        raising_browser_fetcher = RaisingBrowserPageFetcher()
        service = _service(
            company_gateway=company_gateway,
            discovery_gateway=discovery_gateway,
            robots_gateway=robots_gateway,
            crawl_repository=crawl_repository,
            page_fetcher=page_fetcher,
            content_storage=content_storage,
            browser_fetcher=raising_browser_fetcher,
            config=CrawlConfig(
                default_delay_s=0.0, min_delay_s=0.0, browser_policy=BrowserPolicy.DETECT_ONLY
            ),
        )

        run = await service.start_crawl_run("company-1", "discovery-1")

        target = next(iter(crawl_repository.targets.values()))
        assert target.status == PageFetchStatus.BROWSER_REQUIRED
        assert run.summary.pages_requiring_browser == 1
        assert run.summary.pages_browser_fetched == 0
        assert raising_browser_fetcher.calls == []

    async def test_fetch_when_required_invokes_browser_fetcher(
        self,
        company_gateway: FakeCompanyCrawlGateway,
        discovery_gateway: FakeDiscoveryCrawlGateway,
        robots_gateway: FakeRobotsPolicyGateway,
        crawl_repository: FakeCrawlRepository,
        page_fetcher: FakePageFetcher,
        content_storage: FakeContentStorage,
    ) -> None:
        _single_homepage_discovery(discovery_gateway)
        page_fetcher.set_response(
            HOMEPAGE_URL,
            _http_result(body=b'<html><body><div id="root"></div></body></html>'),
        )
        browser_fetcher = FakeBrowserPageFetcher(html="<html><body><h1>Rendered</h1></body></html>")
        service = _service(
            company_gateway=company_gateway,
            discovery_gateway=discovery_gateway,
            robots_gateway=robots_gateway,
            crawl_repository=crawl_repository,
            page_fetcher=page_fetcher,
            content_storage=content_storage,
            browser_fetcher=browser_fetcher,
            config=CrawlConfig(
                default_delay_s=0.0,
                min_delay_s=0.0,
                browser_policy=BrowserPolicy.FETCH_WHEN_REQUIRED,
            ),
        )

        run = await service.start_crawl_run("company-1", "discovery-1")

        assert browser_fetcher.calls == [HOMEPAGE_URL]
        assert run.summary.pages_browser_fetched == 1
        page = next(iter(crawl_repository.pages.values()))
        assert page.fetch_status == PageFetchStatus.BROWSER_FETCHED
        assert "Rendered" in (page.extracted_text or "")

    async def test_always_for_selected_page_types_forces_browser_regardless_of_detection(
        self,
        company_gateway: FakeCompanyCrawlGateway,
        discovery_gateway: FakeDiscoveryCrawlGateway,
        robots_gateway: FakeRobotsPolicyGateway,
        crawl_repository: FakeCrawlRepository,
        page_fetcher: FakePageFetcher,
        content_storage: FakeContentStorage,
    ) -> None:
        _single_homepage_discovery(discovery_gateway)
        # An entirely normal, server-rendered page — `detect_browser_fallback`
        # alone would never flag this as `browser_required`.
        page_fetcher.set_response(HOMEPAGE_URL, _http_result())
        browser_fetcher = FakeBrowserPageFetcher(html="<html><body><h1>Rendered</h1></body></html>")
        service = _service(
            company_gateway=company_gateway,
            discovery_gateway=discovery_gateway,
            robots_gateway=robots_gateway,
            crawl_repository=crawl_repository,
            page_fetcher=page_fetcher,
            content_storage=content_storage,
            browser_fetcher=browser_fetcher,
            config=CrawlConfig(
                default_delay_s=0.0,
                min_delay_s=0.0,
                browser_policy=BrowserPolicy.ALWAYS_FOR_SELECTED_PAGE_TYPES,
                always_browser_page_types=frozenset({PageType.HOMEPAGE}),
            ),
        )

        run = await service.start_crawl_run("company-1", "discovery-1")

        assert browser_fetcher.calls == [HOMEPAGE_URL]
        assert run.summary.pages_requiring_browser == 1
        assert run.summary.pages_browser_fetched == 1
        page = next(iter(crawl_repository.pages.values()))
        assert page.fetch_status == PageFetchStatus.BROWSER_FETCHED

    async def test_browser_fetch_failure_preserves_http_result(
        self,
        company_gateway: FakeCompanyCrawlGateway,
        discovery_gateway: FakeDiscoveryCrawlGateway,
        robots_gateway: FakeRobotsPolicyGateway,
        crawl_repository: FakeCrawlRepository,
        page_fetcher: FakePageFetcher,
        content_storage: FakeContentStorage,
    ) -> None:
        _single_homepage_discovery(discovery_gateway)
        # Triggers `browser:script-heavy` (>=3 script tags, short visible
        # text) regardless of the shell-specific `id="root"`/`id="app"`
        # rules, so the extra paragraph doesn't defeat detection.
        page_fetcher.set_response(
            HOMEPAGE_URL,
            _http_result(
                body=(
                    b"<html><body><script>1</script><script>2</script><script>3</script>"
                    b"<p>Fallback text here</p></body></html>"
                )
            ),
        )
        browser_fetcher = FakeBrowserPageFetcher(succeed=False, error="render timed out")
        service = _service(
            company_gateway=company_gateway,
            discovery_gateway=discovery_gateway,
            robots_gateway=robots_gateway,
            crawl_repository=crawl_repository,
            page_fetcher=page_fetcher,
            content_storage=content_storage,
            browser_fetcher=browser_fetcher,
            config=CrawlConfig(
                default_delay_s=0.0,
                min_delay_s=0.0,
                browser_policy=BrowserPolicy.FETCH_WHEN_REQUIRED,
            ),
        )

        run = await service.start_crawl_run("company-1", "discovery-1")

        page = next(iter(crawl_repository.pages.values()))
        assert "Fallback text here" in (page.extracted_text or "")
        assert run.status != CrawlStatus.FAILED
        assert any(w.code == "browser_fetch_failed" for w in run.warnings)


class TestFailureIsolation:
    async def test_one_page_failure_isolated(
        self,
        company_gateway: FakeCompanyCrawlGateway,
        discovery_gateway: FakeDiscoveryCrawlGateway,
        robots_gateway: FakeRobotsPolicyGateway,
        crawl_repository: FakeCrawlRepository,
        page_fetcher: FakePageFetcher,
        content_storage: FakeContentStorage,
    ) -> None:
        discovery_gateway._urls.extend(
            [
                make_discovered_url(
                    discovery_run_id="discovery-1",
                    url=HOMEPAGE_URL,
                    page_type=PageType.HOMEPAGE,
                    priority=DiscoveryPriority.PRIORITY_1,
                ),
                make_discovered_url(
                    discovery_run_id="discovery-1",
                    url="https://example.com/about-us",
                    page_type=PageType.ABOUT,
                    priority=DiscoveryPriority.PRIORITY_1,
                ),
                make_discovered_url(
                    discovery_run_id="discovery-1",
                    url="https://example.com/contact-us",
                    page_type=PageType.CONTACT,
                    priority=DiscoveryPriority.PRIORITY_1,
                ),
            ]
        )
        page_fetcher.set_response(HOMEPAGE_URL, _http_result())
        page_fetcher.set_response("https://example.com/about-us", RuntimeError("boom"))
        page_fetcher.set_response("https://example.com/contact-us", _http_result())

        # RuntimeError isn't a CrawlFetchError, so wrap it to exercise the
        # real failure path via a typed error instead.
        from app.modules.crawling.domain.exceptions import TimeoutFetchError

        page_fetcher.set_response(
            "https://example.com/about-us", TimeoutFetchError("https://example.com/about-us")
        )

        service = _service(
            company_gateway=company_gateway,
            discovery_gateway=discovery_gateway,
            robots_gateway=robots_gateway,
            crawl_repository=crawl_repository,
            page_fetcher=page_fetcher,
            content_storage=content_storage,
        )

        run = await service.start_crawl_run("company-1", "discovery-1")

        assert run.summary.pages_fetched == 2
        assert run.summary.pages_failed == 1
        assert run.status != CrawlStatus.FAILED

    async def test_homepage_failure_marks_partial(
        self,
        company_gateway: FakeCompanyCrawlGateway,
        discovery_gateway: FakeDiscoveryCrawlGateway,
        robots_gateway: FakeRobotsPolicyGateway,
        crawl_repository: FakeCrawlRepository,
        page_fetcher: FakePageFetcher,
        content_storage: FakeContentStorage,
    ) -> None:
        from app.modules.crawling.domain.exceptions import TimeoutFetchError

        _single_homepage_discovery(discovery_gateway)
        page_fetcher.set_response(HOMEPAGE_URL, TimeoutFetchError(HOMEPAGE_URL))
        service = _service(
            company_gateway=company_gateway,
            discovery_gateway=discovery_gateway,
            robots_gateway=robots_gateway,
            crawl_repository=crawl_repository,
            page_fetcher=page_fetcher,
            content_storage=content_storage,
        )

        run = await service.start_crawl_run("company-1", "discovery-1")

        assert run.status == CrawlStatus.PARTIAL
        assert run.status != CrawlStatus.FAILED


class TestCancellation:
    async def test_cancellation_preserves_completed_pages(
        self,
        company_gateway: FakeCompanyCrawlGateway,
        discovery_gateway: FakeDiscoveryCrawlGateway,
        robots_gateway: FakeRobotsPolicyGateway,
        crawl_repository: FakeCrawlRepository,
        content_storage: FakeContentStorage,
    ) -> None:
        urls = [HOMEPAGE_URL, "https://example.com/a", "https://example.com/b"]
        for index, url in enumerate(urls):
            discovery_gateway._urls.append(
                make_discovered_url(
                    discovery_run_id="discovery-1",
                    url=url,
                    page_type=PageType.HOMEPAGE if index == 0 else PageType.ABOUT,
                    priority=DiscoveryPriority.PRIORITY_1,
                )
            )

        class CancellingAfterTwoFetcher(FakePageFetcher):
            def __init__(self, repository: FakeCrawlRepository, run_holder: dict) -> None:
                super().__init__()
                self._repository = repository
                self._run_holder = run_holder
                self._count = 0

            async def fetch_page(self, request):
                self._count += 1
                result = _http_result(final_url=request.url)
                if self._count == 2:
                    # Cancel right after the 2nd fetch completes (but
                    # before returning) — the *next* target's
                    # before-target cancellation check must then skip it,
                    # leaving exactly 2 completed pages.
                    run_id = self._run_holder["id"]
                    await self._repository.mark_run_cancelled(run_id)
                return result

        run_holder: dict = {}
        fetcher = CancellingAfterTwoFetcher(crawl_repository, run_holder)
        service = _service(
            company_gateway=company_gateway,
            discovery_gateway=discovery_gateway,
            robots_gateway=robots_gateway,
            crawl_repository=crawl_repository,
            page_fetcher=fetcher,
            content_storage=content_storage,
        )

        # Pre-create the run id the fetcher will use to cancel, by peeking
        # at idempotency: simplest is to run and capture after the fact —
        # instead, monkeypatch via a wrapper that records the run id after
        # creation. We approximate by running once and asserting behavior
        # on the resulting run/pages directly.
        original_create_run = crawl_repository.create_run

        async def _create_and_record(run):
            created = await original_create_run(run)
            run_holder["id"] = created.crawl_run_id
            return created

        crawl_repository.create_run = _create_and_record  # type: ignore[method-assign]

        run = await service.start_crawl_run("company-1", "discovery-1")

        assert run.status == CrawlStatus.CANCELLED
        assert len(crawl_repository.pages) == 2
        for target in crawl_repository.targets.values():
            assert target.status != PageFetchStatus.QUEUED


class TestDuplicateActiveRunAndRetry:
    async def test_duplicate_active_run_conflicts(
        self,
        company_gateway: FakeCompanyCrawlGateway,
        discovery_gateway: FakeDiscoveryCrawlGateway,
        robots_gateway: FakeRobotsPolicyGateway,
        crawl_repository: FakeCrawlRepository,
        content_storage: FakeContentStorage,
    ) -> None:
        _single_homepage_discovery(discovery_gateway)

        class NeverRespondingFetcher(FakePageFetcher):
            async def fetch_page(self, request):
                raise AssertionError("should not be called before conflict check")

        service = _service(
            company_gateway=company_gateway,
            discovery_gateway=discovery_gateway,
            robots_gateway=robots_gateway,
            crawl_repository=crawl_repository,
            page_fetcher=NeverRespondingFetcher(),
            content_storage=content_storage,
        )

        # Seed an already-active run for the same idempotency key.
        from datetime import UTC, datetime

        from app.modules.crawling.domain.idempotency import compute_idempotency_key
        from app.modules.crawling.domain.models import CrawlRun

        options = CrawlRunOptions()
        key = compute_idempotency_key(
            "company-1", "discovery-1", config=service._config, options=options
        )
        now = datetime.now(UTC)
        active_run = CrawlRun(
            company_id="company-1",
            discovery_run_id="discovery-1",
            status=CrawlStatus.RUNNING,
            idempotency_key=key,
            created_at=now,
            updated_at=now,
        )
        await crawl_repository.create_run(active_run)

        try:
            await service.start_crawl_run("company-1", "discovery-1", options)
            raised = False
        except DuplicateActiveCrawlRunError as error:
            raised = True
            assert error.existing_crawl_run_id == active_run.crawl_run_id

        assert raised is True

    async def test_retry_failed_does_not_duplicate_pages(
        self,
        company_gateway: FakeCompanyCrawlGateway,
        discovery_gateway: FakeDiscoveryCrawlGateway,
        robots_gateway: FakeRobotsPolicyGateway,
        crawl_repository: FakeCrawlRepository,
        page_fetcher: FakePageFetcher,
        content_storage: FakeContentStorage,
    ) -> None:
        from app.modules.crawling.domain.exceptions import TimeoutFetchError

        discovery_gateway._urls.extend(
            [
                make_discovered_url(
                    discovery_run_id="discovery-1",
                    url=HOMEPAGE_URL,
                    page_type=PageType.HOMEPAGE,
                    priority=DiscoveryPriority.PRIORITY_1,
                ),
                make_discovered_url(
                    discovery_run_id="discovery-1",
                    url=ABOUT_URL,
                    page_type=PageType.ABOUT,
                    priority=DiscoveryPriority.PRIORITY_1,
                ),
            ]
        )
        page_fetcher.set_response(HOMEPAGE_URL, TimeoutFetchError(HOMEPAGE_URL))
        page_fetcher.set_response(ABOUT_URL, TimeoutFetchError(ABOUT_URL))

        service = _service(
            company_gateway=company_gateway,
            discovery_gateway=discovery_gateway,
            robots_gateway=robots_gateway,
            crawl_repository=crawl_repository,
            page_fetcher=page_fetcher,
            content_storage=content_storage,
        )
        run = await service.start_crawl_run("company-1", "discovery-1")
        assert run.summary.pages_failed == 2

        page_fetcher.set_response(HOMEPAGE_URL, _http_result())
        page_fetcher.set_response(ABOUT_URL, _http_result(final_url=ABOUT_URL))

        await service.retry_failed(run.crawl_run_id)
        await service.retry_failed(run.crawl_run_id)

        pages_for_run = [
            p for p in crawl_repository.pages.values() if p.crawl_run_id == run.crawl_run_id
        ]
        assert len(pages_for_run) == 2


class TestCompanyStatusAdvances:
    async def test_status_advances_on_success(
        self,
        company_gateway: FakeCompanyCrawlGateway,
        discovery_gateway: FakeDiscoveryCrawlGateway,
        robots_gateway: FakeRobotsPolicyGateway,
        crawl_repository: FakeCrawlRepository,
        page_fetcher: FakePageFetcher,
        content_storage: FakeContentStorage,
    ) -> None:
        _single_homepage_discovery(discovery_gateway)
        page_fetcher.set_response(HOMEPAGE_URL, _http_result())
        service = _service(
            company_gateway=company_gateway,
            discovery_gateway=discovery_gateway,
            robots_gateway=robots_gateway,
            crawl_repository=crawl_repository,
            page_fetcher=page_fetcher,
            content_storage=content_storage,
        )

        await service.start_crawl_run("company-1", "discovery-1")

        assert ("company-1", ProcessingStatus.CRAWLING) in company_gateway.status_updates
        assert ("company-1", ProcessingStatus.CRAWLED) in company_gateway.status_updates

    async def test_status_advances_to_failed_when_nothing_succeeds(
        self,
        company_gateway: FakeCompanyCrawlGateway,
        discovery_gateway: FakeDiscoveryCrawlGateway,
        robots_gateway: FakeRobotsPolicyGateway,
        crawl_repository: FakeCrawlRepository,
        page_fetcher: FakePageFetcher,
        content_storage: FakeContentStorage,
    ) -> None:
        from app.modules.crawling.domain.exceptions import TimeoutFetchError

        _single_homepage_discovery(discovery_gateway)
        page_fetcher.set_response(HOMEPAGE_URL, TimeoutFetchError(HOMEPAGE_URL))
        service = _service(
            company_gateway=company_gateway,
            discovery_gateway=discovery_gateway,
            robots_gateway=robots_gateway,
            crawl_repository=crawl_repository,
            page_fetcher=page_fetcher,
            content_storage=content_storage,
            config=CrawlConfig(
                default_delay_s=0.0, min_delay_s=0.0, homepage_failure_marks_run="failed"
            ),
        )

        run = await service.start_crawl_run("company-1", "discovery-1")

        assert run.status == CrawlStatus.FAILED
        assert ("company-1", ProcessingStatus.FAILED) in company_gateway.status_updates


class TestSummaryAccuracy:
    async def test_summary_matches_constructed_scenario(
        self,
        company_gateway: FakeCompanyCrawlGateway,
        discovery_gateway: FakeDiscoveryCrawlGateway,
        crawl_repository: FakeCrawlRepository,
        content_storage: FakeContentStorage,
    ) -> None:
        from app.modules.crawling.domain.exceptions import TimeoutFetchError

        urls = {
            HOMEPAGE_URL: (PageType.HOMEPAGE, "fetch_ok"),
            "https://example.com/about-us": (PageType.ABOUT, "fetch_ok"),
            "https://example.com/unchanged": (PageType.CONTACT, "unchanged"),
            "https://example.com/blocked": (PageType.WHOLESALE, "blocked"),
            "https://example.com/broken": (PageType.CAREERS, "failed"),
        }
        for url, (page_type, _behavior) in urls.items():
            discovery_gateway._urls.append(
                make_discovered_url(
                    discovery_run_id="discovery-1",
                    url=url,
                    page_type=page_type,
                    priority=DiscoveryPriority.PRIORITY_1,
                )
            )

        robots_gateway = FakeRobotsPolicyGateway(disallowed_path_markers={"/blocked"})
        page_fetcher = FakePageFetcher()
        page_fetcher.set_response(HOMEPAGE_URL, _http_result(final_url=HOMEPAGE_URL))
        page_fetcher.set_response(
            "https://example.com/about-us", _http_result(final_url="https://example.com/about-us")
        )
        page_fetcher.set_response(
            "https://example.com/unchanged", _http_result(outcome="not_modified")
        )
        page_fetcher.set_response(
            "https://example.com/broken", TimeoutFetchError("https://example.com/broken")
        )

        # Pre-seed a previous page for the "unchanged" URL so the 304
        # response has something to link back to — without running the
        # whole service twice (which would also make the homepage/about
        # pages "unchanged" on a second identical run).
        from datetime import UTC, datetime

        previous_page = CrawledPage(
            crawl_run_id="previous-run",
            company_id="company-1",
            discovery_run_id="discovery-1",
            original_url="https://example.com/unchanged",
            normalized_url="https://example.com/unchanged",
            page_type=PageType.CONTACT,
            priority=DiscoveryPriority.PRIORITY_1,
            fetch_status=PageFetchStatus.FETCHED,
            http_metadata=HttpMetadata(status_code=200, etag='"v1"'),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            fetched_at=datetime.now(UTC),
        )
        await crawl_repository.save_page(previous_page)

        service = _service(
            company_gateway=company_gateway,
            discovery_gateway=discovery_gateway,
            robots_gateway=robots_gateway,
            crawl_repository=crawl_repository,
            page_fetcher=page_fetcher,
            content_storage=content_storage,
        )
        run = await service.start_crawl_run(
            "company-1", "discovery-1", CrawlRunOptions(force_refresh=False)
        )

        assert run.summary.targets_selected == 5
        assert run.summary.pages_fetched == 2
        assert run.summary.pages_unchanged == 1
        assert run.summary.pages_blocked_by_robots == 1
        assert run.summary.pages_failed == 1
        assert run.summary.duration_ms >= 0


class TestInlineAndExternalStorageThresholds:
    async def test_content_below_threshold_is_stored_inline(
        self,
        company_gateway: FakeCompanyCrawlGateway,
        discovery_gateway: FakeDiscoveryCrawlGateway,
        robots_gateway: FakeRobotsPolicyGateway,
        crawl_repository: FakeCrawlRepository,
        page_fetcher: FakePageFetcher,
        content_storage: FakeContentStorage,
    ) -> None:
        _single_homepage_discovery(discovery_gateway)
        page_fetcher.set_response(HOMEPAGE_URL, _http_result())
        service = _service(
            company_gateway=company_gateway,
            discovery_gateway=discovery_gateway,
            robots_gateway=robots_gateway,
            crawl_repository=crawl_repository,
            page_fetcher=page_fetcher,
            content_storage=content_storage,
            config=CrawlConfig(
                default_delay_s=0.0,
                min_delay_s=0.0,
                inline_cleaned_html_limit_bytes=250_000,
                inline_extracted_text_limit_bytes=250_000,
            ),
        )

        await service.start_crawl_run("company-1", "discovery-1")

        page = next(iter(crawl_repository.pages.values()))
        assert page.content_storage.cleaned_html_mode.value == "inline"
        assert page.content_storage.extracted_text_mode.value == "inline"
        assert page.cleaned_html is not None
        assert page.extracted_text is not None
        assert page.content_storage.cleaned_html_reference is None
        assert page.content_storage.extracted_text_reference is None
        # Raw content is always stored externally, regardless of size.
        assert page.content_storage.raw_content_mode.value == "external"
        assert page.raw_content_reference is not None

    async def test_content_above_threshold_is_stored_externally(
        self,
        company_gateway: FakeCompanyCrawlGateway,
        discovery_gateway: FakeDiscoveryCrawlGateway,
        robots_gateway: FakeRobotsPolicyGateway,
        crawl_repository: FakeCrawlRepository,
        page_fetcher: FakePageFetcher,
        content_storage: FakeContentStorage,
    ) -> None:
        _single_homepage_discovery(discovery_gateway)
        page_fetcher.set_response(HOMEPAGE_URL, _http_result())
        service = _service(
            company_gateway=company_gateway,
            discovery_gateway=discovery_gateway,
            robots_gateway=robots_gateway,
            crawl_repository=crawl_repository,
            page_fetcher=page_fetcher,
            content_storage=content_storage,
            config=CrawlConfig(
                default_delay_s=0.0,
                min_delay_s=0.0,
                inline_cleaned_html_limit_bytes=1,
                inline_extracted_text_limit_bytes=1,
            ),
        )

        await service.start_crawl_run("company-1", "discovery-1")

        page = next(iter(crawl_repository.pages.values()))
        assert page.content_storage.cleaned_html_mode.value == "external"
        assert page.content_storage.extracted_text_mode.value == "external"
        assert page.content_storage.cleaned_html_reference is not None
        assert page.content_storage.extracted_text_reference is not None
        # Inline fields stay empty once content moved to external storage.
        assert page.cleaned_html is None
        assert page.extracted_text is None


class TestChallengePagePolicy:
    """Regression coverage for a gap an evaluation found: `classify_blocked_or_challenge`
    itself was unit-tested, but the `challenge_page_policy` config's
    `failed`/`rejected` branches (as opposed to the default
    `browser_required`) were never exercised at the service level."""

    async def test_failed_policy_marks_page_failed(
        self,
        company_gateway: FakeCompanyCrawlGateway,
        discovery_gateway: FakeDiscoveryCrawlGateway,
        robots_gateway: FakeRobotsPolicyGateway,
        crawl_repository: FakeCrawlRepository,
        page_fetcher: FakePageFetcher,
        content_storage: FakeContentStorage,
    ) -> None:
        _single_homepage_discovery(discovery_gateway)
        page_fetcher.set_response(
            HOMEPAGE_URL, _http_result(body=_read_text("page-cloudflare-challenge.html").encode())
        )
        service = _service(
            company_gateway=company_gateway,
            discovery_gateway=discovery_gateway,
            robots_gateway=robots_gateway,
            crawl_repository=crawl_repository,
            page_fetcher=page_fetcher,
            content_storage=content_storage,
            config=CrawlConfig(
                default_delay_s=0.0, min_delay_s=0.0, challenge_page_policy="failed"
            ),
        )

        run = await service.start_crawl_run("company-1", "discovery-1")

        page = next(iter(crawl_repository.pages.values()))
        assert page.fetch_status == PageFetchStatus.FAILED
        assert run.summary.pages_failed == 1
        assert any(warning.code == "challenge_page_detected" for warning in run.warnings)

    async def test_rejected_policy_marks_page_rejected(
        self,
        company_gateway: FakeCompanyCrawlGateway,
        discovery_gateway: FakeDiscoveryCrawlGateway,
        robots_gateway: FakeRobotsPolicyGateway,
        crawl_repository: FakeCrawlRepository,
        page_fetcher: FakePageFetcher,
        content_storage: FakeContentStorage,
    ) -> None:
        _single_homepage_discovery(discovery_gateway)
        page_fetcher.set_response(
            HOMEPAGE_URL, _http_result(body=_read_text("page-access-denied.html").encode())
        )
        service = _service(
            company_gateway=company_gateway,
            discovery_gateway=discovery_gateway,
            robots_gateway=robots_gateway,
            crawl_repository=crawl_repository,
            page_fetcher=page_fetcher,
            content_storage=content_storage,
            config=CrawlConfig(
                default_delay_s=0.0, min_delay_s=0.0, challenge_page_policy="rejected"
            ),
        )

        run = await service.start_crawl_run("company-1", "discovery-1")

        page = next(iter(crawl_repository.pages.values()))
        assert page.fetch_status == PageFetchStatus.REJECTED
        assert run.summary.pages_failed == 1
        assert any(warning.code == "challenge_page_detected" for warning in run.warnings)

    async def test_browser_required_policy_does_not_fail_the_page(
        self,
        company_gateway: FakeCompanyCrawlGateway,
        discovery_gateway: FakeDiscoveryCrawlGateway,
        robots_gateway: FakeRobotsPolicyGateway,
        crawl_repository: FakeCrawlRepository,
        page_fetcher: FakePageFetcher,
        content_storage: FakeContentStorage,
    ) -> None:
        """The default policy leaves challenge-page handling to browser-fallback
        detection instead of failing/rejecting the page outright."""
        _single_homepage_discovery(discovery_gateway)
        page_fetcher.set_response(
            HOMEPAGE_URL, _http_result(body=_read_text("page-cloudflare-challenge.html").encode())
        )
        service = _service(
            company_gateway=company_gateway,
            discovery_gateway=discovery_gateway,
            robots_gateway=robots_gateway,
            crawl_repository=crawl_repository,
            page_fetcher=page_fetcher,
            content_storage=content_storage,
            config=CrawlConfig(
                default_delay_s=0.0, min_delay_s=0.0, challenge_page_policy="browser_required"
            ),
        )

        run = await service.start_crawl_run("company-1", "discovery-1")

        page = next(iter(crawl_repository.pages.values()))
        assert page.fetch_status != PageFetchStatus.FAILED
        assert page.fetch_status != PageFetchStatus.REJECTED
        assert run.summary.pages_failed == 0
