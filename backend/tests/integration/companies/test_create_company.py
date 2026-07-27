from collections.abc import Awaitable, Callable

from httpx import AsyncClient

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
        assert body["processing"]["status"] == "imported"
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
