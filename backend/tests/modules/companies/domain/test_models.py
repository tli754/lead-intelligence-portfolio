from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.modules.companies.domain.enums import ProcessingStatus, WorkflowStatus
from app.modules.companies.domain.models import Company, CompanyTimestamps


def _timestamps() -> CompanyTimestamps:
    now = datetime.now(UTC)
    return CompanyTimestamps(created_at=now, updated_at=now)


class TestCompanyValidation:
    def test_defaults(self) -> None:
        company = Company(
            domain="example.com", normalized_domain="example.com", timestamps=_timestamps()
        )
        assert company.processing.status == ProcessingStatus.IMPORTED
        assert company.workflow.manual_status == WorkflowStatus.UNREVIEWED
        assert company.workflow.shortlisted is False
        assert company.workflow.notes_count == 0
        assert company.company_id  # auto-generated

    def test_rejects_empty_normalized_domain(self) -> None:
        with pytest.raises(ValidationError):
            Company(domain="example.com", normalized_domain="   ", timestamps=_timestamps())

    def test_rejects_invalid_processing_status(self) -> None:
        with pytest.raises(ValidationError):
            Company(
                domain="example.com",
                normalized_domain="example.com",
                processing={"status": "not-a-real-status"},
                timestamps=_timestamps(),
            )

    def test_rejects_invalid_workflow_status(self) -> None:
        with pytest.raises(ValidationError):
            Company(
                domain="example.com",
                normalized_domain="example.com",
                workflow={"manual_status": "not-a-real-status"},
                timestamps=_timestamps(),
            )

    def test_rejects_negative_notes_count(self) -> None:
        with pytest.raises(ValidationError):
            Company(
                domain="example.com",
                normalized_domain="example.com",
                workflow={"notes_count": -1},
                timestamps=_timestamps(),
            )

    def test_accepts_valid_enum_values(self) -> None:
        company = Company(
            domain="example.com",
            normalized_domain="example.com",
            processing={"status": "crawling"},
            workflow={"manual_status": "shortlisted"},
            timestamps=_timestamps(),
        )
        assert company.processing.status == ProcessingStatus.CRAWLING
        assert company.workflow.manual_status == WorkflowStatus.SHORTLISTED
