"""Pydantic models for the `companies` domain.

`Company` mirrors the MongoDB document shape exactly (see
docs/architecture/mongodb-design.md). Request/response models validate
everything crossing the API boundary — the router never validates
anything by hand.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

CompanySource = Literal["paste_domain_list", "paste_storeleads_html"]


class Company(BaseModel):
    """A single imported company/store, as stored in the `companies` collection.

    Records are immutable once created in v1 (see ADR 0003) — there is no
    update/upsert path.
    """

    domain: str
    source: CompanySource
    url: str | None = None
    estimated_sales_yearly_usd: float | None = None
    source_created_at: date | None = None
    emails: list[str] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)
    imported_at: datetime


class ImportRequest(BaseModel):
    """Request body for `POST /api/companies/import`."""

    raw_text: str = Field(min_length=1)

    @field_validator("raw_text")
    @classmethod
    def reject_whitespace_only(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("raw_text must not be empty or whitespace-only")
        return value


class SkippedInvalidEntry(BaseModel):
    """A pasted line/row that could not be parsed into a valid domain."""

    raw_value: str
    reason: str


class ImportResponse(BaseModel):
    """Response body for `POST /api/companies/import`."""

    detected_format: Literal["domain_list", "storeleads_html"]
    total_rows_detected: int
    created: list[Company]
    created_count: int
    skipped_duplicate_in_paste: list[str]
    skipped_existing_in_db: list[str]
    skipped_invalid: list[SkippedInvalidEntry]
