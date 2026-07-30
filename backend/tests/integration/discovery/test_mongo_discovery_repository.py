"""Real-MongoDB tests for `MongoDiscoveryRepository`.

Uses the *inherited* root `backend/tests/conftest.py` fixtures
(`test_database`/`motor_client`, available automatically to any test
under `backend/tests/` — no edit to that shared root file was made).

This file did not exist before Task 012: discovery previously had no
real-Mongo repository test at all (unlike crawling's
`test_mongo_crawl_repository.py` and extraction's
`test_mongo_extraction_repository.py`), relying only on the fakes-based
`FakeDiscoveryRepository` in `conftest.py`. Task 012 adds this file so
`list_runs` (and `ensure_indexes`) get equivalent real-Mongo coverage —
a deliberate, documented gap-closing addition, not scope creep.

The drop-collections-before/after fixture is defined directly in *this*
module and marked `autouse` only at module scope, matching
`test_mongo_crawl_repository.py`'s precedent — the sibling fakes-based
integration tests in this same directory
(`test_discovery_service.py`, `test_api_schema_serialization.py`,
`test_processing_status_transitions.py`) must stay free of any real-
MongoDB dependency.
"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.modules.discovery.domain.enums import DiscoveryStatus
from app.modules.discovery.domain.models import DiscoveryRun
from app.modules.discovery.infrastructure.mongo_discovery_repository import (
    MongoDiscoveryRepository,
)


@pytest.fixture(autouse=True)
async def _clean_discovery_collections(
    test_database: AsyncIOMotorDatabase,
) -> AsyncGenerator[None, None]:
    for name in ("discovery_runs", "discoveries"):
        await test_database[name].drop()
    yield
    for name in ("discovery_runs", "discoveries"):
        await test_database[name].drop()


@pytest.fixture
def repository(test_database: AsyncIOMotorDatabase) -> MongoDiscoveryRepository:
    return MongoDiscoveryRepository(test_database)


def _now() -> datetime:
    return datetime.now(UTC)


def _make_run(
    *,
    company_id: str = "company-1",
    status: DiscoveryStatus = DiscoveryStatus.QUEUED,
    created_at: datetime | None = None,
) -> DiscoveryRun:
    now = created_at or _now()
    return DiscoveryRun(
        company_id=company_id,
        root_domain="example.com",
        homepage_url="https://example.com/",
        status=status,
        created_at=now,
        updated_at=now,
    )


class TestEnsureIndexes:
    async def test_indexes_are_created(
        self, repository: MongoDiscoveryRepository, test_database: AsyncIOMotorDatabase
    ) -> None:
        await repository.ensure_indexes()

        run_indexes = await test_database["discovery_runs"].index_information()

        assert "discovery_run_id_1" in run_indexes
        assert "status_1" in run_indexes
        assert "created_at_1" in run_indexes


class TestListRuns:
    async def test_list_runs_returns_all_runs_paginated(
        self, repository: MongoDiscoveryRepository
    ) -> None:
        await repository.create_run(_make_run(company_id="company-1"))
        await repository.create_run(_make_run(company_id="company-2"))

        page = await repository.list_runs()

        assert page.total == 2
        assert len(page.items) == 2

    async def test_list_runs_filters_by_status(
        self, repository: MongoDiscoveryRepository
    ) -> None:
        await repository.create_run(_make_run(status=DiscoveryStatus.COMPLETED))
        await repository.create_run(_make_run(status=DiscoveryStatus.FAILED))

        page = await repository.list_runs(status=DiscoveryStatus.FAILED)

        assert page.total == 1
        assert page.items[0].status == DiscoveryStatus.FAILED

    async def test_list_runs_with_no_matches_returns_empty_page(
        self, repository: MongoDiscoveryRepository
    ) -> None:
        await repository.create_run(_make_run(status=DiscoveryStatus.COMPLETED))

        page = await repository.list_runs(status=DiscoveryStatus.FAILED)

        assert page.total == 0
        assert page.items == []

    async def test_list_runs_sorted_by_created_at_descending(
        self, repository: MongoDiscoveryRepository
    ) -> None:
        older = _make_run(created_at=datetime(2024, 1, 1, tzinfo=UTC))
        newer = _make_run(created_at=datetime(2024, 6, 1, tzinfo=UTC))
        await repository.create_run(older)
        await repository.create_run(newer)

        page = await repository.list_runs()

        assert [run.discovery_run_id for run in page.items] == [
            newer.discovery_run_id,
            older.discovery_run_id,
        ]

    async def test_list_runs_respects_pagination(
        self, repository: MongoDiscoveryRepository
    ) -> None:
        for _ in range(3):
            await repository.create_run(_make_run())

        page = await repository.list_runs(page=2, page_size=2)

        assert page.total == 3
        assert len(page.items) == 1
