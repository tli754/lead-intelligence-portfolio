"""API-level integration tests: camelCase, pagination, enum serialization,
excluded-URL filtering — via the real HTTP layer, fakes underneath.

Since Task 020 (`docs/contracts/active/020-rq-discovery-vertical-slice.md`),
`POST .../discovery-runs` enqueues execution via RQ instead of running it
inline, so tests below that need a *completed* run with discovered URLs
drive `execute_discovery_run` directly against a `WebsiteDiscoveryService`
built from the exact same fakes the HTTP app is wired to (after creating
the run over HTTP) — exactly what a real worker does via
`run_discovery_execution`. This file only tests HTTP response
*serialization*, not the enqueue/execute split itself (see
`test_router_rq_enqueue.py` for that).
"""

from httpx import AsyncClient

from app.modules.discovery.application.website_discovery_service import WebsiteDiscoveryService

from .conftest import FakeHttpDiscoveryClient

BASIC_HOMEPAGE_HTML = """
<html><body>
  <nav><a href="/about-us">About Us</a></nav>
  <footer><a href="/cart">Cart</a></footer>
</body></html>
"""


class TestCreateDiscoveryRunResponse:
    async def test_response_shape_is_camel_case(self, client: AsyncClient) -> None:
        response = await client.post("/api/companies/company-1/discovery-runs")

        assert response.status_code == 201
        body = response.json()
        assert set(body.keys()) == {"data"}
        run = body["data"]
        assert set(run.keys()) == {
            "discoveryRunId",
            "companyId",
            "rootDomain",
            "homepageUrl",
            "status",
            "startedAt",
            "completedAt",
            "summary",
            "error",
            "createdAt",
            "updatedAt",
        }
        assert set(run["summary"].keys()) == {
            "urlsFound",
            "urlsAccepted",
            "urlsExcluded",
            "sitemapUrlsFound",
            "robotsUrlsFound",
            "duplicateUrlsMerged",
            "warnings",
            "durationMs",
        }

    async def test_unknown_company_returns_404(self, client: AsyncClient) -> None:
        response = await client.post("/api/companies/does-not-exist/discovery-runs")
        assert response.status_code == 404


class TestGetLatestDiscoveryRun:
    async def test_returns_the_most_recent_run(self, client: AsyncClient) -> None:
        created = await client.post("/api/companies/company-1/discovery-runs")
        run_id = created.json()["data"]["discoveryRunId"]

        response = await client.get("/api/companies/company-1/discovery-runs/latest")

        assert response.status_code == 200
        assert response.json()["data"]["discoveryRunId"] == run_id

    async def test_no_runs_yet_returns_404(self, client: AsyncClient) -> None:
        response = await client.get("/api/companies/company-1/discovery-runs/latest")
        assert response.status_code == 404


class TestGetDiscoveryRunById:
    async def test_get_by_id(self, client: AsyncClient) -> None:
        created = await client.post("/api/companies/company-1/discovery-runs")
        run_id = created.json()["data"]["discoveryRunId"]

        response = await client.get(f"/api/discovery-runs/{run_id}")

        assert response.status_code == 200
        assert response.json()["data"]["discoveryRunId"] == run_id

    async def test_missing_run_returns_404(self, client: AsyncClient) -> None:
        response = await client.get("/api/discovery-runs/does-not-exist")
        assert response.status_code == 404


class TestListDiscoveryRuns:
    async def test_response_shape_and_pagination(self, client: AsyncClient) -> None:
        await client.post("/api/companies/company-1/discovery-runs")

        response = await client.get("/api/discovery-runs", params={"page": 1, "pageSize": 10})

        assert response.status_code == 200
        body = response.json()
        assert set(body.keys()) == {"data", "pagination"}
        assert set(body["pagination"].keys()) == {"page", "pageSize", "total"}
        assert body["pagination"]["page"] == 1
        assert body["pagination"]["pageSize"] == 10
        assert body["pagination"]["total"] >= 1
        assert "discoveryRunId" in body["data"][0]

    async def test_status_filter(self, client: AsyncClient) -> None:
        created = await client.post("/api/companies/company-1/discovery-runs")
        run_status = created.json()["data"]["status"]

        matching = await client.get("/api/discovery-runs", params={"status": run_status})
        assert matching.json()["pagination"]["total"] >= 1
        assert all(item["status"] == run_status for item in matching.json()["data"])

        other_status = "failed" if run_status != "failed" else "completed"
        non_matching = await client.get("/api/discovery-runs", params={"status": other_status})
        assert non_matching.json()["pagination"]["total"] == 0
        assert non_matching.json()["data"] == []


