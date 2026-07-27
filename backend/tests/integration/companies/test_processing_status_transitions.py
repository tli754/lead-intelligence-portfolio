from collections.abc import Awaitable, Callable

from httpx import AsyncClient

CreateCompany = Callable[..., Awaitable[dict]]


class TestProcessingStatusTransitions:
    async def test_valid_transition_succeeds(
        self, client: AsyncClient, create_company: CreateCompany
    ) -> None:
        created = await create_company(client, "example.com")
        assert created["processing"]["status"] == "imported"

        response = await client.patch(
            f"/api/companies/{created['companyId']}/processing-status",
            json={"status": "discovering"},
        )

        assert response.status_code == 200
        assert response.json()["processing"]["status"] == "discovering"

    async def test_invalid_transition_is_rejected(
        self, client: AsyncClient, create_company: CreateCompany
    ) -> None:
        created = await create_company(client, "example.com")

        # imported -> ready skips the entire pipeline; not a valid edge.
        response = await client.patch(
            f"/api/companies/{created['companyId']}/processing-status",
            json={"status": "ready"},
        )

        assert response.status_code == 409

    async def test_missing_company_returns_404(self, client: AsyncClient) -> None:
        response = await client.patch(
            "/api/companies/does-not-exist/processing-status",
            json={"status": "discovering"},
        )
        assert response.status_code == 404

    async def test_invalid_status_value_returns_422(
        self, client: AsyncClient, create_company: CreateCompany
    ) -> None:
        created = await create_company(client, "example.com")

        response = await client.patch(
            f"/api/companies/{created['companyId']}/processing-status",
            json={"status": "not-a-real-status"},
        )

        assert response.status_code == 422
