from collections.abc import Awaitable, Callable

from httpx import AsyncClient

from app.main import app
from app.modules.companies.api.router import get_http_discovery_client

from .conftest import StubHttpDiscoveryClient

CreateCompany = Callable[..., Awaitable[dict]]


class TestCreateCompany:
    async def test_create_company_returns_camel_case_body_with_defaults(
        self, client: AsyncClient, create_company: CreateCompany
    ) -> None:
        body = await create_company(
            client,
            "example.com",
            company_name="Example",
            platform="Shopify",
            country="US",
            city="NYC",
        )

        assert body["domain"] == "example.com"
        assert body["normalizedDomain"] == "example.com"
        assert body["identity"] == {
            "companyName": "Example",
            "platform": "Shopify",
            "country": "US",
            "city": "NYC",
        }
        assert body["processing"]["status"] == "discovered"
        assert body["workflow"]["manualStatus"] == "unreviewed"
        assert body["workflow"]["shortlisted"] is False
        assert body["workflow"]["notesCount"] == 0
        assert body["documentVersion"] == 1
        assert body["companyId"]
        assert body["createdAt"]
        assert body["updatedAt"]

    async def test_create_company_normalizes_domain(
        self, client: AsyncClient, create_company: CreateCompany
    ) -> None:
        body = await create_company(client, "https://WWW.Example.com/path")
        assert body["normalizedDomain"] == "example.com"

    async def test_rejects_empty_domain(self, client: AsyncClient) -> None:
        response = await client.post("/api/companies", json={"domain": ""})
        assert response.status_code == 422

    async def test_auto_triggers_discovery_on_creation(
        self, client: AsyncClient, create_company: CreateCompany
    ) -> None:
        """ADR 0003 / Task 015: creation synchronously runs discovery, and
        the response reflects the post-discovery company state."""
        body = await create_company(client, "discoverable.com")

        assert body["processing"]["status"] == "discovered"
        assert body["processing"]["latestDiscoveryRunId"]

    async def test_still_creates_company_when_discovery_fails(
        self, client: AsyncClient, create_company: CreateCompany
    ) -> None:
        """Company creation must not fail just because discovery did —
        only the processing status reflects the failure. Per
        `run_discovery`'s own behavior, `latest_discovery_run_id` is only
        set on the success path, so it stays null here even though a
        (failed) DiscoveryRun record was created."""
        app.dependency_overrides[get_http_discovery_client] = lambda: StubHttpDiscoveryClient(
            homepage_success=False
        )
        try:
            body = await create_company(client, "unreachable.com")
        finally:
            app.dependency_overrides.pop(get_http_discovery_client, None)

        assert body["processing"]["status"] == "failed"
        assert body["processing"]["latestDiscoveryRunId"] is None
