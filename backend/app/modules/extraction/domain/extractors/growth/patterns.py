"""Centralized regex pattern rules for the growth-signal extractor family.

`HIRING_RULE` requires supporting-growth context (`context_requirements`)
so a single, routine job-vacancy posting is never treated as a major
expansion signal on its own (brief section 11's explicit false-positive-
prevention rule / AC-14).
"""

import re

from app.modules.evidence.domain.enums import EvidenceStrength
from app.modules.extraction.domain.field_catalogue import FieldPath
from app.modules.extraction.domain.pattern_types import PatternRule

PATTERN_RULES_VERSION = "v1"

HIRING_RULE = PatternRule(
    rule_id="growth.hiring.expansion_context",
    version=PATTERN_RULES_VERSION,
    field_path=FieldPath.GROWTH_HIRING,
    positive_patterns=(
        re.compile(r"\bwe(?:'|’)re\s+hiring\b", re.IGNORECASE),
        re.compile(r"\bjoin\s+our\s+growing\s+team\b", re.IGNORECASE),
        re.compile(r"\bmultiple\s+(?:roles|positions)\s+available\b", re.IGNORECASE),
    ),
    context_requirements=(
        re.compile(r"\b(?:growing|growth|expand(?:ing|sion)?|scaling)\b", re.IGNORECASE),
    ),
    base_confidence=68,
    evidence_strength=EvidenceStrength.MODERATE,
    notes="Requires nearby growth/expansion wording; a single generic vacancy never matches alone.",
)

NEW_STORE_RULE = PatternRule(
    rule_id="growth.new_store.opening_announcement",
    version=PATTERN_RULES_VERSION,
    field_path=FieldPath.GROWTH_NEW_STORE,
    positive_patterns=(
        re.compile(r"\bopening\s+(?:a\s+)?new\s+store\b", re.IGNORECASE),
        re.compile(r"\bnew\s+store\s+now\s+open\b", re.IGNORECASE),
        re.compile(r"\bwe(?:'|’)ve\s+opened\s+a\s+new\s+location\b", re.IGNORECASE),
    ),
    base_confidence=75,
    evidence_strength=EvidenceStrength.STRONG,
    notes="Explicit new-store-opening announcement.",
)

WAREHOUSE_CHANGE_RULE = PatternRule(
    rule_id="growth.warehouse_change.move_announcement",
    version=PATTERN_RULES_VERSION,
    field_path=FieldPath.GROWTH_WAREHOUSE_CHANGE,
    positive_patterns=(
        re.compile(
            r"\bmoving\s+(?:to\s+)?(?:a\s+)?(?:new|bigger|larger)\s+warehouse\b", re.IGNORECASE
        ),
        re.compile(r"\bnew\s+distribution\s+centre?\b", re.IGNORECASE),
    ),
    base_confidence=72,
    evidence_strength=EvidenceStrength.STRONG,
    notes="Explicit warehouse relocation/expansion announcement.",
)

EXPANSION_RULE = PatternRule(
    rule_id="growth.expansion.distribution_or_acquisition",
    version=PATTERN_RULES_VERSION,
    field_path=FieldPath.GROWTH_EXPANSION,
    positive_patterns=(
        re.compile(r"\bexpanding\s+(?:our\s+)?distribution\b", re.IGNORECASE),
        re.compile(r"\binternational\s+expansion\b", re.IGNORECASE),
        re.compile(r"\bnow\s+shipping\s+(?:internationally|to\s+[A-Z][a-z]+)\b", re.IGNORECASE),
        re.compile(r"\backquir(?:ed|ing|es|e)\b", re.IGNORECASE),
        re.compile(r"\bmerger\b", re.IGNORECASE),
        re.compile(r"\brebrand(?:ed|ing)?\b", re.IGNORECASE),
    ),
    base_confidence=70,
    evidence_strength=EvidenceStrength.MODERATE,
    notes="Distribution/international expansion, acquisition/merger, and rebrand wording.",
)

PLATFORM_MIGRATION_RULE = PatternRule(
    rule_id="growth.platform_migration.explicit_statement",
    version=PATTERN_RULES_VERSION,
    field_path=FieldPath.GROWTH_PLATFORM_MIGRATION,
    positive_patterns=(
        re.compile(r"\bwe(?:'|’)ve\s+moved\s+to\s+[A-Z][\w]*\b"),
        re.compile(r"\bmigrat(?:ed|ing)\s+to\s+a\s+new\s+platform\b", re.IGNORECASE),
    ),
    base_confidence=72,
    evidence_strength=EvidenceStrength.STRONG,
    notes="Explicit commerce-platform migration announcement.",
)

NEW_CATEGORY_RULE = PatternRule(
    rule_id="growth.new_category.explicit_launch",
    version=PATTERN_RULES_VERSION,
    field_path=FieldPath.GROWTH_NEW_CATEGORY,
    positive_patterns=(
        re.compile(r"\bnow\s+launching\s+(?:our\s+)?new\s+[a-z]+\s+range\b", re.IGNORECASE),
        re.compile(r"\bintroducing\s+(?:our\s+)?new\s+category\b", re.IGNORECASE),
    ),
    base_confidence=70,
    evidence_strength=EvidenceStrength.MODERATE,
    notes="Explicit new-product-category entry wording.",
)

SUBSCRIPTION_LAUNCH_RULE = PatternRule(
    rule_id="growth.subscription_launch.explicit_launch",
    version=PATTERN_RULES_VERSION,
    field_path=FieldPath.GROWTH_SUBSCRIPTION_LAUNCH,
    positive_patterns=(
        re.compile(r"\blaunching\s+(?:our\s+)?(?:new\s+)?subscription\b", re.IGNORECASE),
        re.compile(r"\bnow\s+offering\s+subscriptions\b", re.IGNORECASE),
    ),
    base_confidence=72,
    evidence_strength=EvidenceStrength.STRONG,
    notes="Explicit subscription-program launch announcement.",
)

PATTERN_RULES: dict[str, PatternRule] = {
    rule.rule_id: rule
    for rule in (
        HIRING_RULE,
        NEW_STORE_RULE,
        WAREHOUSE_CHANGE_RULE,
        EXPANSION_RULE,
        PLATFORM_MIGRATION_RULE,
        NEW_CATEGORY_RULE,
        SUBSCRIPTION_LAUNCH_RULE,
    )
}
