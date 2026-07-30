"""Centralized regex pattern rules for the catalogue extractor family."""

import re

from app.modules.evidence.domain.enums import EvidenceStrength
from app.modules.extraction.domain.field_catalogue import FieldPath
from app.modules.extraction.domain.pattern_types import PatternRule

PATTERN_RULES_VERSION = "v1"

BUNDLE_EVIDENCE_RULE = PatternRule(
    rule_id="catalogue.bundle_evidence.explicit_wording",
    version=PATTERN_RULES_VERSION,
    field_path=FieldPath.CATALOGUE_BUNDLE_EVIDENCE,
    positive_patterns=(
        re.compile(r"\bbundle\b", re.IGNORECASE),
        re.compile(r"\bgift\s+set\b", re.IGNORECASE),
        re.compile(r"\b\d[- ]piece\s+kit\b", re.IGNORECASE),
        re.compile(r"\bmultipack\b", re.IGNORECASE),
        re.compile(r"\bbuild[- ]your[- ]own\b", re.IGNORECASE),
    ),
    base_confidence=65,
    evidence_strength=EvidenceStrength.MODERATE,
    notes="Bundle/set/kit/multipack/build-your-own wording on a product or collection page.",
)

CUSTOMIZATION_TEXT_RULE = PatternRule(
    rule_id="catalogue.customization_evidence.explicit_wording",
    version=PATTERN_RULES_VERSION,
    field_path=FieldPath.CATALOGUE_CUSTOMIZATION_EVIDENCE,
    positive_patterns=(
        re.compile(r"\bpersonali[sz]e\s+(?:this\s+)?(?:item|product)\b", re.IGNORECASE),
        re.compile(r"\bengraving\b", re.IGNORECASE),
        re.compile(r"\bmonogram\b", re.IGNORECASE),
        re.compile(r"\bcustom\s+text\b", re.IGNORECASE),
    ),
    base_confidence=65,
    evidence_strength=EvidenceStrength.MODERATE,
    notes="Explicit personalization/engraving wording, distinct from an actual form control.",
)

PATTERN_RULES: dict[str, PatternRule] = {
    rule.rule_id: rule for rule in (BUNDLE_EVIDENCE_RULE, CUSTOMIZATION_TEXT_RULE)
}
