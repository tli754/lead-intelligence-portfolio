"""Thin orchestration over `EvidenceRepository`.

Independently queryable per the brief's explicit requirement ("evidence
must be first-class and independently queryable", line 52) — not merely a
helper class embedded inside `modules/extraction`. Depends only on the
`EvidenceRepository` interface, never a concrete Mongo class.
"""

from datetime import UTC, datetime

from app.modules.evidence.domain.enums import EvidenceStatus, EvidenceStrength, EvidenceType
from app.modules.evidence.domain.evidence_factory import EvidenceDraft, create_evidence_record
from app.modules.evidence.domain.exceptions import (
    EvidenceCreationFailedError,
    EvidenceNotFoundError,
)
from app.modules.evidence.domain.models import EvidenceRecord
from app.modules.evidence.domain.repository import EvidencePage, EvidenceRepository


class EvidenceService:
    def __init__(self, repository: EvidenceRepository) -> None:
        self._repository = repository

    async def create_evidence(self, draft: EvidenceDraft) -> EvidenceRecord:
        record = create_evidence_record(draft)
        try:
            return await self._repository.save_evidence(record)
        except Exception as error:  # any persistence failure blocks fact acceptance upstream
            raise EvidenceCreationFailedError(reason=str(error)) from error

    async def get_evidence(self, evidence_id: str) -> EvidenceRecord:
        evidence = await self._repository.get_evidence(evidence_id)
        if evidence is None:
            raise EvidenceNotFoundError(evidence_id)
        return evidence

    async def list_evidence_for_fact(self, evidence_ids: list[str]) -> list[EvidenceRecord]:
        return await self._repository.list_evidence_for_fact(evidence_ids)

    async def list_evidence_for_page(self, page_id: str) -> list[EvidenceRecord]:
        return await self._repository.list_evidence_for_page(page_id)

    async def list_evidence(
        self,
        *,
        evidence_type: EvidenceType | None = None,
        strength: EvidenceStrength | None = None,
        status: EvidenceStatus | None = None,
        page_id: str | None = None,
        fact_field_path: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> EvidencePage:
        return await self._repository.list_evidence(
            evidence_type=evidence_type,
            strength=strength,
            status=status,
            page_id=page_id,
            fact_field_path=fact_field_path,
            page=page,
            page_size=page_size,
        )

    async def mark_status(self, evidence_id: str, status: EvidenceStatus) -> EvidenceRecord:
        """Changes only `status` — the one field `EvidenceRecord` allows to
        mutate in place (brief section 2 / AC-20). A genuine content change
        must instead call `create_evidence` again with a new draft."""
        updated = await self._repository.update_evidence_status(evidence_id, status)
        if updated is None:
            raise EvidenceNotFoundError(evidence_id)
        return updated

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)
