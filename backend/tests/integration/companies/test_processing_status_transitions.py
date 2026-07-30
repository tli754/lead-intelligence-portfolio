from collections.abc import Awaitable, Callable

from httpx import AsyncClient

CreateCompany = Callable[..., Awaitable[dict]]


class TestProcessingStatusTransitions:
    async def test_valid_transition_succeeds(
        self, client: AsyncClient, create_company: CreateCompany
    ) -> None:
        # Creation now auto-triggers discovery (Task 015 / ADR 0003), so a
        # freshly created company is already "discovered", not "imported" —
        # the next valid edge from there is "crawling".
        created = await create_company(client, "example.com")
        assert created["processing"]["status"] == "discovered"

        response = await client.patch(
            f"/api/companies/{created['companyId']}/processing-status",
            json={"status": "crawling"},
        )

        assert response.status_code == 200
        assert response.json()["processing"]["status"] == "crawling"

    async def test_invalid_transition_is_rejected(
        self, client: AsyncClient, create_company: CreateCompany
    ) -> None:
        created = await create_company(client, "example.com")

        # discovered -> ready skips the rest of the pipeline; not a valid edge.
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
