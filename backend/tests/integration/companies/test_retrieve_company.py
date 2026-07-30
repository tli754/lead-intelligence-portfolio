from collections.abc import Awaitable, Callable

from httpx import AsyncClient

CreateCompany = Callable[..., Awaitable[dict]]


class TestRetrieveCompany:
    async def test_get_by_id(self, client: AsyncClient, create_company: CreateCompany) -> None:
        created = await create_company(client, "example.com", company_name="Example")

        response = await client.get(f"/api/companies/{created['companyId']}")

        assert response.status_code == 200
        body = response.json()
        assert body["companyId"] == created["companyId"]
        assert body["domain"] == "example.com"

    async def test_get_missing_returns_404(self, client: AsyncClient) -> None:
        response = await client.get("/api/companies/does-not-exist")
        assert response.status_code == 404
