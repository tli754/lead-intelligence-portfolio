"""Real-MongoDB tests for `MongoCrawlRepository` (AC-36).

Uses the *inherited* root `backend/tests/conftest.py` fixtures
(`test_database`/`motor_client`, available automatically to any test
under `backend/tests/` — no edit to that shared root file was made).

The drop-collections-before/after fixture is defined directly in *this*
module (not the shared `backend/tests/integration/crawling/conftest.py`)
and deliberately marked `autouse` only at module scope — the sibling
fakes-based integration tests in this same directory
(`test_website_crawl_service.py`, `test_api_schema_serialization.py`)
must stay free of any real-MongoDB dependency (matching
`modules/imports`'s precedent), so the Mongo-specific cleanup fixture is
scoped to this file only rather than promoted to the shared
`conftest.py`, where an autouse fixture would apply to every test in the
directory regardless of file.
"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.modules.crawling.domain.enums import CrawlStatus, PageFetchStatus
from app.modules.crawling.domain.models import CrawledPage, CrawlRun, CrawlSummary, CrawlTarget
from app.modules.crawling.infrastructure.mongo_crawl_repository import MongoCrawlRepository
from app.modules.discovery.domain.enums import DiscoveryPriority, PageType


@pytest.fixture(autouse=True)
async def _clean_crawling_collections(
    test_database: AsyncIOMotorDatabase,
) -> AsyncGenerator[None, None]:
    for name in ("crawl_runs", "crawl_targets", "pages"):
        await test_database[name].drop()
    yield
    for name in ("crawl_runs", "crawl_targets", "pages"):
        await test_database[name].drop()


@pytest.fixture
def repository(test_database: AsyncIOMotorDatabase) -> MongoCrawlRepository:
    return MongoCrawlRepository(test_database)


def _now() -> datetime:
    return datetime.now(UTC)


def _make_run(
    *,
    idempotency_key: str = "key-1",
    status: CrawlStatus = CrawlStatus.QUEUED,
) -> CrawlRun:
    now = _now()
    return CrawlRun(
        company_id="company-1",
        discovery_run_id="discovery-run-1",
        status=status,
        created_at=now,
        updated_at=now,
        idempotency_key=idempotency_key,
        summary=CrawlSummary(),
    )


def _make_target(
    *,
    normalized_url: str = "https://example.com/",
    status: PageFetchStatus = PageFetchStatus.QUEUED,
) -> CrawlTarget:
    now = _now()
    return CrawlTarget(
        crawl_run_id="run-1",
        company_id="company-1",
        discovery_run_id="discovery-run-1",
        url=normalized_url,
        normalized_url=normalized_url,
        page_type=PageType.HOMEPAGE,
        priority=DiscoveryPriority.PRIORITY_1,
        status=status,
        created_at=now,
        updated_at=now,
    )


def _make_page(
    *,
    crawl_run_id: str = "run-1",
    normalized_url: str = "https://example.com/",
    fetch_status: PageFetchStatus = PageFetchStatus.FETCHED,
    fetched_at: datetime | None = None,
) -> CrawledPage:
    now = _now()
    return CrawledPage(
        crawl_run_id=crawl_run_id,
        company_id="company-1",
        discovery_run_id="discovery-run-1",
        original_url=normalized_url,
        normalized_url=normalized_url,
        page_type=PageType.HOMEPAGE,
        priority=DiscoveryPriority.PRIORITY_1,
        fetch_status=fetch_status,
        created_at=now,
        updated_at=now,
        fetched_at=fetched_at or now,
    )


class TestEnsureIndexes:
    async def test_indexes_are_created(
        self, repository: MongoCrawlRepository, test_database: AsyncIOMotorDatabase
    ) -> None:
        await repository.ensure_indexes()

        run_indexes = await test_database["crawl_runs"].index_information()
        target_indexes = await test_database["crawl_targets"].index_information()
        page_indexes = await test_database["pages"].index_information()

        assert "crawl_run_id_1" in run_indexes
        assert "crawl_target_id_1" in target_indexes
        assert "crawl_run_id_1_normalized_url_1" in target_indexes
        assert target_indexes["crawl_run_id_1_normalized_url_1"]["unique"] is True
        assert "page_id_1" in page_indexes
        assert "crawl_run_id_1_normalized_url_1" in page_indexes
        assert page_indexes["crawl_run_id_1_normalized_url_1"]["unique"] is True


class TestRunCrud:
    async def test_create_and_get_run(self, repository: MongoCrawlRepository) -> None:
        run = _make_run()
        await repository.create_run(run)

        fetched = await repository.get_run(run.crawl_run_id)
        assert fetched is not None
        assert fetched.crawl_run_id == run.crawl_run_id
        assert fetched.status == CrawlStatus.QUEUED

    async def test_update_run_succeeds_with_current_version(
        self, repository: MongoCrawlRepository
    ) -> None:
        run = _make_run()
        await repository.create_run(run)

        run.status = CrawlStatus.RUNNING
        updated = await repository.update_run(run)

        assert updated is not None
        assert updated.status == CrawlStatus.RUNNING
        assert updated.document_version == 2

    async def test_stale_document_version_update_is_rejected(
        self, repository: MongoCrawlRepository
    ) -> None:
        run = _make_run()
        await repository.create_run(run)

        run.status = CrawlStatus.RUNNING
        await repository.update_run(run)  # version now 2 in the database

        # Attempting another update using the *original* (now stale) version.
        stale_update = run.model_copy(update={"status": CrawlStatus.FAILED})
        result = await repository.update_run(stale_update)

        assert result is None
        unchanged = await repository.get_run(run.crawl_run_id)
        assert unchanged is not None
        assert unchanged.status == CrawlStatus.RUNNING  # the stale write never applied
        assert unchanged.document_version == 2

    async def test_find_active_run(self, repository: MongoCrawlRepository) -> None:
        run = _make_run(idempotency_key="key-active")
        await repository.create_run(run)

        found = await repository.find_active_run("company-1", "key-active")
        assert found is not None
        assert found.crawl_run_id == run.crawl_run_id

    async def test_find_active_run_ignores_completed_runs(
        self, repository: MongoCrawlRepository
    ) -> None:
        run = _make_run(idempotency_key="key-done", status=CrawlStatus.COMPLETED)
        await repository.create_run(run)

        found = await repository.find_active_run("company-1", "key-done")
        assert found is None

    async def test_mark_run_cancelled(self, repository: MongoCrawlRepository) -> None:
        run = _make_run()
        await repository.create_run(run)

        cancelled = await repository.mark_run_cancelled(run.crawl_run_id)
        assert cancelled is not None
        assert cancelled.status == CrawlStatus.CANCELLED

    async def test_list_runs_by_company(self, repository: MongoCrawlRepository) -> None:
        await repository.create_run(_make_run(idempotency_key="a"))
        await repository.create_run(_make_run(idempotency_key="b"))

        page = await repository.list_runs_by_company("company-1")
        assert page.total == 2
        assert len(page.items) == 2


class TestTargetCrud:
    async def test_save_and_find_target(self, repository: MongoCrawlRepository) -> None:
        target = _make_target()
        await repository.save_target(target)

        found = await repository.find_target_by_url("run-1", "https://example.com/")
        assert found is not None
        assert found.crawl_target_id == target.crawl_target_id

    async def test_save_target_upserts_without_duplicating(
        self, repository: MongoCrawlRepository, test_database: AsyncIOMotorDatabase
    ) -> None:
        target = _make_target()
        await repository.save_target(target)
        await repository.save_target(target.model_copy(update={"status": PageFetchStatus.FETCHED}))

        count = await test_database["crawl_targets"].count_documents(
            {"crawl_run_id": "run-1", "normalized_url": "https://example.com/"}
        )
        assert count == 1

    async def test_update_target_stale_version_rejected(
        self, repository: MongoCrawlRepository
    ) -> None:
        target = _make_target()
        await repository.save_target(target)

        target.status = PageFetchStatus.FETCHED
        updated = await repository.update_target(target)
        assert updated is not None
        assert updated.document_version == 2

        stale = target.model_copy(update={"status": PageFetchStatus.FAILED})
        result = await repository.update_target(stale)
        assert result is None

    async def test_list_targets_by_run_filters_by_status(
        self, repository: MongoCrawlRepository
    ) -> None:
        await repository.save_target(_make_target(normalized_url="https://example.com/a"))
        await repository.save_target(
            _make_target(normalized_url="https://example.com/b", status=PageFetchStatus.FAILED)
        )

        page = await repository.list_targets_by_run("run-1", status=PageFetchStatus.FAILED)
        assert page.total == 1
        assert page.items[0].normalized_url == "https://example.com/b"


class TestPageCrud:
    async def test_save_and_get_page(self, repository: MongoCrawlRepository) -> None:
        page = _make_page()
        await repository.save_page(page)

        found = await repository.get_page(page.page_id)
        assert found is not None
        assert found.page_id == page.page_id

    async def test_save_page_upserts_by_run_and_normalized_url(
        self, repository: MongoCrawlRepository, test_database: AsyncIOMotorDatabase
    ) -> None:
        page = _make_page()
        await repository.save_page(page)
        await repository.save_page(page.model_copy(update={"fetch_status": PageFetchStatus.FAILED}))

        count = await test_database["pages"].count_documents(
            {"crawl_run_id": "run-1", "normalized_url": "https://example.com/"}
        )
        assert count == 1

    async def test_get_latest_page_by_normalized_url(
        self, repository: MongoCrawlRepository
    ) -> None:
        older = _make_page(
            crawl_run_id="run-old",
            fetched_at=datetime(2024, 1, 1, tzinfo=UTC),
        )
        newer = _make_page(
            crawl_run_id="run-new",
            fetched_at=datetime(2024, 6, 1, tzinfo=UTC),
        )
        await repository.save_page(older)
        await repository.save_page(newer)

        latest = await repository.get_latest_page_by_normalized_url(
            "company-1", "https://example.com/"
        )
        assert latest is not None
        assert latest.crawl_run_id == "run-new"

    async def test_list_pages_by_run_excludes_failed_by_default(
        self, repository: MongoCrawlRepository
    ) -> None:
        await repository.save_page(_make_page(normalized_url="https://example.com/ok"))
        await repository.save_page(
            _make_page(
                normalized_url="https://example.com/bad", fetch_status=PageFetchStatus.FAILED
            )
        )

        default_page = await repository.list_pages_by_run("run-1")
        assert default_page.total == 1

        with_failed = await repository.list_pages_by_run("run-1", include_failed=True)
        assert with_failed.total == 2
