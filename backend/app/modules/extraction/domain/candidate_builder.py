"""Small builder helpers shared by every extractor — reduces boilerplate
around constructing a `FactCandidateDraft` + its `EvidenceDraft`(s) from a
`PageContext`, without hiding any business decision (every argument an
extractor cares about is still passed explicitly)."""

from typing import Any

from app.modules.evidence.domain.enums import EvidenceStrength, EvidenceType
from app.modules.evidence.domain.evidence_factory import EvidenceDraft
from app.modules.evidence.domain.models import EvidenceLocation
from app.modules.extraction.domain.enums import FactSourceType, VerificationState
from app.modules.extraction.domain.extractor import FactCandidateDraft, PageContext
from app.modules.extraction.domain.field_catalogue import FieldPath, FieldValueType
from app.modules.extraction.domain.models import ConfidenceScore


def build_evidence_draft(
    *,
    page_context: PageContext,
    field_path: FieldPath,
    evidence_type: EvidenceType,
    strength: EvidenceStrength,
    source_fragment: str,
    extractor_id: str,
    extractor_version: str,
    prefix_context: str = "",
    suffix_context: str = "",
    location: EvidenceLocation | None = None,
    raw_value: str | None = None,
    normalized_value: str | None = None,
    is_business_contact_fact: bool = False,
    metadata: dict[str, Any] | None = None,
) -> EvidenceDraft:
    return EvidenceDraft(
        company_id=page_context.company_id,
        extraction_run_id="",  # filled in by the application service
        page_id=page_context.page_id,
        fact_field_path=field_path.value,
        evidence_type=evidence_type,
        strength=strength,
        source_url=page_context.source_url,
        page_type=page_context.page_type.value,
        extractor_id=extractor_id,
        extractor_version=extractor_version,
        location=location or EvidenceLocation(),
        source_fragment=source_fragment,
        prefix_context=prefix_context,
        suffix_context=suffix_context,
        raw_value=raw_value,
        normalized_value=normalized_value,
        observed_at=page_context.fetched_at,
        is_business_contact_fact=is_business_contact_fact,
        metadata=metadata or {},
    )


def build_candidate_draft(
    *,
    field_path: FieldPath,
    value: Any,
    normalized_value: Any,
    value_type: FieldValueType,
    source_type: FactSourceType,
    confidence: ConfidenceScore,
    verification_state: VerificationState,
    evidence_drafts: list[EvidenceDraft],
    qualifiers: dict[str, Any] | None = None,
) -> FactCandidateDraft:
    return FactCandidateDraft(
        field_path=field_path,
        value=value,
        normalized_value=normalized_value,
        value_type=value_type,
        source_type=source_type,
        confidence=confidence,
        verification_state=verification_state,
        qualifiers=qualifiers or {},
        evidence_drafts=evidence_drafts,
    )
