"""Domain models for the imports module. Pure Pydantic — no FastAPI or MongoDB imports."""

from pydantic import BaseModel, Field

from app.modules.imports.domain.enums import (
    DuplicateStatus,
    ImportRowOutcome,
    ImportSource,
    ValidationStatus,
)


class ImportRowError(BaseModel):
    """A single structured validation problem on a row.

    `field` is `None` for row-level problems not tied to one column.
    """

    field: str | None
    message: str


class ImportRow(BaseModel):
    """One row of a parsed import file, from raw extraction through to import outcome.

    `outcome` is `None` until `ImportService` actually attempts to import
    the row — a preview never sets it.
    """

    row_number: int
    website: str | None
    normalized_domain: str | None
    platform: str | None
    country: str | None
    city: str | None
    validation_status: ValidationStatus
    errors: list[ImportRowError] = Field(default_factory=list)
    duplicate_status: DuplicateStatus
    outcome: ImportRowOutcome | None = None


class ImportBatchSummary(BaseModel):
    rows_found: int
    valid_rows: int
    invalid_rows: int
    existing_companies: int
    duplicate_rows_in_file: int
    importable_rows: int


class ImportPreview(BaseModel):
    source: ImportSource
    summary: ImportBatchSummary
    rows: list[ImportRow]


class ImportResult(BaseModel):
    source: ImportSource
    created: int
    skipped_existing: int
    skipped_invalid: int
    failed: int
    rows: list[ImportRow]
