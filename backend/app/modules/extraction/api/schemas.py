"""Request/response DTOs for the extraction-module HTTP API. All JSON is camelCase.

A small local `CamelCaseModel` base, not imported from any other module —
matching `modules/crawling/api/schemas.py`'s exact precedent. Responses
never include full page HTML, distinguish `unknown` from `false`
(a boolean fact's `value`/`normalizedValue` stay `null` unless a fact was
actually accepted), distinguish exact values from estimates (surfacing
`estimationMethod`/`sampleSize` from `qualifiers` where present), preserve
conflicts (`conflictingCandidateIds` is never silently dropped), and
expose extractor/rule/policy version fields.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.modules.discovery.domain.enums import PageType
from app.modules.extraction.domain.models import (
    ExtractionRun,
    ExtractionRunOptions,
    ExtractionSummary,
    ExtractorExecution,
    FactCandidate,
    FactConflict,
    FactRecord,
)


class CamelCaseModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# --- Requests ------------------------------------------------------------------


class ExtractionRunOptionsRequest(CamelCaseModel):
    extractor_ids: list[str] = []
    page_types: list[PageType] = []
    force_refresh: bool = False

    def to_domain(self) -> ExtractionRunOptions:
        return ExtractionRunOptions(
            extractor_ids=self.extractor_ids,
            page_types=self.page_types,
            force_refresh=self.force_refresh,
        )


class CreateExtractionRunRequest(CamelCaseModel):
    crawl_run_id: str
    options: ExtractionRunOptionsRequest | None = None


# --- Shared response fragments --------------------------------------------------


class PaginationMeta(CamelCaseModel):
    page: int
    page_size: int
    total: int


class ExtractionSummaryResponse(CamelCaseModel):
    pages_considered: int
    pages_processed: int
    pages_skipped: int
    extractor_executions: int
    candidates_created: int
    facts_accepted: int
    facts_conflicting: int
    facts_unknown: int
    evidence_created: int
    warnings: int
    duration_ms: int


def summary_to_response(summary: ExtractionSummary) -> ExtractionSummaryResponse:
    return ExtractionSummaryResponse(**summary.model_dump())


# --- Extraction runs -------------------------------------------------------------


class ExtractionRunResponse(CamelCaseModel):
    extraction_run_id: str
    company_id: str
    crawl_run_id: str
    status: str
    extractor_version: str
    reconciliation_version: str
    started_at: str | None
    completed_at: str | None
    configuration_snapshot: dict[str, Any]
    summary: ExtractionSummaryResponse
    warnings_count: int
    error: str | None
    created_at: str
    updated_at: str


class ExtractionRunEnvelope(CamelCaseModel):
    data: ExtractionRunResponse


def run_to_response(run: ExtractionRun) -> ExtractionRunResponse:
    return ExtractionRunResponse(
        extraction_run_id=run.extraction_run_id,
        company_id=run.company_id,
        crawl_run_id=run.crawl_run_id,
        status=run.status.value,
        extractor_version=run.extractor_version,
        reconciliation_version=run.reconciliation_version,
        started_at=run.started_at.isoformat() if run.started_at else None,
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
        configuration_snapshot=run.configuration_snapshot,
        summary=summary_to_response(run.summary),
        warnings_count=len(run.warnings),
        error=run.error,
        created_at=run.created_at.isoformat(),
        updated_at=run.updated_at.isoformat(),
    )


# --- Facts -----------------------------------------------------------------------


class FactResponse(CamelCaseModel):
    fact_id: str
    company_id: str
    extraction_run_id: str
    field_path: str
    value: Any
    normalized_value: Any
    value_type: str
    status: str
    verification_state: str
    confidence: int
    evidence_ids: list[str]
    selected_candidate_ids: list[str]
    conflicting_candidate_ids: list[str]
    source_count: int
    first_observed_at: str
    last_observed_at: str
    last_verified_at: str
    extractor_versions: dict[str, str]
    reconciliation_rule_ids: list[str]
    estimation_method: str | None = None
    sample_size: int | None = None
    created_at: str
    updated_at: str


class FactEnvelope(CamelCaseModel):
    data: FactResponse


class FactListResponse(CamelCaseModel):
    data: list[FactResponse]
    pagination: PaginationMeta


def fact_to_response(fact: FactRecord) -> FactResponse:
    return FactResponse(
        fact_id=fact.fact_id,
        company_id=fact.company_id,
        extraction_run_id=fact.extraction_run_id,
        field_path=fact.field_path.value,
        value=fact.value,
        normalized_value=fact.normalized_value,
        value_type=fact.value_type.value,
        status=fact.status.value,
        verification_state=fact.verification_state.value,
        confidence=fact.confidence,
        evidence_ids=fact.evidence_ids,
        selected_candidate_ids=fact.selected_candidate_ids,
        conflicting_candidate_ids=fact.conflicting_candidate_ids,
        source_count=fact.source_count,
        first_observed_at=fact.first_observed_at.isoformat(),
        last_observed_at=fact.last_observed_at.isoformat(),
        last_verified_at=fact.last_verified_at.isoformat(),
        extractor_versions=fact.extractor_versions,
        reconciliation_rule_ids=fact.reconciliation_rule_ids,
        estimation_method=fact.qualifiers.get("estimation_method"),
        sample_size=fact.qualifiers.get("sample_size"),
        created_at=fact.created_at.isoformat(),
        updated_at=fact.updated_at.isoformat(),
    )


# --- Candidates -------------------------------------------------------------------


class FactCandidateResponse(CamelCaseModel):
    candidate_id: str
    extraction_run_id: str
    company_id: str
    page_id: str
    field_path: str
    value: Any
    normalized_value: Any
    value_type: str
    source_type: str
    extractor_id: str
    extractor_version: str
    confidence: int
    verification_state: str
    evidence_ids: list[str]
    qualifiers: dict[str, Any]
    observed_at: str
    created_at: str


class FactCandidateListResponse(CamelCaseModel):
    data: list[FactCandidateResponse]
    pagination: PaginationMeta


def candidate_to_response(candidate: FactCandidate) -> FactCandidateResponse:
    return FactCandidateResponse(
        candidate_id=candidate.candidate_id,
        extraction_run_id=candidate.extraction_run_id,
        company_id=candidate.company_id,
        page_id=candidate.page_id,
        field_path=candidate.field_path.value,
        value=candidate.value,
        normalized_value=candidate.normalized_value,
        value_type=candidate.value_type.value,
        source_type=candidate.source_type.value,
        extractor_id=candidate.extractor_id,
        extractor_version=candidate.extractor_version,
        confidence=candidate.confidence,
        verification_state=candidate.verification_state.value,
        evidence_ids=candidate.evidence_ids,
        qualifiers=candidate.qualifiers,
        observed_at=candidate.observed_at.isoformat(),
        created_at=candidate.created_at.isoformat(),
    )


# --- Conflicts (embedded informationally, not its own top-level route) -----------


class FactConflictResponse(CamelCaseModel):
    conflict_id: str
    company_id: str
    extraction_run_id: str
    field_path: str
    candidate_ids: list[str]
    selected_candidate_id: str | None
    conflict_type: str
    resolution: str | None
    rule_ids: list[str]
    created_at: str


def conflict_to_response(conflict: FactConflict) -> FactConflictResponse:
    return FactConflictResponse(
        conflict_id=conflict.conflict_id,
        company_id=conflict.company_id,
        extraction_run_id=conflict.extraction_run_id,
        field_path=conflict.field_path.value,
        candidate_ids=conflict.candidate_ids,
        selected_candidate_id=conflict.selected_candidate_id,
        conflict_type=conflict.conflict_type,
        resolution=conflict.resolution,
        rule_ids=conflict.rule_ids,
        created_at=conflict.created_at.isoformat(),
    )


class ExtractorExecutionResponse(CamelCaseModel):
    extractor_execution_id: str
    extraction_run_id: str
    page_id: str
    extractor_id: str
    extractor_version: str
    status: str
    candidates_produced: int
    duration_ms: int
    started_at: str
    completed_at: str


def execution_to_response(execution: ExtractorExecution) -> ExtractorExecutionResponse:
    return ExtractorExecutionResponse(
        extractor_execution_id=execution.extractor_execution_id,
        extraction_run_id=execution.extraction_run_id,
        page_id=execution.page_id,
        extractor_id=execution.extractor_id,
        extractor_version=execution.extractor_version,
        status=execution.status.value,
        candidates_produced=execution.candidates_produced,
        duration_ms=execution.duration_ms,
        started_at=execution.started_at.isoformat(),
        completed_at=execution.completed_at.isoformat(),
    )
