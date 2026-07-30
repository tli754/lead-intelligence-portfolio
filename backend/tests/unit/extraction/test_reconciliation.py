"""Unit tests for the reconciliation engine (AC-22 through AC-27)."""

from datetime import UTC, datetime

from app.modules.extraction.domain.enums import FactSourceType, FactStatus, VerificationState
from app.modules.extraction.domain.field_catalogue import FIELD_CATALOGUE, FieldPath, FieldValueType
from app.modules.extraction.domain.models import FactCandidate, FactRecord
from app.modules.extraction.domain.reconciliation import group_candidates, reconcile_candidates

NOW = datetime(2026, 7, 26, tzinfo=UTC)


def _candidate(
    field_path: FieldPath,
    *,
    value,
    confidence: int,
    source_type: FactSourceType = FactSourceType.HTML_ELEMENT,
    verification_state: VerificationState = VerificationState.MEASURED,
    evidence_ids: list[str] | None = None,
    qualifiers: dict | None = None,
    page_id: str = "page-1",
    value_type: FieldValueType | None = None,
) -> FactCandidate:
    definition = FIELD_CATALOGUE[field_path]
    return FactCandidate(
        extraction_run_id="run-1",
        company_id="company-1",
        page_id=page_id,
        field_path=field_path,
        value=value,
        normalized_value=value,
        value_type=value_type or definition.value_type,
        source_type=source_type,
        extractor_id="test-extractor",
        extractor_version="v1",
        confidence=confidence,
        verification_state=verification_state,
        evidence_ids=evidence_ids or ["evidence-1"],
        qualifiers=qualifiers or {},
        observed_at=NOW,
        created_at=NOW,
    )


def test_agreeing_scalars_merge():
    candidates = [
        _candidate(
            FieldPath.IDENTITY_COMPANY_NAME,
            value="Acme Corporation",
            confidence=85,
            source_type=FactSourceType.JSON_LD,
            evidence_ids=["e1"],
        ),
        _candidate(
            FieldPath.IDENTITY_COMPANY_NAME,
            value="Acme Corporation",
            confidence=88,
            source_type=FactSourceType.JSON_LD,
            evidence_ids=["e2"],
            page_id="page-2",
        ),
    ]
    outcome = reconcile_candidates(
        candidates, field_definition=FIELD_CATALOGUE[FieldPath.IDENTITY_COMPANY_NAME]
    )
    assert outcome.accepted_fact is not None
    assert outcome.accepted_fact.source_count >= 2
    assert outcome.accepted_fact.status == FactStatus.ACCEPTED


def test_conflicting_strong_scalars_preserved():
    candidates = [
        _candidate(
            FieldPath.IDENTITY_COMPANY_NAME,
            value="Acme Corp",
            confidence=85,
            source_type=FactSourceType.JSON_LD,
        ),
        _candidate(
            FieldPath.IDENTITY_COMPANY_NAME,
            value="Zenith Trading",
            confidence=85,
            source_type=FactSourceType.JSON_LD,
            page_id="page-2",
        ),
    ]
    outcome = reconcile_candidates(
        candidates, field_definition=FIELD_CATALOGUE[FieldPath.IDENTITY_COMPANY_NAME]
    )
    assert outcome.accepted_fact is not None
    assert outcome.accepted_fact.status == FactStatus.CONFLICTING
    assert outcome.conflict is not None
    assert set(outcome.conflict.candidate_ids) == {c.candidate_id for c in candidates}


def test_manual_override():
    candidates = [
        _candidate(
            FieldPath.IDENTITY_COMPANY_NAME,
            value="Weak Guess Co",
            confidence=40,
            source_type=FactSourceType.DETERMINISTIC_INFERENCE,
        ),
        _candidate(
            FieldPath.IDENTITY_COMPANY_NAME,
            value="Verified Manual Co",
            confidence=60,
            source_type=FactSourceType.MANUAL,
        ),
    ]
    outcome = reconcile_candidates(
        candidates, field_definition=FIELD_CATALOGUE[FieldPath.IDENTITY_COMPANY_NAME]
    )
    assert outcome.accepted_fact is not None
    assert outcome.accepted_fact.normalized_value == "Verified Manual Co"
    assert outcome.accepted_fact.verification_state == VerificationState.VERIFIED


