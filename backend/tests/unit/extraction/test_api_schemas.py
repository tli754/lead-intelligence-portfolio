"""Unit tests for the extraction-module API schemas — camelCase shape only."""

from datetime import UTC, datetime

from app.modules.extraction.api.schemas import fact_to_response, run_to_response
from app.modules.extraction.domain.enums import ExtractionStatus, FactStatus, VerificationState
from app.modules.extraction.domain.field_catalogue import FieldPath, FieldValueType
from app.modules.extraction.domain.models import ExtractionRun, FactRecord

NOW = datetime(2026, 7, 26, tzinfo=UTC)


def test_extraction_run_response_is_camel_case():
    run = ExtractionRun(
        company_id="company-1",
        crawl_run_id="crawl-1",
        status=ExtractionStatus.COMPLETED,
        idempotency_key="key-1",
        created_at=NOW,
        updated_at=NOW,
    )
    payload = run_to_response(run).model_dump(by_alias=True)
    assert "extractionRunId" in payload
    assert "crawlRunId" in payload
    assert "extraction_run_id" not in payload


def test_fact_response_distinguishes_unknown_from_false():
    fact = FactRecord(
        company_id="company-1",
        extraction_run_id="run-1",
        field_path=FieldPath.BUSINESS_WHOLESALE,
        value=False,
        normalized_value=False,
        value_type=FieldValueType.BOOLEAN,
        status=FactStatus.ACCEPTED,
        verification_state=VerificationState.VERIFIED,
        confidence=80,
        first_observed_at=NOW,
        last_observed_at=NOW,
        last_verified_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    payload = fact_to_response(fact).model_dump(by_alias=True)
    assert payload["value"] is False
    assert payload["normalizedValue"] is False


def test_fact_response_preserves_conflict():
    fact = FactRecord(
        company_id="company-1",
        extraction_run_id="run-1",
        field_path=FieldPath.IDENTITY_COMPANY_NAME,
        value=None,
        normalized_value=None,
        value_type=FieldValueType.STRING,
        status=FactStatus.CONFLICTING,
        verification_state=VerificationState.CONFLICTING,
        confidence=80,
        conflicting_candidate_ids=["c1", "c2"],
        first_observed_at=NOW,
        last_observed_at=NOW,
        last_verified_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    payload = fact_to_response(fact).model_dump(by_alias=True)
    assert payload["status"] == "conflicting"
    assert payload["conflictingCandidateIds"] == ["c1", "c2"]


def test_fact_response_exposes_estimate_metadata():
    fact = FactRecord(
        company_id="company-1",
        extraction_run_id="run-1",
        field_path=FieldPath.CATALOGUE_PRODUCT_COUNT_ESTIMATE,
        value=120,
        normalized_value=120,
        value_type=FieldValueType.INTEGER,
        status=FactStatus.ACCEPTED,
        verification_state=VerificationState.INFERRED,
        confidence=60,
        qualifiers={"estimation_method": "pagination_derived", "sample_size": 12},
        first_observed_at=NOW,
        last_observed_at=NOW,
        last_verified_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    payload = fact_to_response(fact).model_dump(by_alias=True)
    assert payload["estimationMethod"] == "pagination_derived"
    assert payload["sampleSize"] == 12


def test_run_response_exposes_version_fields():
    run = ExtractionRun(
        company_id="company-1",
        crawl_run_id="crawl-1",
        idempotency_key="key-1",
        created_at=NOW,
        updated_at=NOW,
        configuration_snapshot={"field_catalogue_version": "v1"},
    )
    payload = run_to_response(run).model_dump(by_alias=True)
    assert payload["extractorVersion"] == "v1"
    assert payload["reconciliationVersion"] == "v1"
    assert payload["configurationSnapshot"]["field_catalogue_version"] == "v1"
