"""Unit tests for the company facts projection (AC-36)."""

from datetime import UTC, datetime

from app.modules.extraction.domain.company_projection import build_projection
from app.modules.extraction.domain.enums import FactStatus, VerificationState
from app.modules.extraction.domain.field_catalogue import FieldPath, FieldValueType
from app.modules.extraction.domain.models import FactRecord

NOW = datetime(2026, 7, 26, tzinfo=UTC)


def _fact(
    field_path: FieldPath, *, value, evidence_ids, verification_state=VerificationState.VERIFIED
):
    return FactRecord(
        company_id="company-1",
        extraction_run_id="run-1",
        field_path=field_path,
        value=value,
        normalized_value=value,
        value_type=FieldValueType.STRING,
        status=FactStatus.ACCEPTED,
        verification_state=verification_state,
        confidence=80,
        evidence_ids=evidence_ids,
        selected_candidate_ids=["c1"],
        first_observed_at=NOW,
        last_observed_at=NOW,
        last_verified_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


def test_projection_preserves_evidence():
    facts = [
        _fact(FieldPath.IDENTITY_COMPANY_NAME, value="Acme", evidence_ids=["e1", "e2"]),
        _fact(FieldPath.TECHNOLOGY_COMMERCE_PLATFORM, value="shopify", evidence_ids=["e3"]),
    ]
    projection = build_projection(facts)

    assert projection.identity["company_name"].value == "Acme"
    assert projection.identity["company_name"].evidence_ids == ["e1", "e2"]
    assert projection.identity["company_name"].verification_state == VerificationState.VERIFIED
    assert projection.identity["company_name"].last_verified_at == NOW

    assert projection.technology["commerce_platform"].evidence_ids == ["e3"]


def test_projection_never_bare_value():
    facts = [_fact(FieldPath.BUSINESS_WHOLESALE, value=True, evidence_ids=["e1"])]
    projection = build_projection(facts)
    field = projection.business["wholesale"]
    assert field.evidence_ids
    assert field.confidence == 80


def test_extraction_quality_summary_counts():
    facts = [
        _fact(FieldPath.IDENTITY_COMPANY_NAME, value="Acme", evidence_ids=["e1"]),
        _fact(
            FieldPath.IDENTITY_CITY,
            value=None,
            evidence_ids=["e2"],
            verification_state=VerificationState.CONFLICTING,
        ),
        _fact(
            FieldPath.GROWTH_EXPANSION,
            value="expanding",
            evidence_ids=["e3"],
            verification_state=VerificationState.STALE,
        ),
    ]
    projection = build_projection(facts)
    assert projection.extraction_quality.facts_accepted == 1
    assert projection.extraction_quality.facts_conflicting == 1
    assert projection.extraction_quality.facts_stale == 1
    assert projection.extraction_quality.fields_covered == 3