def test_jsonld_beats_title():
    candidates = [
        _candidate(
            FieldPath.IDENTITY_COMPANY_NAME,
            value="Title Inference Co",
            confidence=55,
            source_type=FactSourceType.HTML_ELEMENT,
        ),
        _candidate(
            FieldPath.IDENTITY_COMPANY_NAME,
            value="JSON-LD Co",
            confidence=90,
            source_type=FactSourceType.JSON_LD,
            page_id="page-2",
        ),
    ]
    outcome = reconcile_candidates(
        candidates, field_definition=FIELD_CATALOGUE[FieldPath.IDENTITY_COMPANY_NAME]
    )
    assert outcome.accepted_fact is not None
    assert outcome.accepted_fact.normalized_value == "JSON-LD Co"
    assert outcome.conflict is None


def test_exact_beats_estimate():
    candidates = [
        _candidate(
            FieldPath.CATALOGUE_PRODUCT_COUNT,
            value=120,
            confidence=60,
            source_type=FactSourceType.DETERMINISTIC_INFERENCE,
            qualifiers={"estimation_method": "sampled_collection", "sample_size": 12},
        ),
        _candidate(
            FieldPath.CATALOGUE_PRODUCT_COUNT,
            value=118,
            confidence=90,
            source_type=FactSourceType.SITEMAP_SUMMARY,
            qualifiers={"estimation_method": "exact", "exact": True},
            page_id="page-2",
        ),
    ]
    outcome = reconcile_candidates(
        candidates, field_definition=FIELD_CATALOGUE[FieldPath.CATALOGUE_PRODUCT_COUNT]
    )
    assert outcome.accepted_fact is not None
    assert outcome.accepted_fact.normalized_value == 118
    assert outcome.accepted_fact.qualifiers.get("exact") is True


def test_competing_exact_counts_conflict():
    candidates = [
        _candidate(
            FieldPath.CATALOGUE_PRODUCT_COUNT,
            value=100,
            confidence=88,
            source_type=FactSourceType.SITEMAP_SUMMARY,
            qualifiers={"exact": True},
        ),
        _candidate(
            FieldPath.CATALOGUE_PRODUCT_COUNT,
            value=140,
            confidence=82,
            source_type=FactSourceType.JSON_LD,
            qualifiers={"exact": True},
            page_id="page-2",
        ),
    ]
    outcome = reconcile_candidates(
        candidates, field_definition=FIELD_CATALOGUE[FieldPath.CATALOGUE_PRODUCT_COUNT]
    )
    assert outcome.accepted_fact is not None
    assert outcome.accepted_fact.status == FactStatus.CONFLICTING
    assert outcome.conflict is not None


def test_technology_set_union_per_item_confidence():
    candidates = [
        _candidate(
            FieldPath.TECHNOLOGY_COMMERCE_PLATFORM,
            value="shopify",
            confidence=85,
            source_type=FactSourceType.SCRIPT_MARKER,
            qualifiers={"dedup_key": "shopify"},
            page_id="page-1",
        ),
        _candidate(
            FieldPath.TECHNOLOGY_COMMERCE_PLATFORM,
            value="shopify",
            confidence=80,
            source_type=FactSourceType.SCRIPT_MARKER,
            qualifiers={"dedup_key": "shopify"},
            page_id="page-2",
        ),
        _candidate(
            FieldPath.TECHNOLOGY_COMMERCE_PLATFORM,
            value="hubspot",
            confidence=75,
            source_type=FactSourceType.SCRIPT_MARKER,
            qualifiers={"dedup_key": "hubspot"},
            page_id="page-3",
        ),
    ]
    outcome = reconcile_candidates(
        candidates, field_definition=FIELD_CATALOGUE[FieldPath.TECHNOLOGY_COMMERCE_PLATFORM]
    )
    assert outcome.accepted_fact is not None
    values = {item["value"] for item in outcome.accepted_fact.normalized_value}
    assert values == {"shopify", "hubspot"}
    shopify_item = next(
        item for item in outcome.accepted_fact.normalized_value if item["value"] == "shopify"
    )
    assert shopify_item["confidence"] == 85
    assert shopify_item["source_count"] == 2


