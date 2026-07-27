"""Centralized regex pattern rules for the physical-operations extractor family."""

import re

from app.modules.evidence.domain.enums import EvidenceStrength
from app.modules.extraction.domain.field_catalogue import FieldPath
from app.modules.extraction.domain.pattern_types import PatternRule

PATTERN_RULES_VERSION = "v1"

PICKUP_AVAILABLE_RULE = PatternRule(
    rule_id="operations.pickup_available.explicit_offer",
    version=PATTERN_RULES_VERSION,
    field_path=FieldPath.OPERATIONS_PICKUP_AVAILABLE,
    positive_patterns=(
        re.compile(r"\bpickup\s+(?:is\s+)?available\b", re.IGNORECASE),
        re.compile(r"\bcurbside\s+pickup\b", re.IGNORECASE),
        re.compile(r"\bin-?store\s+pickup\b", re.IGNORECASE),
    ),
    base_confidence=75,
    evidence_strength=EvidenceStrength.STRONG,
    notes="Explicit pickup-location wording.",
)

WAREHOUSE_WORDING_RULE = PatternRule(
    rule_id="operations.warehouse_count.explicit_wording",
    version=PATTERN_RULES_VERSION,
    field_path=FieldPath.OPERATIONS_WAREHOUSE_COUNT,
    positive_patterns=(re.compile(r"\bwarehouse\b", re.IGNORECASE),),
    base_confidence=55,
    evidence_strength=EvidenceStrength.WEAK,
    notes="Bare 'warehouse' mention — used only as page-level classification support.",
)

SHOWROOM_WORDING_RULE = PatternRule(
    rule_id="operations.showroom_count.explicit_wording",
    version=PATTERN_RULES_VERSION,
    field_path=FieldPath.OPERATIONS_SHOWROOM_COUNT,
    positive_patterns=(re.compile(r"\bshowroom\b", re.IGNORECASE),),
    base_confidence=55,
    evidence_strength=EvidenceStrength.WEAK,
    notes="Bare 'showroom' mention — used only as page-level classification support.",
)

STOCKIST_WORDING_RULE = PatternRule(
    rule_id="operations.locations.stockist_wording",
    version=PATTERN_RULES_VERSION,
    field_path=FieldPath.OPERATIONS_LOCATIONS,
    positive_patterns=(
        re.compile(r"\bstockists?\b", re.IGNORECASE),
        re.compile(r"\bfind\s+us\s+at\s+these\s+retailers\b", re.IGNORECASE),
        re.compile(r"\bavailable\s+at\s+these\s+retailers\b", re.IGNORECASE),
    ),
    base_confidence=70,
    evidence_strength=EvidenceStrength.MODERATE,
    notes="Page-level wording distinguishing third-party stockists from company-owned stores.",
)

PATTERN_RULES: dict[str, PatternRule] = {
    rule.rule_id: rule
    for rule in (
        PICKUP_AVAILABLE_RULE,
        WAREHOUSE_WORDING_RULE,
        SHOWROOM_WORDING_RULE,
        STOCKIST_WORDING_RULE,
    )
}
