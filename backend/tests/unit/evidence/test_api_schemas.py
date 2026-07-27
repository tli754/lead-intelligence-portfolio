"""Unit tests for the evidence-module API schemas — camelCase shape only."""

from datetime import UTC, datetime
from typing import Any

from app.modules.evidence.api.schemas import evidence_to_response
from app.modules.evidence.domain.enums import EvidenceStatus, EvidenceStrength, EvidenceType
from app.modules.evidence.domain.models import EvidenceExcerpt, EvidenceRecord

NOW = datetime(2026, 7, 26, tzinfo=UTC)


def _evidence(**overrides: Any) -> EvidenceRecord:
    defaults: dict[str, Any] = dict(
        company_id="company-1",
        extraction_run_id="run-1",
        page_id="page-1",
        fact_field_path="identity.company_name",
        evidence_type=EvidenceType.JSON_LD,
        strength=EvidenceStrength.AUTHORITATIVE,
        source_url="https://example.com/",
        normalized_source_url="https://example.com/",
        page_type="homepage",
        extractor_id="identity.company_name",
        extractor_version="v1",
        excerpt=EvidenceExcerpt(text="Acme Corporation"),
        content_hash="abc123",
        observed_at=NOW,
        last_verified_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    defaults.update(overrides)
    return EvidenceRecord(**defaults)


def test_evidence_response_is_camel_case():
    payload = evidence_to_response(_evidence()).model_dump(by_alias=True)
    assert "evidenceId" in payload
    assert "factFieldPath" in payload
    assert "fact_field_path" not in payload


def test_evidence_response_excerpt_only_no_full_html():
    payload = evidence_to_response(_evidence()).model_dump(by_alias=True)
    assert payload["excerpt"]["text"] == "Acme Corporation"
    assert "<html" not in payload["excerpt"]["text"]


def test_evidence_response_includes_source_url():
    payload = evidence_to_response(_evidence()).model_dump(by_alias=True)
    assert payload["sourceUrl"] == "https://example.com/"


def test_evidence_status_enum_serialization():
    payload = evidence_to_response(_evidence(status=EvidenceStatus.STALE)).model_dump(by_alias=True)
    assert payload["status"] == "stale"
