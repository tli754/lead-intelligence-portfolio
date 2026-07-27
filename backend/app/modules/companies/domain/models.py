"""Domain model for a company tracked through the discovery/scoring pipeline.

Pure Pydantic — no FastAPI or MongoDB imports. This mirrors the MongoDB
document shape stored by `infrastructure/mongo_repository.py`.
"""

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from app.modules.companies.domain.enums import ProcessingStatus, WorkflowStatus


class CompanyIdentity(BaseModel):
    """Descriptive, non-pipeline facts about the company."""

    company_name: str | None = None
    platform: str | None = None
    country: str | None = None
    city: str | None = None


class CompanyProcessing(BaseModel):
    """Where the company sits in the pipeline, and the run that last touched each stage.

    Each `latest_*_run_id` is an opaque identifier for a run record owned by
    that stage's own future module (discovery/crawl/extraction/analysis/
    scoring) — this module only stores the id, never interprets it.
    """

    status: ProcessingStatus = ProcessingStatus.IMPORTED
    latest_discovery_run_id: str | None = None
    latest_crawl_run_id: str | None = None
    latest_extraction_run_id: str | None = None
    latest_analysis_run_id: str | None = None
    latest_scoring_run_id: str | None = None


class CompanyWorkflow(BaseModel):
    """A human reviewer's manual disposition of the company."""

    manual_status: WorkflowStatus = WorkflowStatus.UNREVIEWED
    shortlisted: bool = False
    notes_count: int = Field(default=0, ge=0)


def _as_utc(value: datetime) -> datetime:
    """Treat a naive datetime as UTC rather than rejecting it.

    Motor returns naive datetimes on read unless the client is constructed
    with `tz_aware=True` (configured in `app/db.py`, outside this module) —
    so timezone-awareness has to be enforced at this boundary instead of
    assumed from the driver.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class Company(BaseModel):
    """A company tracked through discovery, crawling, extraction, analysis and scoring.

    `company_id` is an application-generated identifier (not the MongoDB
    `_id`), so callers never depend on MongoDB's ObjectId type.
    """

    company_id: str = Field(default_factory=lambda: str(uuid4()))
    domain: str
    normalized_domain: str

    identity: CompanyIdentity = Field(default_factory=CompanyIdentity)
    processing: CompanyProcessing = Field(default_factory=CompanyProcessing)
    workflow: CompanyWorkflow = Field(default_factory=CompanyWorkflow)

    created_at: datetime
    updated_at: datetime
    document_version: int = 1

    @field_validator("normalized_domain")
    @classmethod
    def normalized_domain_not_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("normalized_domain must not be empty")
        return value

    @field_validator("created_at", "updated_at")
    @classmethod
    def timestamps_are_utc(cls, value: datetime) -> datetime:
        return _as_utc(value)
