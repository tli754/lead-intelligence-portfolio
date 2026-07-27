"""Integration tests for `EvidenceService` against a `FakeEvidenceRepository`
(AC-20's integration half) — no real MongoDB."""

from datetime import UTC, datetime
from typing import Any

import pytest

from app.modules.evidence.application.evidence_service import EvidenceService
from app.modules.evidence.domain.enums import EvidenceStatus
from app.modules.evidence.domain.evidence_factory import EvidenceDraft
from app.modules.evidence.domain.exceptions import EvidenceNotFoundError
from app.modules.evidence.domain.models import EvidenceLocation

from .conftest import FakeEvidenceRepository, make_evidence_record


def _draft(**overrides: Any) -> EvidenceDraft:
    defaults: dict[str, Any] = dict(
        company_id="company-1",
        extraction_run_id="run-1",
        page_id="page-1",
        fact_field_path="identity.company_name",
        evidence_type="json_ld",
        strength="authoritative",
        source_url="https://example.com/about",
        page_type="about",
        extractor_id="identity.company_name",
        extractor_version="v1",
        location=EvidenceLocation(json_path="$.name"),
        source_fragment="Acme Corporation",
        raw_value="Acme Corporation",
        normalized_value="acme corporation",
        observed_at=datetime(2026, 7, 26, tzinfo=UTC),
    )
    defaults.update(overrides)
    return EvidenceDraft(**defaults)


@pytest.mark.asyncio
async def test_create_and_get_evidence(evidence_repository: FakeEvidenceRepository):
    service = EvidenceService(evidence_repository)
    created = await service.create_evidence(_draft())
    fetched = await service.get_evidence(created.evidence_id)
    assert fetched.evidence_id == created.evidence_id


@pytest.mark.asyncio
async def test_get_missing_evidence_raises(evidence_repository: FakeEvidenceRepository):
    service = EvidenceService(evidence_repository)
    with pytest.raises(EvidenceNotFoundError):
        await service.get_evidence("missing-id")


@pytest.mark.asyncio
async def test_list_evidence_for_fact(evidence_repository: FakeEvidenceRepository):
    record = make_evidence_record()
    await evidence_repository.save_evidence(record)
    service = EvidenceService(evidence_repository)
    results = await service.list_evidence_for_fact([record.evidence_id])
    assert results == [record]


@pytest.mark.asyncio
async def test_mark_status_updates_only_status(evidence_repository: FakeEvidenceRepository):
    record = make_evidence_record()
    await evidence_repository.save_evidence(record)
    service = EvidenceService(evidence_repository)
    updated = await service.mark_status(record.evidence_id, EvidenceStatus.SUPERSEDED)
    assert updated.status == EvidenceStatus.SUPERSEDED
    assert updated.excerpt == record.excerpt
    assert updated.content_hash == record.content_hash


@pytest.mark.asyncio
async def test_mark_status_missing_evidence_raises(evidence_repository: FakeEvidenceRepository):
    service = EvidenceService(evidence_repository)
    with pytest.raises(EvidenceNotFoundError):
        await service.mark_status("missing-id", EvidenceStatus.STALE)


@pytest.mark.asyncio
async def test_list_evidence_with_filters(evidence_repository: FakeEvidenceRepository):
    record = make_evidence_record()
    await evidence_repository.save_evidence(record)
    service = EvidenceService(evidence_repository)
    page = await service.list_evidence(page_id="page-1")
    assert page.total == 1
