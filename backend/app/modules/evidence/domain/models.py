"""Domain models for the evidence module. Pure Pydantic — no FastAPI or MongoDB imports.

`EvidenceRecord.fact_field_path` is deliberately typed `str`, not the
extraction module's `FieldPath` enum — the evidence module must remain
independently buildable/testable without importing anything from
`modules/extraction` (contract resolution #5: extraction depends on
evidence through a port, never the reverse). The extraction module's own
`EvidenceDraft`/`EvidenceGateway` boundary is responsible for always
supplying a real `FieldPath.value` string here.
"""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from app.modules.evidence.domain.enums import EvidenceStatus, EvidenceStrength, EvidenceType


def _as_utc(value: datetime) -> datetime:
    """Treat a naive datetime as UTC rather than rejecting it. Duplicated
    locally, matching every prior module's own `_as_utc` precedent."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class EvidenceLocation(BaseModel):
    selector: str | None = None
    xpath: str | None = None
    json_path: str | None = None
    attribute: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    section_heading: str | None = None
    element_tag: str | None = None


class EvidenceExcerpt(BaseModel):
    text: str
    prefix: str = ""
    suffix: str = ""
    truncated: bool = False
    start_offset: int = 0
    end_offset: int = 0


class EvidenceReference(BaseModel):
    """A small `{evidence_id, field_path}` cross-reference shape.

    Defined minimally per the contract's resolution: `FactRecord.evidence_ids`/
    `FactCandidate.evidence_ids` are already plain `list[str]`, so this type
    is only used where a caller needs the field-path alongside the id.
    """

    evidence_id: str
    field_path: str | None = None


class EvidenceRecord(BaseModel):
    """Immutable except `status`/verification metadata (brief section 2) —
    enforced by `EvidenceRepository.update_evidence_status` being the only
    mutating method on the repository interface; a genuine content change
    creates a *new* evidence record instead of rewriting this one."""

    evidence_id: str = Field(default_factory=lambda: str(uuid4()))
    company_id: str
    extraction_run_id: str
    page_id: str
    fact_field_path: str

    evidence_type: EvidenceType
    status: EvidenceStatus = EvidenceStatus.ACTIVE
    strength: EvidenceStrength

    source_url: str
    normalized_source_url: str
    page_type: str

    extractor_id: str
    extractor_version: str

    location: EvidenceLocation = Field(default_factory=EvidenceLocation)
    excerpt: EvidenceExcerpt
    raw_value: str | None = None
    normalized_value: str | None = None
    content_hash: str

    observed_at: datetime
    last_verified_at: datetime
    created_at: datetime
    updated_at: datetime

    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("observed_at", "last_verified_at", "created_at", "updated_at")
    @classmethod
    def timestamps_are_utc(cls, value: datetime) -> datetime:
        return _as_utc(value)
