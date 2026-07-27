"""Integration tests for MongoCompanyRepository against a real MongoDB instance.

Uses the shared `test_database` fixture from `backend/tests/conftest.py`
(a dedicated test database, cleaned by the autouse
`clean_companies_pipeline_collection` fixture).
"""

from datetime import UTC, datetime

import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.modules.companies.domain.enums import ProcessingStatus, WorkflowStatus
from app.modules.companies.domain.exceptions import DuplicateCompanyError
from app.modules.companies.domain.models import Company, CompanyIdentity, CompanyTimestamps
from app.modules.companies.infrastructure.mongo_repository import MongoCompanyRepository


def _make_company(domain: str = "example.com", **identity_kwargs: str | None) -> Company:
    now = datetime.now(UTC)
    return Company(
        domain=domain,
        normalized_domain=domain,
        identity=CompanyIdentity(**identity_kwargs),
        timestamps=CompanyTimestamps(created_at=now, updated_at=now),
    )


@pytest.fixture
async def repository(test_database: AsyncIOMotorDatabase) -> MongoCompanyRepository:
    repo = MongoCompanyRepository(test_database)
    await repo.ensure_indexes()
    return repo


class TestCreateAndFetch:
    async def test_create_then_get_by_id(self, repository: MongoCompanyRepository) -> None:
        created = await repository.create(_make_company())
        fetched = await repository.get_by_id(created.company_id)
        assert fetched is not None
        assert fetched.normalized_domain == "example.com"

    async def test_get_by_domain(self, repository: MongoCompanyRepository) -> None:
        await repository.create(_make_company("example.com"))
        fetched = await repository.get_by_domain("example.com")
        assert fetched is not None
        assert fetched.domain == "example.com"

    async def test_get_by_id_missing_returns_none(self, repository: MongoCompanyRepository) -> None:
        assert await repository.get_by_id("missing") is None

    async def test_get_by_domain_missing_returns_none(
        self, repository: MongoCompanyRepository
    ) -> None:
        assert await repository.get_by_domain("missing.com") is None

    async def test_exists(self, repository: MongoCompanyRepository) -> None:
        assert await repository.exists("example.com") is False
        await repository.create(_make_company("example.com"))
        assert await repository.exists("example.com") is True

    async def test_duplicate_normalized_domain_rejected(
        self, repository: MongoCompanyRepository
    ) -> None:
        await repository.create(_make_company("example.com"))
        with pytest.raises(DuplicateCompanyError):
            await repository.create(_make_company("example.com"))


class TestStatusUpdates:
    async def test_update_processing_status(self, repository: MongoCompanyRepository) -> None:
        created = await repository.create(_make_company())
        updated = await repository.update_processing_status(
            created.company_id, ProcessingStatus.CRAWLING
        )
        assert updated is not None
        assert updated.processing.status == ProcessingStatus.CRAWLING

    async def test_update_processing_status_missing_returns_none(
        self, repository: MongoCompanyRepository
    ) -> None:
        result = await repository.update_processing_status("missing", ProcessingStatus.CRAWLING)
        assert result is None

    async def test_update_workflow_status(self, repository: MongoCompanyRepository) -> None:
        created = await repository.create(_make_company())
        updated = await repository.update_workflow_status(
            created.company_id, WorkflowStatus.SHORTLISTED
        )
        assert updated is not None
        assert updated.workflow.manual_status == WorkflowStatus.SHORTLISTED
        assert updated.workflow.shortlisted is True

    async def test_update_workflow_status_missing_returns_none(
        self, repository: MongoCompanyRepository
    ) -> None:
        assert (
            await repository.update_workflow_status("missing", WorkflowStatus.SHORTLISTED) is None
        )


class TestList:
    async def test_filters_by_platform(self, repository: MongoCompanyRepository) -> None:
        await repository.create(_make_company("shopify-store.com", platform="shopify"))
        await repository.create(_make_company("other-store.com", platform="woocommerce"))

        results = await repository.list(platform="shopify")
        assert [c.normalized_domain for c in results] == ["shopify-store.com"]

    async def test_respects_skip_and_limit(self, repository: MongoCompanyRepository) -> None:
        for i in range(3):
            await repository.create(_make_company(f"store-{i}.com"))

        results = await repository.list(skip=1, limit=1)
        assert len(results) == 1
