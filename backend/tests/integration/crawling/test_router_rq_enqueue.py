"""Router-level tests for Task 017's RQ-enqueue behavior
(`docs/contracts/active/017-rq-crawling-vertical-slice.md`) — AC-01,
AC-02, AC-07, AC-08. No real MongoDB, no real network, and (for the
enqueue path) no real Redis — a locally-defined `FakeQueue` overrides
`get_crawl_queue` via `client_factory`'s `queue` parameter, recording
`enqueue_call` invocations instead of talking to RQ.

`cancel_crawl_run`'s best-effort RQ-job-cancel step uses the real Redis
connection directly (`app.queue.get_redis_connection`) rather than the
injected queue — per the contract's own design, this isn't parameterized
via `Depends`. `test_cancel_tolerates_missing_rq_job` still passes
whether or not a real Redis is reachable in the test environment: a
missing job raises `NoSuchJobError` (swallowed), and any other
connection failure is caught and logged by the router's broader
best-effort `except Exception` clause — neither ever propagates to the
caller.
"""

from app.modules.crawling.application.website_crawl_service import WebsiteCrawlService
from app.modules.crawling.domain.enums import CrawlStatus
from app.modules.crawling.domain.exceptions import TimeoutFetchError
from app.modules.crawling.infrastructure.rq_jobs import CRAWL_JOB_TIMEOUT, run_crawl_execution
from app.modules.discovery.domain.enums import DiscoveryPriority, PageType

from .conftest import (
    ClientFactory,
    FakeCompanyCrawlGateway,
    FakeContentStorage,
    FakeCrawlRepository,
    FakeDiscoveryCrawlGateway,
    FakePageFetcher,
    FakeRobotsPolicyGateway,
    make_discovered_url,
)

HOMEPAGE_URL = "https://example.com/"

# RQ's own default job timeout — the concrete regression guard for AC-02's
# "a timeout other than RQ's default" assertion.
RQ_DEFAULT_TIMEOUT = 180


