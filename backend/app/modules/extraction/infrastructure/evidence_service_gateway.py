"""The real `EvidenceGateway` adapter, wrapping the Evidence module's own
public application service (`EvidenceService`) — never `EvidenceRepository`/
`MongoEvidenceRepository` directly (contract resolution #5).

Obtained via `modules/evidence/api/router.py`'s own public
`get_evidence_service` DI function — the identical "import the other
module's own public application service + its DI function" shape every
other cross-module gateway in this repository uses.
"""

from app.modules.evidence.application.evidence_service import EvidenceService
from app.modules.evidence.domain.evidence_factory import EvidenceDraft
from app.modules.evidence.domain.exceptions import EvidenceNotFoundError
from app.modules.evidence.domain.models import EvidenceRecord
from app.modules.extraction.domain.gateway import EvidenceGateway


class EvidenceServiceExtractionGateway(EvidenceGateway):
    def __init__(self, evidence_service: EvidenceService) -> None:
        self._evidence_service = evidence_service

    async def create_evidence(self, draft: EvidenceDraft) -> EvidenceRecord:
        return await self._evidence_service.create_evidence(draft)

    async def get_evidence(self, evidence_id: str) -> EvidenceRecord | None:
        try:
            return await self._evidence_service.get_evidence(evidence_id)
        except EvidenceNotFoundError:
            return None

    async def list_evidence_for_fact(self, evidence_ids: list[str]) -> list[EvidenceRecord]:
        return await self._evidence_service.list_evidence_for_fact(evidence_ids)
