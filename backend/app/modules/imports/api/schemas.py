"""Request/response DTOs for the imports HTTP API. All JSON is camelCase.

A small local `CamelCaseModel` base, not imported from the companies
module's own copy — this module's only real coupling to `companies` is
the gateway (`infrastructure/company_service_gateway.py`); duplicating a
few lines of Pydantic config here keeps that coupling to just the one
sanctioned integration point.
"""

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.modules.imports.domain.models import (
    ImportBatchSummary,
    ImportPreview,
    ImportResult,
    ImportRow,
)


class CamelCaseModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class StoreLeadsImportRequest(CamelCaseModel):
    html: str = Field(min_length=1)


class ImportRowErrorResponse(CamelCaseModel):
    field: str | None
    message: str


class ImportRowResponse(CamelCaseModel):
    row_number: int
    website: str | None
    normalized_domain: str | None
    platform: str | None
    country: str | None
    city: str | None
    validation_status: str
    errors: list[ImportRowErrorResponse]
    duplicate_status: str
    outcome: str | None


def _row_to_response(row: ImportRow) -> ImportRowResponse:
    return ImportRowResponse(
        row_number=row.row_number,
        website=row.website,
        normalized_domain=row.normalized_domain,
        platform=row.platform,
        country=row.country,
        city=row.city,
        validation_status=row.validation_status.value,
        errors=[ImportRowErrorResponse(field=e.field, message=e.message) for e in row.errors],
        duplicate_status=row.duplicate_status.value,
        outcome=row.outcome.value if row.outcome is not None else None,
    )


class ImportBatchSummaryResponse(CamelCaseModel):
    rows_found: int
    valid_rows: int
    invalid_rows: int
    existing_companies: int
    duplicate_rows_in_file: int
    importable_rows: int


def _summary_to_response(summary: ImportBatchSummary) -> ImportBatchSummaryResponse:
    return ImportBatchSummaryResponse(**summary.model_dump())


class ImportPreviewDataResponse(CamelCaseModel):
    summary: ImportBatchSummaryResponse
    rows: list[ImportRowResponse]


class ImportPreviewResponse(CamelCaseModel):
    data: ImportPreviewDataResponse


def preview_to_response(preview: ImportPreview) -> ImportPreviewResponse:
    return ImportPreviewResponse(
        data=ImportPreviewDataResponse(
            summary=_summary_to_response(preview.summary),
            rows=[_row_to_response(row) for row in preview.rows],
        )
    )


class ImportResultDataResponse(CamelCaseModel):
    created: int
    skipped_existing: int
    skipped_invalid: int
    failed: int
    rows: list[ImportRowResponse]


class ImportResultResponse(CamelCaseModel):
    data: ImportResultDataResponse


def result_to_response(result: ImportResult) -> ImportResultResponse:
    return ImportResultResponse(
        data=ImportResultDataResponse(
            created=result.created,
            skipped_existing=result.skipped_existing,
            skipped_invalid=result.skipped_invalid,
            failed=result.failed,
            rows=[_row_to_response(row) for row in result.rows],
        )
    )