def test_unknown_when_below_threshold():
    candidates = [
        _candidate(
            FieldPath.BUSINESS_WHOLESALE,
            value=True,
            confidence=10,
            source_type=FactSourceType.HTML_ELEMENT,
        )
    ]
    outcome = reconcile_candidates(
        candidates, field_definition=FIELD_CATALOGUE[FieldPath.BUSINESS_WHOLESALE]
    )
    assert outcome.accepted_fact is None


def test_boolean_false_requires_explicit_evidence():
    # No candidate at all suggests `false` for wholesale — only a positive
    # signal exists, so `false` must never be emitted from its absence.
    candidates = [
        _candidate(
            FieldPath.BUSINESS_WHOLESALE,
            value=True,
            confidence=80,
            source_type=FactSourceType.HTML_ELEMENT,
        )
    ]
    outcome = reconcile_candidates(
        candidates, field_definition=FIELD_CATALOGUE[FieldPath.BUSINESS_WHOLESALE]
    )
    assert outcome.accepted_fact is not None
    assert outcome.accepted_fact.normalized_value is True


def test_explicit_false_accepted_with_evidence():
    candidates = [
        _candidate(
            FieldPath.BUSINESS_WHOLESALE,
            value=False,
            confidence=75,
            source_type=FactSourceType.HTML_ELEMENT,
        )
    ]
    outcome = reconcile_candidates(
        candidates, field_definition=FIELD_CATALOGUE[FieldPath.BUSINESS_WHOLESALE]
    )
    assert outcome.accepted_fact is not None
    assert outcome.accepted_fact.normalized_value is False


def test_rule_ids_preserved_on_accepted_fact():
    candidates = [
        _candidate(FieldPath.BUSINESS_WHOLESALE, value=True, confidence=80),
    ]
    outcome = reconcile_candidates(
        candidates, field_definition=FIELD_CATALOGUE[FieldPath.BUSINESS_WHOLESALE]
    )
    assert outcome.accepted_fact is not None
    assert outcome.accepted_fact.reconciliation_rule_ids


def test_evidence_references_preserved():
    candidates = [
        _candidate(FieldPath.BUSINESS_WHOLESALE, value=True, confidence=80, evidence_ids=["e-abc"]),
    ]
    outcome = reconcile_candidates(
        candidates, field_definition=FIELD_CATALOGUE[FieldPath.BUSINESS_WHOLESALE]
    )
    assert outcome.accepted_fact is not None
    assert "e-abc" in outcome.accepted_fact.evidence_ids


def test_group_candidates_by_company_and_field():
    candidates = [
        _candidate(FieldPath.BUSINESS_WHOLESALE, value=True, confidence=80),
        _candidate(FieldPath.IDENTITY_COMPANY_NAME, value="Acme", confidence=80),
    ]
    groups = group_candidates(candidates)
    assert len(groups) == 2


def test_supersession_signal_when_value_changes():
    existing = FactRecord(
        company_id="company-1",
        extraction_run_id="run-0",
        field_path=FieldPath.IDENTITY_COMPANY_NAME,
        value="Old Name",
        normalized_value="Old Name",
        value_type=FieldValueType.STRING,
        status=FactStatus.ACCEPTED,
        verification_state=VerificationState.VERIFIED,
        confidence=80,
        selected_candidate_ids=["old-candidate"],
        first_observed_at=NOW,
        last_observed_at=NOW,
        last_verified_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    candidates = [
        _candidate(
            FieldPath.IDENTITY_COMPANY_NAME,
            value="New Name",
            confidence=90,
            source_type=FactSourceType.JSON_LD,
        )
    ]
    outcome = reconcile_candidates(
        candidates,
        field_definition=FIELD_CATALOGUE[FieldPath.IDENTITY_COMPANY_NAME],
        existing_fact=existing,
    )
    assert outcome.superseded_candidate_ids == ["old-candidate"]
