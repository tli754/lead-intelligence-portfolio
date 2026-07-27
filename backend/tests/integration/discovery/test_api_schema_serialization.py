"""API-level integration tests: camelCase, pagination, enum serialization,
excluded-URL filtering — via the real HTTP layer, fakes underneath."""

from httpx import AsyncClient

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


class TestListDiscoveredUrls:
    async def test_response_shape_and_pagination(
        self, client_factory, company_gateway, discovery_repository
    ) -> None:
        http_client = FakeHttpDiscoveryClient(homepage_html=BASIC_HOMEPAGE_HTML)
        async with client_factory(company_gateway, discovery_repository, http_client) as client:
            created = await client.post("/api/companies/company-1/discovery-runs")
            run_id = created.json()["data"]["discoveryRunId"]

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
        async with client_factory(company_gateway, discovery_repository, http_client) as client:
            created = await client.post("/api/companies/company-1/discovery-runs")
            run_id = created.json()["data"]["discoveryRunId"]

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
