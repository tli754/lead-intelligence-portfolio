"""Centralized regex pattern rules for the business-model extractor family.

Every boolean-capability signal here is a *positive-only* pattern list —
matching one of these never implies `false`; only an explicit
`NEGATIVE_STATEMENT_PATTERNS` entry (or a manual override) can produce a
`false` fact, per brief section 6's explicit "false requires explicit
negative evidence or manual confirmation."

`\\btrade\\b` alone is deliberately never used as a positive pattern — every
`trade_accounts` pattern requires an accompanying qualifier word
("account", "application", "pricing", "professional", "commercial") in
the same match, preventing a bare navigation-label "Trade" from matching
(AC-06 / brief's explicit "avoid ... one ambiguous keyword as strong
evidence").
"""

import re

from app.modules.evidence.domain.enums import EvidenceStrength
from app.modules.extraction.domain.field_catalogue import FieldPath
from app.modules.extraction.domain.pattern_types import PatternRule

PATTERN_RULES_VERSION = "v1"


def _rule(
    rule_id: str,
    field_path: FieldPath,
    patterns: tuple[str, ...],
    *,
    base_confidence: int,
    strength: EvidenceStrength,
    notes: str,
    negative: tuple[str, ...] = (),
) -> PatternRule:
    return PatternRule(
        rule_id=rule_id,
        version=PATTERN_RULES_VERSION,
        field_path=field_path,
        positive_patterns=tuple(re.compile(p, re.IGNORECASE) for p in patterns),
        negative_patterns=tuple(re.compile(p, re.IGNORECASE) for p in negative),
        base_confidence=base_confidence,
        evidence_strength=strength,
        notes=notes,
    )


WHOLESALE_RULE = _rule(
    "business.wholesale.explicit_program",
    FieldPath.BUSINESS_WHOLESALE,
    (
        r"\bwholesale\s+application\b",
        r"\bwholesale\s+enquir(?:y|ies)\b",
        r"\bbecome\s+a\s+stockist\b",
        r"\bwholesale\s+pricing\b",
        r"\bretailer\s+application\b",
        r"\bwholesale\s+account\s+login\b",
    ),
    base_confidence=80,
    strength=EvidenceStrength.STRONG,
    notes="Explicit wholesale-program wording — never a bare 'wholesale' mention.",
)

TRADE_ACCOUNTS_RULE = _rule(
    "business.trade_accounts.explicit_program",
    FieldPath.BUSINESS_TRADE_ACCOUNTS,
    (
        r"\btrade\s+account\b",
        r"\btrade\s+application\b",
        r"\btrade\s+pricing\b",
        r"\bprofessional\s+account\b",
        r"\bcommercial\s+account\b",
    ),
    base_confidence=78,
    strength=EvidenceStrength.STRONG,
    notes="Requires an accompanying qualifier word; bare 'trade' never matches.",
)

CLICK_AND_COLLECT_RULE = _rule(
    "business.click_and_collect.explicit_offer",
    FieldPath.BUSINESS_CLICK_AND_COLLECT,
    (
        r"\bclick\s*(?:and|&)\s*collect\b",
        r"\bstore\s+pickup\b",
        r"\bpick\s*up\s+in\s+store\b",
        r"\bcollection\s+available\b",
    ),
    base_confidence=78,
    strength=EvidenceStrength.STRONG,
    notes="Explicit click-and-collect / in-store pickup wording.",
)

SUBSCRIPTION_RULE = _rule(
    "business.subscription.explicit_offer",
    FieldPath.BUSINESS_SUBSCRIPTION,
    (
        r"\bsubscribe\s*(?:and|&)\s*save\b",
        r"\brecurring\s+delivery\b",
        r"\bproduct\s+subscription\b",
        r"\bmembership\s+delivery\s+plan\b",
    ),
    base_confidence=78,
    strength=EvidenceStrength.STRONG,
    notes="Explicit recurring/subscription-purchase wording.",
)

BOOKING_RULE = _rule(
    "business.booking.explicit_offer",
    FieldPath.BUSINESS_BOOKING,
    (
        r"\bbook\s+(?:an\s+)?appointment\b",
        r"\bbooking\s+form\b",
        r"\bschedule\s+a?\s*consultation\b",
        r"\breserve\s+(?:a\s+)?session\b",
    ),
    base_confidence=75,
    strength=EvidenceStrength.STRONG,
    notes="Explicit appointment/consultation booking wording.",
)

ONLINE_ONLY_RULE = _rule(
    "business.online_only.explicit_statement",
    FieldPath.BUSINESS_ONLINE_ONLY,
    (
        r"\bonline[\s-]only\s+store\b",
        r"\bexclusively\s+online\b",
        r"\bno\s+physical\s+retail\s+location\b",
    ),
    base_confidence=80,
    strength=EvidenceStrength.STRONG,
    notes="Only accepted from an explicit statement — never inferred from a missing store page.",
)

CUSTOM_PRODUCTS_RULE = _rule(
    "business.custom_products.explicit_offer",
    FieldPath.BUSINESS_CUSTOM_PRODUCTS,
    (
        r"\bpersonali[sz]ation\b",
        r"\bcustom\s+engraving\b",
        r"\bmade\s+to\s+order\b",
        r"\bcustom\s+printing\b",
        r"\bbespoke\s+product\b",
        r"\bupload\s+(?:your\s+)?artwork\b",
    ),
    base_confidence=72,
    strength=EvidenceStrength.MODERATE,
    notes="Explicit personalization/made-to-order wording.",
)

# `false`-eligible negative statements — one per boolean business field,
# only ever matched explicitly (never derived from absence).
NEGATIVE_STATEMENT_RULES: dict[FieldPath, PatternRule] = {
    FieldPath.BUSINESS_WHOLESALE: _rule(
        "business.wholesale.explicit_negative",
        FieldPath.BUSINESS_WHOLESALE,
        (r"\bwe\s+do\s+not\s+offer\s+wholesale\b", r"\bno\s+wholesale\s+program\b"),
        base_confidence=75,
        strength=EvidenceStrength.STRONG,
        notes="Explicit denial of a wholesale program.",
    ),
    FieldPath.BUSINESS_CLICK_AND_COLLECT: _rule(
        "business.click_and_collect.explicit_negative",
        FieldPath.BUSINESS_CLICK_AND_COLLECT,
        (r"\bclick\s*(?:and|&)\s*collect\s+is\s+not\s+available\b",),
        base_confidence=75,
        strength=EvidenceStrength.STRONG,
        notes="Explicit denial of click-and-collect.",
    ),
}

PATTERN_RULES: dict[str, PatternRule] = {
    rule.rule_id: rule
    for rule in (
        WHOLESALE_RULE,
        TRADE_ACCOUNTS_RULE,
        CLICK_AND_COLLECT_RULE,
        SUBSCRIPTION_RULE,
        BOOKING_RULE,
        ONLINE_ONLY_RULE,
        CUSTOM_PRODUCTS_RULE,
        *NEGATIVE_STATEMENT_RULES.values(),
    )
}
