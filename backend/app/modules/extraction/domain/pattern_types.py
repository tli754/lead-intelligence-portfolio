"""Shared pattern-rule vocabulary for every extractor family's own
`patterns.py` module (brief section 12).

Every pattern rule declares: `rule_id`, `version`, `field_path`, positive
patterns, negative patterns, context requirements, supported page types,
base confidence, evidence strength, and notes — centralized here so every
family's `patterns.py` builds `PatternRule` instances the same way, and
`match_pattern_rule` enforces the brief's explicit "avoid" list itself
(bounded regex with word boundaries, a required context match rather than
a bare keyword hit) rather than leaving that discipline to each family.
"""

import re
from dataclasses import dataclass, field

from app.modules.discovery.domain.enums import PageType
from app.modules.evidence.domain.enums import EvidenceStrength
from app.modules.extraction.domain.field_catalogue import FieldPath
from app.modules.extraction.domain.html_helpers import context_window


@dataclass(frozen=True)
class PatternRule:
    rule_id: str
    version: str
    field_path: FieldPath
    positive_patterns: tuple[re.Pattern[str], ...]
    base_confidence: int
    evidence_strength: EvidenceStrength
    notes: str
    negative_patterns: tuple[re.Pattern[str], ...] = field(default_factory=tuple)
    # Additional patterns, at least one of which must also match within the
    # same context window — prevents an ambiguous bare keyword (e.g. "trade"
    # in a navigation label) from being treated as strong evidence on its
    # own (brief's explicit "avoid ... treating one ambiguous keyword as
    # strong evidence").
    context_requirements: tuple[re.Pattern[str], ...] = field(default_factory=tuple)
    supported_page_types: tuple[PageType, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class PatternMatch:
    rule: PatternRule
    matched_text: str
    start: int
    end: int
    prefix: str
    suffix: str


def _context_satisfied(rule: PatternRule, prefix: str, matched_text: str, suffix: str) -> bool:
    if not rule.context_requirements:
        return True
    window = f"{prefix} {matched_text} {suffix}"
    return any(pattern.search(window) for pattern in rule.context_requirements)


def _negative_hit(rule: PatternRule, prefix: str, matched_text: str, suffix: str) -> bool:
    window = f"{prefix} {matched_text} {suffix}"
    return any(pattern.search(window) for pattern in rule.negative_patterns)


def match_pattern_rule(
    rule: PatternRule,
    text: str,
    *,
    page_type: PageType | None = None,
    context_chars: int = 200,
) -> list[PatternMatch]:
    """Every non-rejected positive match of `rule` in `text`.

    A match is rejected when: `page_type` is set and `rule.supported_page_types`
    is non-empty and doesn't include it, a negative pattern matches within
    the same context window, or `rule.context_requirements` is non-empty
    and none of them match within that window.
    """
    if (
        page_type is not None
        and rule.supported_page_types
        and page_type not in rule.supported_page_types
    ):
        return []

    matches: list[PatternMatch] = []
    for pattern in rule.positive_patterns:
        for match in pattern.finditer(text):
            prefix, suffix = context_window(
                text,
                match.start(),
                match.end(),
                prefix_chars=context_chars,
                suffix_chars=context_chars,
            )
            matched_text = match.group(0)
            if _negative_hit(rule, prefix, matched_text, suffix):
                continue
            if not _context_satisfied(rule, prefix, matched_text, suffix):
                continue
            matches.append(
                PatternMatch(
                    rule=rule,
                    matched_text=matched_text,
                    start=match.start(),
                    end=match.end(),
                    prefix=prefix,
                    suffix=suffix,
                )
            )
    return matches
