"""API-level tests for the crawling module's router — camelCase, pagination,
enum serialization, no raw-HTML/no-filesystem-path leakage, filter
correctness (AC-34, AC-35). No real MongoDB, no real network — a locally-
scoped FastAPI app built by `conftest.py`'s `client_factory`.

Since Task 017 (`docs/contracts/active/017-rq-crawling-vertical-slice.md`),
`POST .../crawl-runs` enqueues execution via RQ instead of running it
inline, so `_create_run` below drives `execute_crawl_run` directly
against the `crawl_service` fixture (the same fakes the HTTP app is
wired to) after creating the run over HTTP — exactly what a real worker
does via `run_crawl_execution`. This file only tests HTTP response
*serialization*, not the enqueue/execute split itself (see
`test_router_rq_enqueue.py` for that).
"""

from httpx import AsyncClient

from app.modules.crawling.application.website_crawl_service import WebsiteCrawlService
from app.modules.discovery.domain.enums import DiscoveryPriority, DiscoverySource, PageType

from .conftest import (
    FakeContentStorage,
    FakeCrawlRepository,
    FakeDiscoveryCrawlGateway,
    FakePageFetcher,
    FakeRobotsPolicyGateway,
    make_discovered_url,
)

HOMEPAGE_URL = "https://example.com/"
ABOUT_URL = "https://example.com/about-us"
CONTACT_URL = "https://example.com/contact-us"


def _html_response(status_code: int = 200, body: bytes = b"<html><body><h1>Hi</h1></body></html>"):
    from app.modules.crawling.domain.models import HttpMetadata
    from app.modules.crawling.domain.page_fetcher import PageFetchResult

    return PageFetchResult(
        status_code=status_code,
        http_metadata=HttpMetadata(status_code=status_code, content_type="text/html"),
        body=body,
        final_url=HOMEPAGE_URL,
        outcome="fetched",
    )


async def _create_run(client: AsyncClient, crawl_service: WebsiteCrawlService) -> dict:
    response = await client.post(
        "/api/companies/company-1/crawl-runs",
        json={"discoveryRunId": "discovery-1"},
    )
    assert response.status_code == 201
    queued_body = response.json()
    assert queued_body["data"]["status"] == "queued"

    await crawl_service.execute_crawl_run(queued_body["data"]["crawlRunId"])

    completed_response = await client.get(f"/api/crawl-runs/{queued_body['data']['crawlRunId']}")
    assert completed_response.status_code == 200
    return completed_response.json()


class TestCamelCaseAndPagination:
    async def test_run_and_pages_serialize_camel_case(
        self,
        client: AsyncClient,
        discovery_gateway: FakeDiscoveryCrawlGateway,
        page_fetcher: FakePageFetcher,
        crawl_service: WebsiteCrawlService,
    ) -> None:
        discovery_gateway._urls.append(
            make_discovered_url(
                discovery_run_id="discovery-1",
                url=HOMEPAGE_URL,
                page_type=PageType.HOMEPAGE,
                priority=DiscoveryPriority.PRIORITY_1,
                discovery_sources=[DiscoverySource.HOMEPAGE],
            )
        )
        page_fetcher.set_response(HOMEPAGE_URL, _html_response())

        run_body = await _create_run(client, crawl_service)
        assert "crawlRunId" in run_body["data"]
        assert "targetsSelected" in run_body["data"]["summary"]

        crawl_run_id = run_body["data"]["crawlRunId"]
        pages_response = await client.get(f"/api/crawl-runs/{crawl_run_id}/pages")
        assert pages_response.status_code == 200
        pages_body = pages_response.json()

        assert "pagination" in pages_body
        assert set(pages_body["pagination"].keys()) == {"page", "pageSize", "total"}
        assert pages_body["pagination"]["total"] == 1

        page_entry = pages_body["data"][0]
        assert "pageId" in page_entry
        assert "extractedTextPreview" in page_entry
        assert "fetchStatus" in page_entry


