from collections.abc import Awaitable, Callable

from httpx import AsyncClient

CreateCompany = Callable[..., Awaitable[dict]]


class TestDuplicateDomain:
    async def test_duplicate_normalized_domain_is_rejected(
        self, client: AsyncClient, create_company: CreateCompany
    ) -> None:
        await create_company(client, "example.com")

        response = await client.post("/api/companies", json={"domain": "https://www.example.com"})

        assert response.status_code == 409

    async def test_original_company_is_unaffected_by_rejected_duplicate(
        self, client: AsyncClient, create_company: CreateCompany
    ) -> None:
        created = await create_company(client, "example.com")
        await client.post("/api/companies", json={"domain": "example.com"})

        response = await client.get(f"/api/companies/{created['companyId']}")

        assert response.status_code == 200
        assert response.json()["companyId"] == created["companyId"]
