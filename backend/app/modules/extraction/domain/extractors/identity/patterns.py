"""Centralized regex pattern rules for the identity extractor family."""

import re

from app.modules.discovery.domain.enums import PageType
from app.modules.evidence.domain.enums import EvidenceStrength
from app.modules.extraction.domain.field_catalogue import FieldPath
from app.modules.extraction.domain.pattern_types import PatternRule

PATTERN_RULES_VERSION = "v1"

TITLE_SEPARATOR_PATTERN = PatternRule(
    rule_id="identity.company_name.title_pattern",
    version=PATTERN_RULES_VERSION,
    field_path=FieldPath.IDENTITY_COMPANY_NAME,
    positive_patterns=(re.compile(r"^\s*(?P<name>[^|\-–—:]{2,80}?)\s*[|\-–—:]"),),
    base_confidence=55,
    evidence_strength=EvidenceStrength.WEAK,
    notes="Text before the first separator in a homepage <title>. Deliberately low confidence.",
    supported_page_types=(PageType.HOMEPAGE,),
)

TRADING_AS_PATTERN = PatternRule(
    rule_id="identity.trading_name.trading_as_phrase",
    version=PATTERN_RULES_VERSION,
    field_path=FieldPath.IDENTITY_TRADING_NAME,
    positive_patterns=(
        re.compile(r"trading\s+as\s+(?P<name>[A-Z][\w&'.\- ]{1,60})", re.IGNORECASE),
    ),
    base_confidence=72,
    evidence_strength=EvidenceStrength.MODERATE,
    notes="Explicit 'trading as <Name>' wording, from footer legal text or about copy.",
)