class FakeQueue:
    """Records every `enqueue_call` invocation instead of talking to real
    Redis/RQ — proves the router enqueues work instead of executing it
    inline (AC-01, AC-02, AC-07)."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def enqueue_call(self, **kwargs) -> None:
        self.calls.append(kwargs)


def _single_homepage_discovery(discovery_gateway: FakeDiscoveryCrawlGateway) -> None:
    discovery_gateway._urls.append(
        make_discovered_url(
            discovery_run_id="discovery-1",
            url=HOMEPAGE_URL,
            page_type=PageType.HOMEPAGE,
            priority=DiscoveryPriority.PRIORITY_1,
        )
    )


def _service(
    *,
    company_gateway: FakeCompanyCrawlGateway,
    discovery_gateway: FakeDiscoveryCrawlGateway,
    robots_gateway: FakeRobotsPolicyGateway,
    crawl_repository: FakeCrawlRepository,
    page_fetcher: FakePageFetcher,
    content_storage: FakeContentStorage,
) -> WebsiteCrawlService:
    return WebsiteCrawlService(
        company_gateway=company_gateway,
        discovery_gateway=discovery_gateway,
        robots_gateway=robots_gateway,
        repository=crawl_repository,
        page_fetcher=page_fetcher,
        content_storage=content_storage,
    )


class TestCreateCrawlRunEnqueues:
    async def test_create_crawl_run_returns_queued_without_executing(
        self,
        client_factory: ClientFactory,
        company_gateway: FakeCompanyCrawlGateway,
        discovery_gateway: FakeDiscoveryCrawlGateway,
        robots_gateway: FakeRobotsPolicyGateway,
        crawl_repository: FakeCrawlRepository,
        page_fetcher: FakePageFetcher,
        content_storage: FakeContentStorage,
    ) -> None:
        _single_homepage_discovery(discovery_gateway)
        # Deliberately no configured response: `FakePageFetcher.fetch_page`
        # raises `AssertionError` for any URL it wasn't told about, so any
        # synchronous execution attempted within the request would fail
        # loudly rather than silently succeeding.
        async with client_factory(
            company_gateway=company_gateway,
            discovery_gateway=discovery_gateway,
            robots_gateway=robots_gateway,
            crawl_repository=crawl_repository,
            page_fetcher=page_fetcher,
            content_storage=content_storage,
            queue=FakeQueue(),
        ) as client:
            response = await client.post(
                "/api/companies/company-1/crawl-runs",
                json={"discoveryRunId": "discovery-1"},
            )

        assert response.status_code == 201
        assert response.json()["data"]["status"] == "queued"
        assert page_fetcher.call_log == []

    async def test_enqueue_call_arguments(
        self,
        client_factory: ClientFactory,
        company_gateway: FakeCompanyCrawlGateway,
        discovery_gateway: FakeDiscoveryCrawlGateway,
        robots_gateway: FakeRobotsPolicyGateway,
        crawl_repository: FakeCrawlRepository,
        page_fetcher: FakePageFetcher,
        content_storage: FakeContentStorage,
    ) -> None:
        _single_homepage_discovery(discovery_gateway)
        queue = FakeQueue()

        async with client_factory(
            company_gateway=company_gateway,
            discovery_gateway=discovery_gateway,
            robots_gateway=robots_gateway,
            crawl_repository=crawl_repository,
            page_fetcher=page_fetcher,
            content_storage=content_storage,
            queue=queue,
        ) as client:
            response = await client.post(
                "/api/companies/company-1/crawl-runs",
                json={"discoveryRunId": "discovery-1"},
            )

        run_id = response.json()["data"]["crawlRunId"]
        assert len(queue.calls) == 1
        call = queue.calls[0]
        assert call["func"] is run_crawl_execution
        assert call["args"] == (run_id,)
        assert call["job_id"] == run_id
        assert call["timeout"] == CRAWL_JOB_TIMEOUT
        assert call["timeout"] != RQ_DEFAULT_TIMEOUT


class TestRetryFailedEnqueues:
    async def test_retry_failed_enqueues(
        self,
        client_factory: ClientFactory,
        company_gateway: FakeCompanyCrawlGateway,
        discovery_gateway: FakeDiscoveryCrawlGateway,
        robots_gateway: FakeRobotsPolicyGateway,
        crawl_repository: FakeCrawlRepository,
        page_fetcher: FakePageFetcher,
        content_storage: FakeContentStorage,
    ) -> None:
        _single_homepage_discovery(discovery_gateway)
        page_fetcher.set_response(HOMEPAGE_URL, TimeoutFetchError(HOMEPAGE_URL))

        # Drive a real run to completion out-of-band, exactly as a worker
        # would via `run_crawl_execution` — ending with a failed target to
        # retry (a precondition `retry-failed` requires: a terminal run).
        service = _service(
            company_gateway=company_gateway,
            discovery_gateway=discovery_gateway,
            robots_gateway=robots_gateway,
            crawl_repository=crawl_repository,
            page_fetcher=page_fetcher,
            content_storage=content_storage,
        )
        enqueued = await service.enqueue_crawl_run("company-1", "discovery-1")
        completed = await service.execute_crawl_run(enqueued.crawl_run_id)
        assert completed.summary.pages_failed == 1

        queue = FakeQueue()
        async with client_factory(
            company_gateway=company_gateway,
            discovery_gateway=discovery_gateway,
            robots_gateway=robots_gateway,
            crawl_repository=crawl_repository,
            page_fetcher=page_fetcher,
            content_storage=content_storage,
            queue=queue,
        ) as client:
            response = await client.post(f"/api/crawl-runs/{completed.crawl_run_id}/retry-failed")

        assert response.status_code == 200
        assert response.json()["data"]["status"] == "queued"
        assert len(queue.calls) == 1
        call = queue.calls[0]
        assert call["job_id"] == f"{completed.crawl_run_id}-retry"
        assert call["args"] == (completed.crawl_run_id,)
        assert call["timeout"] == CRAWL_JOB_TIMEOUT
        # `retry_failed` itself was not executed synchronously — the run
        # is immediately `queued`, not re-evaluated back to a terminal
        # status by any inline retry logic.
        assert crawl_repository.runs[completed.crawl_run_id].status == CrawlStatus.QUEUED


class TestCancelToleratesMissingRqJob:
    async def test_cancel_tolerates_missing_rq_job(
        self,
        client_factory: ClientFactory,
        company_gateway: FakeCompanyCrawlGateway,
        discovery_gateway: FakeDiscoveryCrawlGateway,
        robots_gateway: FakeRobotsPolicyGateway,
        crawl_repository: FakeCrawlRepository,
        page_fetcher: FakePageFetcher,
        content_storage: FakeContentStorage,
    ) -> None:
        _single_homepage_discovery(discovery_gateway)
        service = _service(
            company_gateway=company_gateway,
            discovery_gateway=discovery_gateway,
            robots_gateway=robots_gateway,
            crawl_repository=crawl_repository,
            page_fetcher=page_fetcher,
            content_storage=content_storage,
        )
        # A run with no corresponding RQ job ever enqueued through this
        # test's `FakeQueue` (it never talks to real Redis) — simulating a
        # run created before this feature, or whose job already finished.
        run = await service.enqueue_crawl_run("company-1", "discovery-1")

        async with client_factory(
            company_gateway=company_gateway,
            discovery_gateway=discovery_gateway,
            robots_gateway=robots_gateway,
            crawl_repository=crawl_repository,
            page_fetcher=page_fetcher,
            content_storage=content_storage,
            queue=FakeQueue(),
        ) as client:
            response = await client.post(f"/api/crawl-runs/{run.crawl_run_id}/cancel")

        assert response.status_code == 200
        assert response.json()["data"]["status"] == "cancelled"
        assert crawl_repository.runs[run.crawl_run_id].status == CrawlStatus.CANCELLED
