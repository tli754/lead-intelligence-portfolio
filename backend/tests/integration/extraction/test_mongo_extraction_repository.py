"""Real-MongoDB tests for `MongoExtractionRepository` (AC-37).

Uses the *inherited* root `backend/tests/conftest.py` fixtures
(`test_database`/`motor_client`) — no edit to that shared root file was
made. The drop-collections cleanup fixture is scoped to this file only,
matching `test_mongo_crawl_repository.py`'s own precedent — the sibling
fakes-based integration tests in this directory must stay free of any
real-MongoDB dependency.
"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.modules.extraction.domain.enums import (
    ExtractionStatus,
    ExtractorExecutionStatus,
    FactSourceType,
    FactStatus,
    VerificationState,
)
from app.modules.extraction.domain.field_catalogue import FieldPath, FieldValueType
from app.modules.extraction.domain.models import (
    ExtractionRun,
    ExtractorExecution,
    FactCandidate,
    FactConflict,
    FactRecord,
)
from app.modules.extraction.infrastructure.mongo_extraction_repository import (
    MongoExtractionRepository,
)

_COLLECTIONS = (
    "extraction_runs",
    "extractor_executions",
    "fact_candidates",
    "facts",
    "fact_conflicts",
)


@pytest.fixture(autouse=True)
async def _clean_extraction_collections(
    test_database: AsyncIOMotorDatabase,
) -> AsyncGenerator[None, None]:
    for name in _COLLECTIONS:
        await test_database[name].drop()
    yield
    for name in _COLLECTIONS:
        await test_database[name].drop()


@pytest.fixture
async def repository(test_database: AsyncIOMotorDatabase) -> MongoExtractionRepository:
    repo = MongoExtractionRepository(test_database)
    await repo.ensure_indexes()
    return repo


def _now() -> datetime:
    return datetime.now(UTC)


def _make_run(*, idempotency_key: str = "key-1") -> ExtractionRun:
    now = _now()
    return ExtractionRun(
        company_id="company-1",
        crawl_run_id="crawl-run-1",
        idempotency_key=idempotency_key,
        created_at=now,
        updated_at=now,
    )


def _make_fact(
    *, field_path: FieldPath = FieldPath.IDENTITY_COMPANY_NAME, status=FactStatus.ACCEPTED
) -> FactRecord:
    now = _now()
    return FactRecord(
        company_id="company-1",
        extraction_run_id="run-1",
        field_path=field_path,
        value="Acme",
        normalized_value="Acme",
        value_type=FieldValueType.STRING,
        status=status,
        verification_state=VerificationState.VERIFIED,
        confidence=80,
        first_observed_at=now,
        last_observed_at=now,
        last_verified_at=now,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.asyncio
async def test_create_and_get_run(repository: MongoExtractionRepository):
    run = await repository.create_run(_make_run())
    fetched = await repository.get_run(run.extraction_run_id)
    assert fetched is not None
    assert fetched.company_id == "company-1"


@pytest.mark.asyncio
async def test_update_run_rejects_stale_document_version(repository: MongoExtractionRepository):
    run = await repository.create_run(_make_run())
    run.status = ExtractionStatus.RUNNING
    updated = await repository.update_run(run)
    assert updated is not None
    assert updated.document_version == 2

    # Retry with the now-stale version 1 — must be rejected.
    stale_update = await repository.update_run(run)
    assert stale_update is None


@pytest.mark.asyncio
async def test_list_runs_returns_all_runs_across_companies(repository: MongoExtractionRepository):
    await repository.create_run(_make_run(idempotency_key="a"))
    other_company_run = _make_run(idempotency_key="b")
    other_company_run.company_id = "company-2"
    await repository.create_run(other_company_run)

    page = await repository.list_runs()

    assert page.total == 2
    assert len(page.items) == 2


@pytest.mark.asyncio
async def test_list_runs_filters_by_status(repository: MongoExtractionRepository):
    completed_run = _make_run(idempotency_key="a")
    completed_run.status = ExtractionStatus.COMPLETED
    await repository.create_run(completed_run)
    failed_run = _make_run(idempotency_key="b")
    failed_run.status = ExtractionStatus.FAILED
    await repository.create_run(failed_run)

    page = await repository.list_runs(status=ExtractionStatus.FAILED)

    assert page.total == 1
    assert page.items[0].status == ExtractionStatus.FAILED


@pytest.mark.asyncio
async def test_list_runs_with_no_matches_returns_empty_page(repository: MongoExtractionRepository):
    completed_run = _make_run()
    completed_run.status = ExtractionStatus.COMPLETED
    await repository.create_run(completed_run)

    page = await repository.list_runs(status=ExtractionStatus.FAILED)

    assert page.total == 0
    assert page.items == []


@pytest.mark.asyncio
async def test_list_runs_sorted_by_created_at_descending(repository: MongoExtractionRepository):
    older = _make_run(idempotency_key="older")
    older.created_at = datetime(2024, 1, 1, tzinfo=UTC)
    newer = _make_run(idempotency_key="newer")
    newer.created_at = datetime(2024, 6, 1, tzinfo=UTC)
    await repository.create_run(older)
    await repository.create_run(newer)

    page = await repository.list_runs()

    assert [run.extraction_run_id for run in page.items] == [
        newer.extraction_run_id,
        older.extraction_run_id,
    ]


@pytest.mark.asyncio
async def test_ensure_indexes_creates_expected_indexes(
    repository: MongoExtractionRepository, test_database
):
    index_names = [index["name"] async for index in test_database["facts"].list_indexes()]
    assert any("company_id_1_field_path_1" in name for name in index_names)


@pytest.mark.asyncio
async def test_save_facts_upserts_current_slot_not_duplicate(repository: MongoExtractionRepository):
    first = _make_fact()
    await repository.save_facts([first])

    second = _make_fact()
    await repository.save_facts([second])

    page = await repository.list_facts_by_company("company-1")
    assert page.total == 1


@pytest.mark.asyncio
async def test_mark_previous_facts_stale_then_save_creates_new_document(
    repository: MongoExtractionRepository,
):
    original = _make_fact()
    await repository.save_facts([original])

    marked = await repository.mark_previous_facts_stale(
        "company-1", FieldPath.IDENTITY_COMPANY_NAME, exclude_fact_ids=[]
    )
    assert marked == 1

    replacement = _make_fact()
    await repository.save_facts([replacement])

    page = await repository.list_facts_by_company("company-1", include_stale=True)
    assert page.total == 2
    statuses = {fact.status for fact in page.items}
    assert FactStatus.STALE in statuses
    assert FactStatus.ACCEPTED in statuses


@pytest.mark.asyncio
async def test_save_and_list_candidates(repository: MongoExtractionRepository):
    now = _now()
    candidate = FactCandidate(
        extraction_run_id="run-1",
        company_id="company-1",
        page_id="page-1",
        field_path=FieldPath.IDENTITY_COMPANY_NAME,
        value="Acme",
        normalized_value="Acme",
        value_type=FieldValueType.STRING,
        source_type=FactSourceType.JSON_LD,
        extractor_id="identity.company_name",
        extractor_version="v1",
        confidence=90,
        verification_state=VerificationState.VERIFIED,
        observed_at=now,
        created_at=now,
    )
    await repository.save_candidates([candidate])
    page = await repository.list_candidates_by_run("run-1")
    assert page.total == 1


@pytest.mark.asyncio
async def test_save_and_get_extractor_execution(repository: MongoExtractionRepository):
    now = _now()
    execution = ExtractorExecution(
        extraction_run_id="run-1",
        page_id="page-1",
        extractor_id="identity.company_name",
        extractor_version="v1",
        status=ExtractorExecutionStatus.SUCCEEDED,
        started_at=now,
        completed_at=now,
    )
    saved = await repository.save_extractor_execution(execution)
    assert saved.extractor_execution_id == execution.extractor_execution_id


@pytest.mark.asyncio
async def test_save_conflicts(repository: MongoExtractionRepository, test_database):
    conflict = FactConflict(
        company_id="company-1",
        extraction_run_id="run-1",
        field_path=FieldPath.IDENTITY_COMPANY_NAME,
        candidate_ids=["c1", "c2"],
        conflict_type="scalar_value_conflict",
        created_at=_now(),
    )
    await repository.save_conflicts([conflict])
    stored = await test_database["fact_conflicts"].find_one({"conflict_id": conflict.conflict_id})
    assert stored is not None


@pytest.mark.asyncio
async def test_get_fact_by_id(repository: MongoExtractionRepository):
    fact = _make_fact()
    await repository.save_facts([fact])
    fetched = await repository.get_fact(fact.fact_id)
    assert fetched is not None
    assert fetched.fact_id == fact.fact_id


@pytest.mark.asyncio
async def test_find_active_or_completed_run(repository: MongoExtractionRepository):
    run = await repository.create_run(_make_run(idempotency_key="unique-key"))
    found = await repository.find_active_or_completed_run("company-1", "unique-key")
    assert found is not None
    assert found.extraction_run_id == run.extraction_run_id


@pytest.mark.asyncio
async def test_mark_run_cancelled(repository: MongoExtractionRepository):
    run = await repository.create_run(_make_run())
    cancelled = await repository.mark_run_cancelled(run.extraction_run_id)
    assert cancelled is not None
    assert cancelled.status == ExtractionStatus.CANCELLED
