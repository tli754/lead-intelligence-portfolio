"""Domain models for the extraction module. Pure Pydantic — no FastAPI or MongoDB imports.

Every field is exactly as brief section 1 lists, plus the documented
additions the contract calls out explicitly: `ExtractionRun.idempotency_key`
and `document_version` on `ExtractionRun`/`ExtractorExecution`/
`FactCandidate`/`FactRecord`/`FactConflict` (contract T3).
"""

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from app.modules.discovery.domain.enums import PageType
from app.modules.extraction.domain.enums import (
    ExtractionStatus,
    ExtractorExecutionStatus,
    FactSourceType,
    FactStatus,
    VerificationState,
)
from app.modules.extraction.domain.field_catalogue import FieldPath, FieldValueType


def _as_utc(value: datetime) -> datetime:
    """Treat a naive datetime as UTC rather than rejecting it.

    Duplicated locally, matching every prior module's own `_as_utc`
    precedent — Motor returns naive datetimes on read unless the client is
    constructed with `tz_aware=True`.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


# `int, 0-100 inclusive` via a validated Annotated type — never a bare `int`
# anywhere confidence is stored (brief section 1's explicit `ConfidenceScore`
# type, contract T3).
ConfidenceScore = Annotated[int, Field(ge=0, le=100)]


_LIST_VALUE_TYPES = frozenset({FieldValueType.STRING_LIST, FieldValueType.STRUCTURED_ENTITY_LIST})


class FactValue(BaseModel):
    """A typed wrapper around a raw extracted value.

    Validated against the declared `value_type` at construction — a
    `string_list` value_type must carry an actual `list`, a
    `structured_entity` value_type must carry an actual `dict`, etc.
    `None` is always permitted (an as-yet-unset/unknown value).
    """

    value_type: FieldValueType
    value: Any = None

    @model_validator(mode="after")
    def _value_matches_declared_type(self) -> "FactValue":
        if self.value is None:
            return self
        checks: dict[FieldValueType, type | tuple[type, ...]] = {
            FieldValueType.STRING: str,
            FieldValueType.BOOLEAN: bool,
            FieldValueType.INTEGER: int,
            FieldValueType.FLOAT: (int, float),
            FieldValueType.ENUM: str,
            FieldValueType.STRING_LIST: list,
            FieldValueType.STRUCTURED_ENTITY: dict,
            FieldValueType.STRUCTURED_ENTITY_LIST: list,
        }
        expected = checks[self.value_type]
        if self.value_type == FieldValueType.INTEGER and isinstance(self.value, bool):
            raise ValueError("integer FactValue must not be a bool")
        if not isinstance(self.value, expected):
            raise ValueError(
                f"value {self.value!r} does not match declared value_type={self.value_type!r}"
            )
        if self.value_type in _LIST_VALUE_TYPES and not isinstance(self.value, list):
            raise ValueError(f"value_type={self.value_type!r} requires a list value")
        return self


class ExtractionRunOptions(BaseModel):
    """Per-run overrides accepted by `POST /api/companies/{id}/extraction-runs`
    (brief section 23's request body)."""

    extractor_ids: list[str] = Field(default_factory=list)
    page_types: list[PageType] = Field(default_factory=list)
    force_refresh: bool = False


class ExtractionWarning(BaseModel):
    """A structured, non-fatal issue recorded during an extraction run.

    Mirrors `CrawlWarning`'s shape, extended with `field_path`/
    `extractor_id` since a warning here is usually extractor-scoped.
    """

    code: str
    message: str
    page_id: str | None = None
    field_path: FieldPath | None = None
    extractor_id: str | None = None
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def timestamp_is_utc(cls, value: datetime) -> datetime:
        return _as_utc(value)


class ExtractionSummary(BaseModel):
    pages_considered: int = 0
    pages_processed: int = 0
    pages_skipped: int = 0
    extractor_executions: int = 0
    candidates_created: int = 0
    facts_accepted: int = 0
    facts_conflicting: int = 0
    facts_unknown: int = 0
    evidence_created: int = 0
    warnings: int = 0
    duration_ms: int = 0


class ExtractorDefinition(BaseModel):
    extractor_id: str
    name: str
    version: str
    supported_page_types: list[PageType] = Field(default_factory=list)
    output_field_paths: list[FieldPath] = Field(default_factory=list)
    priority: int = 0
    enabled: bool = True


class ExtractorExecution(BaseModel):
    extractor_execution_id: str = Field(default_factory=lambda: str(uuid4()))
    extraction_run_id: str
    page_id: str
    extractor_id: str
    extractor_version: str
    status: ExtractorExecutionStatus
    candidates_produced: int = 0
    warnings: list[ExtractionWarning] = Field(default_factory=list)
    duration_ms: int = 0
    started_at: datetime
    completed_at: datetime
    document_version: int = 1

    @field_validator("started_at", "completed_at")
    @classmethod
    def timestamps_are_utc(cls, value: datetime) -> datetime:
        return _as_utc(value)


class FactCandidate(BaseModel):
    candidate_id: str = Field(default_factory=lambda: str(uuid4()))
    extraction_run_id: str
    company_id: str
    page_id: str
    field_path: FieldPath
    value: Any = None
    normalized_value: Any = None
    value_type: FieldValueType
    source_type: FactSourceType
    extractor_id: str
    extractor_version: str
    confidence: ConfidenceScore
    verification_state: VerificationState
    evidence_ids: list[str] = Field(default_factory=list)
    qualifiers: dict[str, Any] = Field(default_factory=dict)
    observed_at: datetime
    created_at: datetime
    document_version: int = 1

    @field_validator("observed_at", "created_at")
    @classmethod
    def timestamps_are_utc(cls, value: datetime) -> datetime:
        return _as_utc(value)


class FactRecord(BaseModel):
    fact_id: str = Field(default_factory=lambda: str(uuid4()))
    company_id: str
    extraction_run_id: str
    field_path: FieldPath
    value: Any = None
    normalized_value: Any = None
    value_type: FieldValueType
    status: FactStatus
    verification_state: VerificationState
    confidence: ConfidenceScore
    evidence_ids: list[str] = Field(default_factory=list)
    selected_candidate_ids: list[str] = Field(default_factory=list)
    conflicting_candidate_ids: list[str] = Field(default_factory=list)
    source_count: int = 0
    first_observed_at: datetime
    last_observed_at: datetime
    last_verified_at: datetime
    extractor_versions: dict[str, str] = Field(default_factory=dict)
    reconciliation_rule_ids: list[str] = Field(default_factory=list)
    # Documented addition (contract T3/T29): estimate metadata
    # (`estimation_method`/`sample_size`/`exact`) carried over from the
    # winning candidate(s)' own `qualifiers`, so `GET /api/companies/{id}/facts`
    # can "distinguish exact values from estimates" (brief section 23)
    # without a separate lookup back to the candidate collection.
    qualifiers: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    document_version: int = 1

    @field_validator(
        "first_observed_at", "last_observed_at", "last_verified_at", "created_at", "updated_at"
    )
    @classmethod
    def timestamps_are_utc(cls, value: datetime) -> datetime:
        return _as_utc(value)


class FactConflict(BaseModel):
    conflict_id: str = Field(default_factory=lambda: str(uuid4()))
    company_id: str
    extraction_run_id: str
    field_path: FieldPath
    candidate_ids: list[str] = Field(default_factory=list)
    selected_candidate_id: str | None = None
    conflict_type: str
    resolution: str | None = None
    rule_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    document_version: int = 1

    @field_validator("created_at")
    @classmethod
    def timestamp_is_utc(cls, value: datetime) -> datetime:
        return _as_utc(value)


class ExtractionRun(BaseModel):
    """`configuration_snapshot` holds every version tag from brief section
    27: field-catalogue version, per-extractor implementation versions,
    pattern-rules versions, technology-signatures version, evidence-format
    version, confidence-policy version, reconciliation-rules version,
    freshness-policy version, and projection-schema version (contract T3 /
    AC-40)."""

    extraction_run_id: str = Field(default_factory=lambda: str(uuid4()))
    company_id: str
    crawl_run_id: str

    status: ExtractionStatus = ExtractionStatus.QUEUED
    extractor_version: str = "v1"
    reconciliation_version: str = "v1"
    started_at: datetime | None = None
    completed_at: datetime | None = None

    configuration_snapshot: dict[str, Any] = Field(default_factory=dict)
    summary: ExtractionSummary = Field(default_factory=ExtractionSummary)
    warnings: list[ExtractionWarning] = Field(default_factory=list)
    error: str | None = None

    created_at: datetime
    updated_at: datetime

    # Documented addition (contract T3): needed for idempotent retry.
    idempotency_key: str

    document_version: int = 1

    @field_validator("started_at", "completed_at", "created_at", "updated_at")
    @classmethod
    def timestamps_are_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value) if value is not None else None
