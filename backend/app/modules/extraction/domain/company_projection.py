"""Builds a read-optimized projection of a company's latest accepted facts.

Built entirely inside this module (T23) — never writes to any
Company-owned collection directly (brief's explicit "do not modify the
Company module in this worktree"). Every `ProjectedField` retains its own
`evidence_ids` — this never flattens evidence away (AC-36).

The integration adapter (`infrastructure/company_service_gateway.py`) may
later map this to `companies.latest_facts` or an equivalent field, once
that follow-up lands (contract resolution #3) — not built here.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.modules.extraction.domain.enums import VerificationState
from app.modules.extraction.domain.field_catalogue import FieldPath
from app.modules.extraction.domain.models import ConfidenceScore, FactRecord

PROJECTION_SCHEMA_VERSION = "v1"

_GROUP_PREFIXES = (
    "identity",
    "business",
    "catalogue",
    "operations",
    "technology",
    "organisation",
    "growth",
)


class ProjectedField(BaseModel):
    value: Any = None
    verification_state: VerificationState
    confidence: ConfidenceScore
    evidence_ids: list[str] = Field(default_factory=list)
    last_verified_at: datetime


class ExtractionQualitySummary(BaseModel):
    """The `extraction_quality` group brief section 21 names alongside the
    seven field-based groups — a summary of coverage/trust, not per-field
    projected values."""

    facts_accepted: int = 0
    facts_conflicting: int = 0
    facts_stale: int = 0
    average_confidence: int = 0
    fields_covered: int = 0
    fields_total: int = len(FieldPath)


class CompanyFactsProjection(BaseModel):
    schema_version: str = PROJECTION_SCHEMA_VERSION
    identity: dict[str, ProjectedField] = Field(default_factory=dict)
    business: dict[str, ProjectedField] = Field(default_factory=dict)
    catalogue: dict[str, ProjectedField] = Field(default_factory=dict)
    operations: dict[str, ProjectedField] = Field(default_factory=dict)
    technology: dict[str, ProjectedField] = Field(default_factory=dict)
    organisation: dict[str, ProjectedField] = Field(default_factory=dict)
    growth: dict[str, ProjectedField] = Field(default_factory=dict)
    extraction_quality: ExtractionQualitySummary = Field(default_factory=ExtractionQualitySummary)


_GROUP_ATTRIBUTE_BY_PREFIX = {
    "identity": "identity",
    "business": "business",
    "catalogue": "catalogue",
    "operations": "operations",
    "technology": "technology",
    "organisation": "organisation",
    "growth": "growth",
}


def build_projection(facts: list[FactRecord]) -> CompanyFactsProjection:
    """Pure — groups accepted facts by their `FieldPath` prefix, dropping
    nothing but never inventing anything either. Only `accepted`/
    `conflicting`/`stale` facts (i.e. anything already reconciled) are
    represented; raw candidates never appear here."""
    projection = CompanyFactsProjection()

    accepted_confidences: list[int] = []
    stale_count = 0
    conflicting_count = 0

    for fact in facts:
        prefix, _, short_name = fact.field_path.value.partition(".")
        group_attribute = _GROUP_ATTRIBUTE_BY_PREFIX.get(prefix)
        if group_attribute is None:
            continue

        projected = ProjectedField(
            value=fact.normalized_value if fact.normalized_value is not None else fact.value,
            verification_state=fact.verification_state,
            confidence=fact.confidence,
            evidence_ids=list(fact.evidence_ids),
            last_verified_at=fact.last_verified_at,
        )
        getattr(projection, group_attribute)[short_name] = projected

        if fact.verification_state == VerificationState.STALE:
            stale_count += 1
        elif fact.verification_state == VerificationState.CONFLICTING:
            conflicting_count += 1
        else:
            accepted_confidences.append(fact.confidence)

    fields_covered = sum(
        len(getattr(projection, group_attribute)) for group_attribute in _GROUP_PREFIXES
    )
    projection.extraction_quality = ExtractionQualitySummary(
        facts_accepted=len(accepted_confidences),
        facts_conflicting=conflicting_count,
        facts_stale=stale_count,
        average_confidence=(
            int(sum(accepted_confidences) / len(accepted_confidences))
            if accepted_confidences
            else 0
        ),
        fields_covered=fields_covered,
        fields_total=len(FieldPath),
    )
    return projection
