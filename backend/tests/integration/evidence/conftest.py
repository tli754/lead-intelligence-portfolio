"""Shared fixtures for evidence-module integration tests — no real MongoDB."""

from datetime import UTC, datetime
from typing import Any

import pytest

from app.modules.evidence.domain.enums import EvidenceStatus, EvidenceStrength, EvidenceType
from app.modules.evidence.domain.models import EvidenceExcerpt, EvidenceRecord
from app.modules.evidence.domain.repository import EvidencePage, EvidenceRepository


class FakeEvidenceRepository(EvidenceRepository):
    def __init__(self) -> None:
        self.records: dict[str, EvidenceRecord] = {}

    async def save_evidence(self, evidence: EvidenceRecord) -> EvidenceRecord:
        self.records[evidence.evidence_id] = evidence
        return evidence

    async def get_evidence(self, evidence_id: str) -> EvidenceRecord | None:
        return self.records.get(evidence_id)

    async def list_evidence_for_fact(self, evidence_ids: list[str]) -> list[EvidenceRecord]:
        return [self.records[eid] for eid in evidence_ids if eid in self.records]

    async def list_evidence_for_page(self, page_id: str) -> list[EvidenceRecord]:
        return [record for record in self.records.values() if record.page_id == page_id]

    async def update_evidence_status(
        self, evidence_id: str, status: EvidenceStatus
    ) -> EvidenceRecord | None:
        record = self.records.get(evidence_id)
        if record is None:
            return None
        updated = record.model_copy(update={"status": status})
        self.records[evidence_id] = updated
        return updated

    async def list_evidence(
        self,
        *,
        evidence_type=None,
        strength=None,
        status=None,
        page_id=None,
        fact_field_path=None,
        page: int = 1,
        page_size: int = 20,
    ) -> EvidencePage:
        items = list(self.records.values())
        if evidence_type is not None:
            items = [i for i in items if i.evidence_type == evidence_type]
        if strength is not None:
            items = [i for i in items if i.strength == strength]
        if status is not None:
            items = [i for i in items if i.status == status]
        if page_id is not None:
            items = [i for i in items if i.page_id == page_id]
        if fact_field_path is not None:
            items = [i for i in items if i.fact_field_path == fact_field_path]
        start = (page - 1) * page_size
        return EvidencePage(items=items[start : start + page_size], total=len(items))


def make_evidence_record(**overrides: Any) -> EvidenceRecord:
    now = datetime(2026, 7, 26, tzinfo=UTC)
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


@pytest.fixture
def evidence_repository() -> FakeEvidenceRepository:
    return FakeEvidenceRepository()
