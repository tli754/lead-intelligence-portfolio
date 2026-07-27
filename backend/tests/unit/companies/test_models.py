from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.modules.companies.domain.enums import ProcessingStatus, WorkflowStatus
from app.modules.companies.domain.models import Company


def _now() -> datetime:
    return datetime.now(UTC)


class TestCompanyValidation:
    def test_defaults(self) -> None:
        company = Company(
            domain="example.com",
            normalized_domain="example.com",
            created_at=_now(),
            updated_at=_now(),
        )
        assert company.processing.status == ProcessingStatus.IMPORTED
        assert company.workflow.manual_status == WorkflowStatus.UNREVIEWED
        assert company.workflow.shortlisted is False
        assert company.workflow.notes_count == 0
        assert company.document_version == 1
        assert company.company_id  # auto-generated

    def test_rejects_empty_normalized_domain(self) -> None:
        with pytest.raises(ValidationError):
            Company(
                domain="example.com",
                normalized_domain="   ",
                created_at=_now(),
                updated_at=_now(),
            )

    def test_rejects_invalid_processing_status(self) -> None:
        with pytest.raises(ValidationError):
            Company.model_validate(
                {
                    "domain": "example.com",
                    "normalized_domain": "example.com",
                    "processing": {"status": "not-a-real-status"},
                    "created_at": _now(),
                    "updated_at": _now(),
                }
            )

    def test_rejects_invalid_workflow_status(self) -> None:
        with pytest.raises(ValidationError):
            Company.model_validate(
                {
                    "domain": "example.com",
                    "normalized_domain": "example.com",
                    "workflow": {"manual_status": "not-a-real-status"},
                    "created_at": _now(),
                    "updated_at": _now(),
                }
            )

    def test_rejects_negative_notes_count(self) -> None:
        with pytest.raises(ValidationError):
            Company.model_validate(
                {
                    "domain": "example.com",
                    "normalized_domain": "example.com",
                    "workflow": {"notes_count": -1},
                    "created_at": _now(),
                    "updated_at": _now(),
                }
            )

    def test_accepts_valid_enum_values(self) -> None:
        company = Company.model_validate(
            {
                "domain": "example.com",
                "normalized_domain": "example.com",
                "processing": {"status": "crawling"},
                "workflow": {"manual_status": "shortlisted"},
                "created_at": _now(),
                "updated_at": _now(),
            }
        )
        assert company.processing.status == ProcessingStatus.CRAWLING
        assert company.workflow.manual_status == WorkflowStatus.SHORTLISTED

    def test_coerces_naive_datetime_to_utc(self) -> None:
        naive = datetime(2026, 7, 25, 12, 0, 0)
        assert naive.tzinfo is None

        company = Company(
            domain="example.com",
            normalized_domain="example.com",
            created_at=naive,
            updated_at=naive,
        )

        assert company.created_at.tzinfo is not None
        offset = company.created_at.utcoffset()
        assert offset is not None
        assert offset.total_seconds() == 0
        assert company.updated_at.tzinfo is not None

    def test_preserves_already_aware_utc_datetime(self) -> None:
        aware = datetime(2026, 7, 25, 12, 0, 0, tzinfo=UTC)

        company = Company(
            domain="example.com",
            normalized_domain="example.com",
            created_at=aware,
            updated_at=aware,
        )

        assert company.created_at == aware

    def test_run_id_fields_default_to_none(self) -> None:
        company = Company(
            domain="example.com",
            normalized_domain="example.com",
            created_at=_now(),
            updated_at=_now(),
        )
        assert company.processing.latest_discovery_run_id is None
        assert company.processing.latest_crawl_run_id is None
        assert company.processing.latest_extraction_run_id is None
        assert company.processing.latest_analysis_run_id is None
        assert company.processing.latest_scoring_run_id is None
