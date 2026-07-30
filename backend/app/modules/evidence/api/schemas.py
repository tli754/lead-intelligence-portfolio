"""Request/response DTOs for the evidence-module HTTP API. All JSON is camelCase.

A small local `CamelCaseModel` base, not imported from any other module —
matching `modules/crawling/api/schemas.py`'s exact precedent (duplicated,
not cross-imported).
"""

from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.modules.evidence.domain.models import EvidenceRecord


class CamelCaseModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class EvidenceLocationResponse(CamelCaseModel):
    selector: str | None
    xpath: str | None
    json_path: str | None
    attribute: str | None
    line_start: int | None
    line_end: int | None
    section_heading: str | None
    element_tag: str | None


class EvidenceExcerptResponse(CamelCaseModel):
    text: str
    prefix: str
    suffix: str
    truncated: bool
    start_offset: int
    end_offset: int


class EvidenceResponse(CamelCaseModel):
    evidence_id: str
    company_id: str
    extraction_run_id: str
    page_id: str
    fact_field_path: str
    evidence_type: str
    status: str
    strength: str
    source_url: str
    normalized_source_url: str
    page_type: str
    extractor_id: str
    extractor_version: str
    location: EvidenceLocationResponse
    excerpt: EvidenceExcerptResponse
    raw_value: str | None
    normalized_value: str | None
    content_hash: str
    observed_at: str
    last_verified_at: str
    created_at: str
    updated_at: str
    metadata: dict[str, Any]


class EvidenceEnvelope(CamelCaseModel):
    data: EvidenceResponse


class PaginationMeta(CamelCaseModel):
    page: int
    page_size: int
    total: int


class EvidenceListResponse(CamelCaseModel):
    data: list[EvidenceResponse]
    pagination: PaginationMeta


def evidence_to_response(evidence: EvidenceRecord) -> EvidenceResponse:
    return EvidenceResponse(
        evidence_id=evidence.evidence_id,
        company_id=evidence.company_id,
        extraction_run_id=evidence.extraction_run_id,
        page_id=evidence.page_id,
        fact_field_path=evidence.fact_field_path,
        evidence_type=evidence.evidence_type.value,
        status=evidence.status.value,
        strength=evidence.strength.value,
        source_url=evidence.source_url,
        normalized_source_url=evidence.normalized_source_url,
        page_type=evidence.page_type,
        extractor_id=evidence.extractor_id,
        extractor_version=evidence.extractor_version,
        location=EvidenceLocationResponse(**evidence.location.model_dump()),
        excerpt=EvidenceExcerptResponse(**evidence.excerpt.model_dump()),
        raw_value=evidence.raw_value,
        normalized_value=evidence.normalized_value,
        content_hash=evidence.content_hash,
        observed_at=evidence.observed_at.isoformat(),
        last_verified_at=evidence.last_verified_at.isoformat(),
        created_at=evidence.created_at.isoformat(),
        updated_at=evidence.updated_at.isoformat(),
        metadata=evidence.metadata,
    )
