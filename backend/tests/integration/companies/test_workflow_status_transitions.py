from collections.abc import Awaitable, Callable

from httpx import AsyncClient

CreateCompany = Callable[..., Awaitable[dict]]


class TestWorkflowStatusTransitions:
    async def test_valid_transition_succeeds_and_sets_shortlisted_flag(
        self, client: AsyncClient, create_company: CreateCompany
    ) -> None:
        created = await create_company(client, "example.com")
        assert created["workflow"]["manualStatus"] == "unreviewed"

        response = await client.patch(
            f"/api/companies/{created['companyId']}/workflow-status",
            json={"status": "shortlisted"},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["workflow"]["manualStatus"] == "shortlisted"
        assert body["workflow"]["shortlisted"] is True

    async def test_invalid_transition_is_rejected(
        self, client: AsyncClient, create_company: CreateCompany
    ) -> None:
        created = await create_company(client, "example.com")

        # unreviewed -> customer skips the whole review lifecycle.
        response = await client.patch(
            f"/api/companies/{created['companyId']}/workflow-status",
            json={"status": "customer"},
        )

        assert response.status_code == 409

    async def test_missing_company_returns_404(self, client: AsyncClient) -> None:
        response = await client.patch(
            "/api/companies/does-not-exist/workflow-status",
            json={"status": "shortlisted"},
        )
        assert response.status_code == 404

    async def test_invalid_status_value_returns_422(
        self, client: AsyncClient, create_company: CreateCompany
    ) -> None:
        created = await create_company(client, "example.com")

        response = await client.patch(
            f"/api/companies/{created['companyId']}/workflow-status",
            json={"status": "not-a-real-status"},
        )

        assert response.status_code == 422