class TestListDiscoveredUrls:
    async def test_response_shape_and_pagination(
        self, client_factory, company_gateway, discovery_repository
    ) -> None:
        http_client = FakeHttpDiscoveryClient(homepage_html=BASIC_HOMEPAGE_HTML)
        service = WebsiteDiscoveryService(
            company_gateway=company_gateway,
            discovery_repository=discovery_repository,
            http_client=http_client,
        )
        async with client_factory(company_gateway, discovery_repository, http_client) as client:
            created = await client.post("/api/companies/company-1/discovery-runs")
            run_id = created.json()["data"]["discoveryRunId"]
            await service.execute_discovery_run(run_id)

            response = await client.get(
                f"/api/discovery-runs/{run_id}/urls", params={"page": 1, "pageSize": 10}
            )

        assert response.status_code == 200
        body = response.json()
        assert set(body.keys()) == {"data", "pagination"}
        assert body["pagination"] == {
            "page": 1,
            "pageSize": 10,
            "total": body["pagination"]["total"],
        }
        if body["data"]:
            item = body["data"][0]
            assert set(item.keys()) == {
                "discoveredUrlId",
                "discoveryRunId",
                "companyId",
                "url",
                "normalizedUrl",
                "pageType",
                "pageTypeConfidence",
                "priority",
                "discoverySources",
                "sourceUrls",
                "anchorTexts",
                "depth",
                "isSameDomain",
                "isAllowed",
                "firstDiscoveredAt",
                "lastDiscoveredAt",
                "metadata",
            }

    async def test_excluded_urls_hidden_by_default(
        self, client_factory, company_gateway, discovery_repository
    ) -> None:
        http_client = FakeHttpDiscoveryClient(homepage_html=BASIC_HOMEPAGE_HTML)
        service = WebsiteDiscoveryService(
            company_gateway=company_gateway,
            discovery_repository=discovery_repository,
            http_client=http_client,
        )
        async with client_factory(company_gateway, discovery_repository, http_client) as client:
            created = await client.post("/api/companies/company-1/discovery-runs")
            run_id = created.json()["data"]["discoveryRunId"]
            await service.execute_discovery_run(run_id)

            default_response = await client.get(f"/api/discovery-runs/{run_id}/urls")
            included_response = await client.get(
                f"/api/discovery-runs/{run_id}/urls", params={"includeExcluded": "true"}
            )

        default_priorities = {item["priority"] for item in default_response.json()["data"]}
        included_priorities = {item["priority"] for item in included_response.json()["data"]}

        assert "excluded" not in default_priorities
        assert "excluded" in included_priorities

    async def test_enum_query_params_serialize_correctly(self, client: AsyncClient) -> None:
        created = await client.post("/api/companies/company-1/discovery-runs")
        run_id = created.json()["data"]["discoveryRunId"]

        response = await client.get(
            f"/api/discovery-runs/{run_id}/urls", params={"pageType": "about"}
        )

        assert response.status_code == 200
        assert all(item["pageType"] == "about" for item in response.json()["data"])

    async def test_invalid_page_type_returns_422(self, client: AsyncClient) -> None:
        created = await client.post("/api/companies/company-1/discovery-runs")
        run_id = created.json()["data"]["discoveryRunId"]

        response = await client.get(
            f"/api/discovery-runs/{run_id}/urls", params={"pageType": "not-a-real-type"}
        )

        assert response.status_code == 422
