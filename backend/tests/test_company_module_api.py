"""Full API integration tests for the companies module.

Mirrors `test_company_import.py`'s style: hits the real HTTP app (via the
shared `client` fixture in `conftest.py`), backed by a real MongoDB test
database.
"""

from httpx import AsyncClient


async def _create_company(client: AsyncClient, domain: str = "example.com") -> dict:
    response = await client.post(
        "/api/companies",
        json={
            "domain": domain,
            "company_name": "Example",
            "platform": "shopify",
            "country": "US",
            "city": "NYC",
        },
    )
    assert response.status_code == 201
    return response.json()


class TestCreateCompany:
    async def test_create_company(self, client: AsyncClient) -> None:
        body = await _create_company(client)
        assert body["domain"] == "example.com"
        assert body["normalized_domain"] == "example.com"
        assert body["identity"]["company_name"] == "Example"
        assert body["processing"]["status"] == "imported"
        assert body["workflow"]["manual_status"] == "unreviewed"

    async def test_duplicate_domain_rejected(self, client: AsyncClient) -> None:
        await _create_company(client, domain="example.com")
        response = await client.post("/api/companies", json={"domain": "https://www.example.com"})
        assert response.status_code == 409

    async def test_empty_domain_rejected(self, client: AsyncClient) -> None:
        response = await client.post("/api/companies", json={"domain": ""})
        assert response.status_code == 422


class TestRetrieveCompany:
    async def test_get_by_id(self, client: AsyncClient) -> None:
        created = await _create_company(client)
        response = await client.get(f"/api/companies/{created['company_id']}")
        assert response.status_code == 200
        assert response.json()["company_id"] == created["company_id"]

    async def test_get_missing_returns_404(self, client: AsyncClient) -> None:
        response = await client.get("/api/companies/does-not-exist")
        assert response.status_code == 404

    async def test_list_companies(self, client: AsyncClient) -> None:
        await _create_company(client, domain="example.com")
        await _create_company(client, domain="other.com")
        response = await client.get("/api/companies")
        assert response.status_code == 200
        assert len(response.json()) == 2


class TestProcessingStatus:
    async def test_update_processing_status(self, client: AsyncClient) -> None:
        created = await _create_company(client)
        response = await client.patch(
            f"/api/companies/{created['company_id']}/processing-status",
            json={"status": "crawling"},
        )
        assert response.status_code == 200
        assert response.json()["processing"]["status"] == "crawling"

    async def test_update_processing_status_missing_returns_404(self, client: AsyncClient) -> None:
        response = await client.patch(
            "/api/companies/does-not-exist/processing-status", json={"status": "crawling"}
        )
        assert response.status_code == 404

    async def test_invalid_processing_status_rejected(self, client: AsyncClient) -> None:
        created = await _create_company(client)
        response = await client.patch(
            f"/api/companies/{created['company_id']}/processing-status",
            json={"status": "not-a-status"},
        )
        assert response.status_code == 422


class TestWorkflowStatus:
    async def test_update_workflow_status(self, client: AsyncClient) -> None:
        created = await _create_company(client)
        response = await client.patch(
            f"/api/companies/{created['company_id']}/workflow-status",
            json={"status": "shortlisted"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["workflow"]["manual_status"] == "shortlisted"
        assert body["workflow"]["shortlisted"] is True

    async def test_update_workflow_status_missing_returns_404(self, client: AsyncClient) -> None:
        response = await client.patch(
            "/api/companies/does-not-exist/workflow-status", json={"status": "shortlisted"}
        )
        assert response.status_code == 404

    async def test_invalid_workflow_status_rejected(self, client: AsyncClient) -> None:
        created = await _create_company(client)
        response = await client.patch(
            f"/api/companies/{created['company_id']}/workflow-status",
            json={"status": "not-a-status"},
        )
        assert response.status_code == 422
