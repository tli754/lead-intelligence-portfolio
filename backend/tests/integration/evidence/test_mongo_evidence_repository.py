"""Real-MongoDB tests for `MongoEvidenceRepository` (AC-37).

Uses the *inherited* root `backend/tests/conftest.py` fixtures — no edit
to that shared root file was made. Cleanup fixture scoped to this file
only, matching `test_mongo_extraction_repository.py`'s own precedent.
"""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import pytest
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.modules.evidence.domain.enums import EvidenceStatus, EvidenceStrength, EvidenceType
from app.modules.evidence.domain.models import EvidenceExcerpt, EvidenceRecord
from app.modules.evidence.infrastructure.mongo_evidence_repository import MongoEvidenceRepository


@pytest.fixture(autouse=True)
async def _clean_evidence_collection(
    test_database: AsyncIOMotorDatabase,
) -> AsyncGenerator[None, None]:
    await test_database["evidence"].drop()
    yield
    await test_database["evidence"].drop()


@pytest.fixture
async def repository(test_database: AsyncIOMotorDatabase) -> MongoEvidenceRepository:
    repo = MongoEvidenceRepository(test_database)
    await repo.ensure_indexes()
    return repo


def _now() -> datetime:
    return datetime.now(UTC)


def _make_evidence(**overrides: Any) -> EvidenceRecord:
    now = _now()
    defaults: dict[str, Any] = dict(
        company_id="company-1",
        extraction_run_id="run-1",
        page_id="page-1",
        fact_field_path="identity.company_name",
        evidence_type=EvidenceType.JSON_LD,
        strength=EvidenceStrength.AUTHORITATIVE,
        source_url="https://example.com/",
        normalized_source_url="https://example.com/",
        page_type="homepage",
        extractor_id="identity.company_name",
        extractor_version="v1",
        excerpt=EvidenceExcerpt(text="Acme Corporation"),
        content_hash="hash-1",
        observed_at=now,
        last_verified_at=now,
        created_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    return EvidenceRecord(**defaults)


@pytest.mark.asyncio
async def test_save_and_get_evidence(repository: MongoEvidenceRepository):
    evidence = _make_evidence()
    await repository.save_evidence(evidence)
    fetched = await repository.get_evidence(evidence.evidence_id)
    assert fetched is not None
    assert fetched.company_id == "company-1"


@pytest.mark.asyncio
async def test_save_evidence_is_idempotent_by_id(repository: MongoEvidenceRepository):
    evidence = _make_evidence()
    await repository.save_evidence(evidence)
    await repository.save_evidence(evidence)
    all_for_page = await repository.list_evidence_for_page(evidence.page_id)
    assert len(all_for_page) == 1


@pytest.mark.asyncio
async def test_list_evidence_for_fact(repository: MongoEvidenceRepository):
    e1 = _make_evidence(fact_field_path="identity.company_name")
    e2 = _make_evidence(fact_field_path="business.wholesale", page_id="page-2")
    await repository.save_evidence(e1)
    await repository.save_evidence(e2)

    results = await repository.list_evidence_for_fact([e1.evidence_id, e2.evidence_id])
    assert {r.evidence_id for r in results} == {e1.evidence_id, e2.evidence_id}


@pytest.mark.asyncio
async def test_update_evidence_status(repository: MongoEvidenceRepository):
    evidence = _make_evidence()
    await repository.save_evidence(evidence)
    updated = await repository.update_evidence_status(evidence.evidence_id, EvidenceStatus.STALE)
    assert updated is not None
    assert updated.status == EvidenceStatus.STALE


@pytest.mark.asyncio
async def test_content_change_creates_new_evidence_not_rewrite(repository: MongoEvidenceRepository):
    """A genuine content change must produce a *new* evidence record
    (deterministic id derived from different content), never overwrite
    the original one in place (AC-20's integration half)."""
    original = _make_evidence(content_hash="hash-original")
    await repository.save_evidence(original)

    changed = _make_evidence(content_hash="hash-changed", evidence_id="different-evidence-id")
    await repository.save_evidence(changed)

    all_for_page = await repository.list_evidence_for_page(original.page_id)
    assert len(all_for_page) == 2
    original_still_present = await repository.get_evidence(original.evidence_id)
    assert original_still_present is not None
    assert original_still_present.content_hash == "hash-original"


@pytest.mark.asyncio
async def test_list_evidence_with_filters(repository: MongoEvidenceRepository):
    active = _make_evidence(status=EvidenceStatus.ACTIVE)
    stale = _make_evidence(status=EvidenceStatus.STALE, page_id="page-2")
    await repository.save_evidence(active)
    await repository.save_evidence(stale)

    result = await repository.list_evidence(status=EvidenceStatus.ACTIVE)
    assert [item.evidence_id for item in result.items] == [active.evidence_id]


@pytest.mark.asyncio
async def test_ensure_indexes_creates_unique_evidence_id_index(
    repository: MongoEvidenceRepository, test_database
):
    index_names = [index["name"] async for index in test_database["evidence"].list_indexes()]
    assert any("evidence_id" in name for name in index_names)