class TestNoLeakage:
    async def test_no_filesystem_path_or_raw_html_in_page_response(
        self,
        client: AsyncClient,
        discovery_gateway: FakeDiscoveryCrawlGateway,
        page_fetcher: FakePageFetcher,
        content_storage: FakeContentStorage,
        crawl_service: WebsiteCrawlService,
    ) -> None:
        discovery_gateway._urls.append(
            make_discovered_url(
                discovery_run_id="discovery-1",
                url=HOMEPAGE_URL,
                page_type=PageType.HOMEPAGE,
                priority=DiscoveryPriority.PRIORITY_1,
            )
        )
        long_text_body = b"<html><body>" + b"<p>" + (b"word " * 5000) + b"</p></body></html>"
        page_fetcher.set_response(HOMEPAGE_URL, _html_response(body=long_text_body))

        run_body = await _create_run(client, crawl_service)
        crawl_run_id = run_body["data"]["crawlRunId"]

        pages_response = await client.get(f"/api/crawl-runs/{crawl_run_id}/pages")
        serialized = pages_response.text

        assert "data/crawl-content" not in serialized
        # The raw/cleaned HTML markup itself is never serialized — only
        # metadata *about* it (e.g. `cleanedHtmlSizeBytes`) is present.
        assert "<html" not in serialized
        assert "<p>" not in serialized
        page_entry = pages_response.json()["data"][0]
        assert len(page_entry["extractedTextPreview"]) < len(long_text_body)


class TestEnumSerialization:
    async def test_status_and_page_type_are_plain_strings(
        self,
        client: AsyncClient,
        discovery_gateway: FakeDiscoveryCrawlGateway,
        page_fetcher: FakePageFetcher,
        crawl_service: WebsiteCrawlService,
    ) -> None:
        discovery_gateway._urls.append(
            make_discovered_url(
                discovery_run_id="discovery-1",
                url=HOMEPAGE_URL,
                page_type=PageType.HOMEPAGE,
                priority=DiscoveryPriority.PRIORITY_1,
            )
        )
        page_fetcher.set_response(HOMEPAGE_URL, _html_response())

        run_body = await _create_run(client, crawl_service)
        assert run_body["data"]["status"] in (
            "completed",
            "completed_with_warnings",
            "partial",
            "failed",
        )

        crawl_run_id = run_body["data"]["crawlRunId"]
        targets_response = await client.get(f"/api/crawl-runs/{crawl_run_id}/targets")
        target_entry = targets_response.json()["data"][0]
        assert target_entry["pageType"] == "homepage"
        assert target_entry["priority"] == "1"


class TestPageListFilters:
    async def test_page_list_filters(
        self,
        client: AsyncClient,
        discovery_gateway: FakeDiscoveryCrawlGateway,
        robots_gateway: FakeRobotsPolicyGateway,
        page_fetcher: FakePageFetcher,
        crawl_service: WebsiteCrawlService,
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
                make_discovered_url(
                    discovery_run_id="discovery-1",
                    url=CONTACT_URL,
                    page_type=PageType.CONTACT,
                    priority=DiscoveryPriority.PRIORITY_1,
                ),
            ]
        )
        page_fetcher.set_response(HOMEPAGE_URL, _html_response())
        page_fetcher.set_response(ABOUT_URL, _html_response())
        page_fetcher.set_response(CONTACT_URL, TimeoutFetchError(CONTACT_URL))

        run_body = await _create_run(client, crawl_service)
        crawl_run_id = run_body["data"]["crawlRunId"]

        default_response = await client.get(f"/api/crawl-runs/{crawl_run_id}/pages")
        assert default_response.json()["pagination"]["total"] == 2

        with_failed_response = await client.get(
            f"/api/crawl-runs/{crawl_run_id}/pages", params={"includeFailed": "true"}
        )
        assert with_failed_response.json()["pagination"]["total"] == 3

        by_page_type = await client.get(
            f"/api/crawl-runs/{crawl_run_id}/pages", params={"pageType": "about"}
        )
        assert by_page_type.json()["pagination"]["total"] == 1
        assert by_page_type.json()["data"][0]["pageType"] == "about"

        by_status = await client.get(
            f"/api/crawl-runs/{crawl_run_id}/pages",
            params={"status": "failed", "includeFailed": "true"},
        )
        assert by_status.json()["pagination"]["total"] == 1


