"""Unit tests for the evidence factory (AC-16 through AC-20)."""

from datetime import UTC, datetime
from typing import Any

from app.modules.evidence.domain.enums import EvidenceStatus, EvidenceStrength, EvidenceType
from app.modules.evidence.domain.evidence_factory import (
    PREFIX_EXCERPT_CAP,
    PRIMARY_EXCERPT_CAP,
    SUFFIX_EXCERPT_CAP,
    EvidenceDraft,
    create_evidence_record,
)
from app.modules.evidence.domain.models import EvidenceLocation
from app.modules.evidence.domain.repository import EvidenceRepository


def _draft(**overrides: Any) -> EvidenceDraft:
    defaults: dict[str, Any] = dict(
        company_id="company-1",
        extraction_run_id="run-1",
        page_id="page-1",
        fact_field_path="identity.company_name",
        evidence_type=EvidenceType.JSON_LD,
        strength=EvidenceStrength.AUTHORITATIVE,
        source_url="https://example.com/about",
        page_type="about",
        extractor_id="identity.company_name",
        extractor_version="v1",
        location=EvidenceLocation(json_path="$.name"),
        source_fragment="Acme Corporation",
        prefix_context="",
        suffix_context="",
        raw_value="Acme Corporation",
        normalized_value="acme corporation",
        observed_at=datetime(2026, 7, 26, tzinfo=UTC),
    )
    defaults.update(overrides)
    return EvidenceDraft(**defaults)


def test_deterministic_evidence_id():
    first = create_evidence_record(_draft())
    second = create_evidence_record(_draft())
    assert first.evidence_id == second.evidence_id


def test_different_content_produces_different_evidence_id():
    first = create_evidence_record(_draft())
    second = create_evidence_record(_draft(source_fragment="Different Corp"))
    assert first.evidence_id != second.evidence_id


def test_excerpt_length_caps():
    long_text = "x" * (PRIMARY_EXCERPT_CAP + 50)
    long_prefix = "p" * (PREFIX_EXCERPT_CAP + 50)
    long_suffix = "s" * (SUFFIX_EXCERPT_CAP + 50)
    record = create_evidence_record(
        _draft(source_fragment=long_text, prefix_context=long_prefix, suffix_context=long_suffix)
    )
    assert len(record.excerpt.text) == PRIMARY_EXCERPT_CAP
    assert record.excerpt.truncated is True
    assert len(record.excerpt.prefix) == PREFIX_EXCERPT_CAP
    assert len(record.excerpt.suffix) == SUFFIX_EXCERPT_CAP


def test_short_excerpt_not_truncated():
    record = create_evidence_record(_draft(source_fragment="short"))
    assert record.excerpt.truncated is False


def test_selector_and_json_path_location_preserved():
    record = create_evidence_record(
        _draft(location=EvidenceLocation(selector=".logo", json_path=None))
    )
    assert record.location.selector == ".logo"


def test_no_full_html_stored():
    html_fragment = "<html><body>" + ("<p>content</p>" * 100) + "</body></html>"
    record = create_evidence_record(_draft(source_fragment=html_fragment))
    assert "<html>" not in record.excerpt.text or len(record.excerpt.text) <= PRIMARY_EXCERPT_CAP
    assert len(record.excerpt.text) <= PRIMARY_EXCERPT_CAP


def test_url_query_redaction():
    record = create_evidence_record(
        _draft(source_url="https://example.com/?utm_source=newsletter&mc_eid=abc123&page=2")
    )
    assert "utm_source" not in record.normalized_source_url
    assert "mc_eid" not in record.normalized_source_url
    assert "page=2" in record.normalized_source_url
    # The original, unredacted URL is still preserved on `source_url`.
    assert record.source_url == "https://example.com/?utm_source=newsletter&mc_eid=abc123&page=2"


def test_business_contact_preserved():
    record = create_evidence_record(
        _draft(
            fact_field_path="organisation.emails",
            source_fragment="Contact us at sales@example.com for wholesale enquiries.",
            raw_value="sales@example.com",
            normalized_value="sales@example.com",
            is_business_contact_fact=True,
        )
    )
    assert "sales@example.com" in record.excerpt.text
    assert record.raw_value == "sales@example.com"


def test_non_contact_email_redacted_from_excerpt():
    record = create_evidence_record(
        _draft(
            fact_field_path="identity.company_name",
            source_fragment="As reviewed by customer jane.doe@example.com in our testimonials.",
            is_business_contact_fact=False,
        )
    )
    assert "jane.doe@example.com" not in record.excerpt.text
    assert "[redacted-email]" in record.excerpt.text


def test_immutability_by_construction():
    """`EvidenceRepository`'s only mutating method is `update_evidence_status`
    — a genuine content change must create a new evidence record instead."""
    mutating_methods = {
        name
        for name in dir(EvidenceRepository)
        if not name.startswith("_") and name not in ("save_evidence",)
    }
    write_methods = {name for name in mutating_methods if name.startswith(("update_", "delete_"))}
    assert write_methods == {"update_evidence_status"}


def test_status_defaults_to_active():
    record = create_evidence_record(_draft())
    assert record.status == EvidenceStatus.ACTIVE
