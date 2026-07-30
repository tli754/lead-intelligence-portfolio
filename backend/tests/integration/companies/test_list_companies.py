from collections.abc import Awaitable, Callable

from httpx import AsyncClient

CreateCompany = Callable[..., Awaitable[dict]]


class TestListCompaniesEnvelope:
    async def test_list_response_shape(
        self, client: AsyncClient, create_company: CreateCompany
    ) -> None:
        await create_company(client, "example.com", company_name="Example", platform="Shopify")

        response = await client.get("/api/companies")

        assert response.status_code == 200
        body = response.json()
        assert set(body.keys()) == {"data", "pagination"}
        assert body["pagination"] == {"page": 1, "pageSize": 20, "total": 1}
        assert len(body["data"]) == 1

        item = body["data"][0]
        assert set(item.keys()) == {
            "companyId",
            "companyName",
            "domain",
            "platform",
            "country",
            "city",
            "opportunityScore",
            "confidence",
            "mainReason",
            "processingStatus",
            "workflowStatus",
            "updatedAt",
        }
        assert item["companyName"] == "Example"
        assert item["opportunityScore"] is None
        assert item["confidence"] is None
        assert item["mainReason"] is None
        assert item["updatedAt"]

    async def test_filters_by_platform(
        self, client: AsyncClient, create_company: CreateCompany
    ) -> None:
        await create_company(client, "shopify-store.com", platform="Shopify")
        await create_company(client, "other-store.com", platform="WooCommerce")

        response = await client.get("/api/companies", params={"platform": "Shopify"})

        body = response.json()
        assert body["pagination"]["total"] == 1
        assert body["data"][0]["domain"] == "shopify-store.com"

    async def test_filters_by_processing_status(
        self, client: AsyncClient, create_company: CreateCompany
    ) -> None:
        await create_company(client, "example.com")

        response = await client.get("/api/companies", params={"processingStatus": "failed"})

        assert response.json()["pagination"]["total"] == 0


class TestPagination:
    async def test_pagination_math(
        self, client: AsyncClient, create_company: CreateCompany
    ) -> None:
        for i in range(5):
            await create_company(client, f"store-{i}.com")

        response = await client.get("/api/companies", params={"page": 2, "pageSize": 2})

        assert response.status_code == 200
        body = response.json()
        assert body["pagination"] == {"page": 2, "pageSize": 2, "total": 5}
        assert len(body["data"]) == 2

    async def test_last_page_may_be_partial(
        self, client: AsyncClient, create_company: CreateCompany
    ) -> None:
        for i in range(5):
            await create_company(client, f"store-{i}.com")

        response = await client.get("/api/companies", params={"page": 3, "pageSize": 2})

        body = response.json()
        assert body["pagination"]["total"] == 5
        assert len(body["data"]) == 1
