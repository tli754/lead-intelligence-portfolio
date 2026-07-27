"""Repository interface for the evidence module.

Pure abstract contract — no MongoDB or FastAPI imports. Implementations
live in `infrastructure/` (`MongoEvidenceRepository`).

`list_evidence_for_fact` deliberately takes an explicit `evidence_ids`
list rather than a `fact_id` — the evidence module has no concept of a
"fact" (that belongs to `modules/extraction`) and must stay independently
buildable/testable (contract resolution #5). A `FactRecord`/`FactCandidate`
already carries its own `evidence_ids: list[str]`, so any caller that
knows which fact it means already has the ids on hand.
"""

from abc import ABC, abstractmethod
from typing import NamedTuple

from app.modules.evidence.domain.enums import EvidenceStatus, EvidenceStrength, EvidenceType
from app.modules.evidence.domain.models import EvidenceRecord


class EvidencePage(NamedTuple):
    items: list[EvidenceRecord]
    total: int


class EvidenceRepository(ABC):
    @abstractmethod
    async def save_evidence(self, evidence: EvidenceRecord) -> EvidenceRecord:
        """Upserts by `evidence_id` — evidence IDs are deterministic
        (`domain/evidence_factory.py`), so re-running extraction against
        unchanged content naturally re-saves the identical record rather
        than duplicating it."""
        ...

    @abstractmethod
    async def get_evidence(self, evidence_id: str) -> EvidenceRecord | None: ...

    @abstractmethod
    async def list_evidence_for_fact(self, evidence_ids: list[str]) -> list[EvidenceRecord]: ...

    @abstractmethod
    async def list_evidence_for_page(self, page_id: str) -> list[EvidenceRecord]: ...

    @abstractmethod
    async def update_evidence_status(
        self, evidence_id: str, status: EvidenceStatus
    ) -> EvidenceRecord | None:
        """The *only* mutating method beyond `save_evidence` — every other
        change creates a new evidence record instead of rewriting an
        existing one (brief section 2's explicit immutability rule)."""
        ...

    @abstractmethod
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
        """A documented addition (contract T9) beyond the brief's literal
        method list — serves the evidence-list query parameters brief
        section 23 describes, scoped by the caller (e.g.
        `GET /api/facts/{fact_id}/evidence` further filters this by the
        fact's own `evidence_ids`)."""
        ...