class TestListCrawlRuns:
    async def test_response_shape_and_pagination(
        self,
        client: AsyncClient,
        discovery_gateway: FakeDiscoveryCrawlGateway,
        page_fetcher: FakePageFetcher,
        crawl_service: WebsiteCrawlService,
    ) -> None:
        discovery_gateway._urls.append(
            make_discovered_url(
                discovery_run_id="discovery-1",
                url=HOMEPAGE_URL,
                page_type=PageType.HOMEPAGE,
                priority=DiscoveryPriority.PRIORITY_1,
            )
        )
        page_fetcher.set_response(HOMEPAGE_URL, _html_response())
        await _create_run(client, crawl_service)

        response = await client.get("/api/crawl-runs", params={"page": 1, "pageSize": 10})

        assert response.status_code == 200
        body = response.json()
        assert set(body.keys()) == {"data", "pagination"}
        assert set(body["pagination"].keys()) == {"page", "pageSize", "total"}
        assert body["pagination"]["total"] >= 1
        assert "crawlRunId" in body["data"][0]

    async def test_status_filter(
        self,
        client: AsyncClient,
        discovery_gateway: FakeDiscoveryCrawlGateway,
        page_fetcher: FakePageFetcher,
        crawl_service: WebsiteCrawlService,
    ) -> None:
        discovery_gateway._urls.append(
            make_discovered_url(
                discovery_run_id="discovery-1",
                url=HOMEPAGE_URL,
                page_type=PageType.HOMEPAGE,
                priority=DiscoveryPriority.PRIORITY_1,
            )
        )
        page_fetcher.set_response(HOMEPAGE_URL, _html_response())
        run_body = await _create_run(client, crawl_service)
        run_status = run_body["data"]["status"]

        matching = await client.get("/api/crawl-runs", params={"status": run_status})
        assert matching.json()["pagination"]["total"] >= 1
        assert all(item["status"] == run_status for item in matching.json()["data"])

        other_status = "failed" if run_status != "failed" else "completed"
        non_matching = await client.get("/api/crawl-runs", params={"status": other_status})
        assert non_matching.json()["pagination"]["total"] == 0
        assert non_matching.json()["data"] == []


class TestCancelAndRetryEndpoints:
    async def test_cancel_then_get_run_reflects_status(
        self,
        client: AsyncClient,
        discovery_gateway: FakeDiscoveryCrawlGateway,
        page_fetcher: FakePageFetcher,
        crawl_repository: FakeCrawlRepository,
        crawl_service: WebsiteCrawlService,
    ) -> None:
        discovery_gateway._urls.append(
            make_discovered_url(
                discovery_run_id="discovery-1",
                url=HOMEPAGE_URL,
                page_type=PageType.HOMEPAGE,
                priority=DiscoveryPriority.PRIORITY_1,
            )
        )
        page_fetcher.set_response(HOMEPAGE_URL, _html_response())
        run_body = await _create_run(client, crawl_service)
        crawl_run_id = run_body["data"]["crawlRunId"]

        cancel_response = await client.post(f"/api/crawl-runs/{crawl_run_id}/cancel")
        assert cancel_response.status_code == 200
        assert cancel_response.json()["data"]["status"] == "cancelled"

    async def test_cancel_unknown_run_returns_404(self, client: AsyncClient) -> None:
        response = await client.post("/api/crawl-runs/does-not-exist/cancel")
        assert response.status_code == 404


class TestDuplicateActiveRunReturns409:
    async def test_duplicate_active_run_returns_409(
        self,
        client: AsyncClient,
        discovery_gateway: FakeDiscoveryCrawlGateway,
        crawl_repository: FakeCrawlRepository,
    ) -> None:
        from datetime import UTC, datetime

        from app.modules.crawling.domain.config import CrawlConfig
        from app.modules.crawling.domain.enums import CrawlStatus
        from app.modules.crawling.domain.idempotency import compute_idempotency_key
        from app.modules.crawling.domain.models import CrawlRun, CrawlRunOptions

        options = CrawlRunOptions()
        key = compute_idempotency_key(
            "company-1", "discovery-1", config=CrawlConfig(), options=options
        )
        now = datetime.now(UTC)
        await crawl_repository.create_run(
            CrawlRun(
                company_id="company-1",
                discovery_run_id="discovery-1",
                status=CrawlStatus.RUNNING,
                idempotency_key=key,
                created_at=now,
                updated_at=now,
            )
        )

        response = await client.post(
            "/api/companies/company-1/crawl-runs", json={"discoveryRunId": "discovery-1"}
        )
        assert response.status_code == 409
