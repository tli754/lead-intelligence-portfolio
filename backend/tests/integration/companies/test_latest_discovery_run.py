"""Integration tests for the cross-module addition that lets the
discovery module record a company's latest discovery run:
`MongoCompanyRepository.update_latest_discovery_run_id` and
`CompanyService.update_latest_discovery_run`.

These were added alongside the discovery module (Task 005's "required
follow-up") but had no automated test coverage of their own — an
evaluation flagged the gap. Real MongoDB, same as the rest of this
directory.
"""

from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.modules.companies.application.service import CompanyService
from app.modules.companies.domain.exceptions import CompanyNotFoundError
from app.modules.companies.infrastructure.mongo_repository import MongoCompanyRepository


class TestMongoCompanyRepositoryUpdateLatestDiscoveryRunId:
    async def test_persists_the_discovery_run_id(
        self, client: AsyncClient, test_database: AsyncIOMotorDatabase, create_company
    ) -> None:
        body = await create_company(client, "example.com")
        repository = MongoCompanyRepository(test_database)

        updated = await repository.update_latest_discovery_run_id(
            body["companyId"], "discovery_run_123"
        )

        assert updated is not None
        assert updated.processing.latest_discovery_run_id == "discovery_run_123"

    async def test_persisted_value_is_readable_via_get_by_id(
        self, client: AsyncClient, test_database: AsyncIOMotorDatabase, create_company
    ) -> None:
        body = await create_company(client, "example.com")
        repository = MongoCompanyRepository(test_database)
        await repository.update_latest_discovery_run_id(body["companyId"], "discovery_run_123")

        refetched = await repository.get_by_id(body["companyId"])

        assert refetched is not None
        assert refetched.processing.latest_discovery_run_id == "discovery_run_123"

    async def test_visible_through_the_real_api(
        self, client: AsyncClient, test_database: AsyncIOMotorDatabase, create_company
    ) -> None:
        body = await create_company(client, "example.com")
        repository = MongoCompanyRepository(test_database)
        await repository.update_latest_discovery_run_id(body["companyId"], "discovery_run_123")

        response = await client.get(f"/api/companies/{body['companyId']}")

        assert response.status_code == 200
        assert response.json()["processing"]["latestDiscoveryRunId"] == "discovery_run_123"

    async def test_unknown_company_returns_none(
        self, test_database: AsyncIOMotorDatabase
    ) -> None:
        repository = MongoCompanyRepository(test_database)

        updated = await repository.update_latest_discovery_run_id(
            "no-such-company", "discovery_run_123"
        )

        assert updated is None


class TestCompanyServiceUpdateLatestDiscoveryRun:
    async def test_returns_updated_company(
        self, client: AsyncClient, test_database: AsyncIOMotorDatabase, create_company
    ) -> None:
        body = await create_company(client, "example.com")
        service = CompanyService(MongoCompanyRepository(test_database))

        updated = await service.update_latest_discovery_run(body["companyId"], "discovery_run_456")

        assert updated.processing.latest_discovery_run_id == "discovery_run_456"

    async def test_unknown_company_raises_not_found(
        self, test_database: AsyncIOMotorDatabase
    ) -> None:
        service = CompanyService(MongoCompanyRepository(test_database))

        try:
            await service.update_latest_discovery_run("no-such-company", "discovery_run_456")
            raised = False
        except CompanyNotFoundError:
            raised = True

        assert raised
