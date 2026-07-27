"""Centralized regex pattern rules for the organisation/contact extractor family."""

import re

from app.modules.evidence.domain.enums import EvidenceStrength
from app.modules.extraction.domain.field_catalogue import FieldPath
from app.modules.extraction.domain.pattern_types import PatternRule

PATTERN_RULES_VERSION = "v1"

EMAIL_TEXT_PATTERN = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE_TEXT_PATTERN = re.compile(r"(?:\+?\d[\d\s().\-]{7,}\d)")

INTERNAL_IT_DETECTED_RULE = PatternRule(
    rule_id="organisation.internal_it_status.explicit_technical_staff",
    version=PATTERN_RULES_VERSION,
    field_path=FieldPath.ORGANISATION_INTERNAL_IT_STATUS,
    positive_patterns=(
        re.compile(
            r"\b(?:head\s+of\s+engineering|software\s+engineer|"
            r"in[\s-]house\s+develop(?:er|ment)|internal\s+it\s+team|"
            r"technology\s+lead|engineering\s+careers|"
            r"we\s+are\s+hiring\s+(?:a\s+)?developers?)\b",
            re.IGNORECASE,
        ),
    ),
    base_confidence=72,
    evidence_strength=EvidenceStrength.MODERATE,
    notes="Explicit technical-staff/engineering wording. Absence never implies not_detected.",
)

EXTERNAL_AGENCY_RULE = PatternRule(
    rule_id="organisation.internal_it_status.agency_credit",
    version=PATTERN_RULES_VERSION,
    field_path=FieldPath.ORGANISATION_INTERNAL_IT_STATUS,
    positive_patterns=(re.compile(r"\bsite\s+by\s+[A-Z][\w& ]{1,40}\b", re.IGNORECASE),),
    base_confidence=40,
    evidence_strength=EvidenceStrength.WEAK,
    notes="Agency-credit wording supports external maintenance; never proves not_detected.",
)

PATTERN_RULES: dict[str, PatternRule] = {
    rule.rule_id: rule for rule in (INTERNAL_IT_DETECTED_RULE, EXTERNAL_AGENCY_RULE)
}
