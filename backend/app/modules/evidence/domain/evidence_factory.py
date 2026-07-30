"""Builds immutable `EvidenceRecord`s from an extractor's raw findings.

Pure and deterministic — an injectable `clock: Callable[[], datetime]`
(defaulting to `datetime.now(UTC)`) matches every prior module's
determinism-via-injection precedent. Responsibilities exactly per brief
section 13:

- stable evidence IDs: a deterministic hash of
  `page_id + field_path + selector/json_path + content_hash`, never a
  random UUID (AC-16).
- capture page reference, selector/JSON path when available.
- a concise excerpt capped at 300/120/120 chars (primary/prefix/suffix,
  AC-17), hashing the relevant source fragment with SHA-256 (reusing
  `modules/crawling/domain/hashing.py`'s existing hash choice).
- mark evidence strength, preserve raw and normalized values.
- never store full page HTML (AC-18).
- redact obvious email-tracking tokens and URL query parameters likely to
  contain personal data (AC-19), while preserving business contact
  details verbatim when *those* are the extracted fact.
"""

import hashlib
import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, Field

from app.modules.evidence.domain.enums import EvidenceStatus, EvidenceStrength, EvidenceType
from app.modules.evidence.domain.models import (
    EvidenceExcerpt,
    EvidenceLocation,
    EvidenceRecord,
)

EVIDENCE_FORMAT_VERSION = "v1"

PRIMARY_EXCERPT_CAP = 300
PREFIX_EXCERPT_CAP = 120
SUFFIX_EXCERPT_CAP = 120

# Versioned, documented redaction pattern list (brief section 13).
# Query-string parameter *names* whose values commonly carry
# email-tracking tokens or other personal-data-bearing identifiers.
REDACTED_QUERY_PARAM_NAMES = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_content",
        "utm_term",
        "mc_cid",
        "mc_eid",
        "vero_id",
        "vero_conv",
        "klaviyo_id",
        "_kx",
        "subscriber_id",
        "contact_id",
        "customer_id",
        "email",
        "recipient",
        "uid",
    }
)

_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def redact_url_query(url: str) -> str:
    """Strips known personal-data-bearing query parameters from `url`.

    Never removes the whole query string — only the specific
    tracking-token-shaped parameter names in `REDACTED_QUERY_PARAM_NAMES`.
    """
    parts = urlsplit(url)
    if not parts.query:
        return url
    kept_params = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in REDACTED_QUERY_PARAM_NAMES
    ]
    new_query = urlencode(kept_params)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))


def _redact_emails(text: str, *, preserve: bool) -> str:
    if preserve or not text:
        return text
    return _EMAIL_PATTERN.sub("[redacted-email]", text)


class EvidenceDraft(BaseModel):
    """The pre-ID shape an extractor/candidate produces, before evidence
    IDs are assigned. Every value here is already extraction-owned plain
    data — no live page/HTML object is ever carried through this draft."""

    company_id: str
    extraction_run_id: str
    page_id: str
    fact_field_path: str

    evidence_type: EvidenceType
    strength: EvidenceStrength

    source_url: str
    page_type: str

    extractor_id: str
    extractor_version: str

    location: EvidenceLocation = Field(default_factory=EvidenceLocation)

    # The raw source fragment the excerpt/hash are derived from — never
    # persisted verbatim beyond the capped excerpt built below.
    source_fragment: str
    prefix_context: str = ""
    suffix_context: str = ""

    raw_value: str | None = None
    normalized_value: str | None = None

    observed_at: datetime

    # True only when the extracted fact *is* a business contact detail
    # (e.g. `organisation.emails`/`organisation.phone_numbers`) — the
    # brief's explicit carve-out preserving that value verbatim rather
    # than redacting an email-shaped substring out of it.
    is_business_contact_fact: bool = False

    metadata: dict[str, Any] = Field(default_factory=dict)


def _cap(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def _build_excerpt(draft: EvidenceDraft) -> EvidenceExcerpt:
    preserve = draft.is_business_contact_fact
    primary = _redact_emails(draft.source_fragment, preserve=preserve)
    prefix = _redact_emails(draft.prefix_context, preserve=preserve)
    suffix = _redact_emails(draft.suffix_context, preserve=preserve)

    primary_capped, primary_truncated = _cap(primary, PRIMARY_EXCERPT_CAP)
    prefix_capped, _ = _cap(prefix, PREFIX_EXCERPT_CAP)
    suffix_capped, _ = _cap(suffix, SUFFIX_EXCERPT_CAP)

    return EvidenceExcerpt(
        text=primary_capped,
        prefix=prefix_capped,
        suffix=suffix_capped,
        truncated=primary_truncated,
        start_offset=0,
        end_offset=len(primary_capped),
    )


def _selector_or_json_path(location: EvidenceLocation) -> str:
    return location.selector or location.json_path or location.xpath or location.attribute or ""


def create_evidence_record(
    draft: EvidenceDraft,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> EvidenceRecord:
    content_hash = _sha256(draft.source_fragment)
    evidence_id = _sha256(
        f"{draft.page_id}|{draft.fact_field_path}|"
        f"{_selector_or_json_path(draft.location)}|{content_hash}"
    )

    excerpt = _build_excerpt(draft)
    normalized_source_url = redact_url_query(draft.source_url)

    raw_value = (
        _redact_emails(draft.raw_value or "", preserve=draft.is_business_contact_fact) or None
    )
    normalized_value = (
        _redact_emails(draft.normalized_value or "", preserve=draft.is_business_contact_fact)
        or None
    )

    now = clock()
    return EvidenceRecord(
        evidence_id=evidence_id,
        company_id=draft.company_id,
        extraction_run_id=draft.extraction_run_id,
        page_id=draft.page_id,
        fact_field_path=draft.fact_field_path,
        evidence_type=draft.evidence_type,
        status=EvidenceStatus.ACTIVE,
        strength=draft.strength,
        source_url=draft.source_url,
        normalized_source_url=normalized_source_url,
        page_type=draft.page_type,
        extractor_id=draft.extractor_id,
        extractor_version=draft.extractor_version,
        location=draft.location,
        excerpt=excerpt,
        raw_value=raw_value,
        normalized_value=normalized_value,
        content_hash=content_hash,
        observed_at=draft.observed_at,
        last_verified_at=now,
        created_at=now,
        updated_at=now,
        metadata={**draft.metadata, "evidence_format_version": EVIDENCE_FORMAT_VERSION},
    )
