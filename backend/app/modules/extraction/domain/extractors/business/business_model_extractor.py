"""Business-model boolean-capability extractors (brief section 6).

One extractor class runs every centralized `patterns.py` rule against
`PageContext.extracted_text` — each field's positive pattern list only
ever produces `true`/absent (never `false`); `false` is only ever
produced by the field's own `NEGATIVE_STATEMENT_RULES` entry, an
explicit denial statement.
"""

from app.modules.evidence.domain.enums import EvidenceType
from app.modules.extraction.domain.candidate_builder import (
    build_candidate_draft,
    build_evidence_draft,
)
from app.modules.extraction.domain.enums import FactSourceType, VerificationState
from app.modules.extraction.domain.extractor import FactCandidateDraft, PageContext
from app.modules.extraction.domain.extractors.business.patterns import (
    BOOKING_RULE,
    CLICK_AND_COLLECT_RULE,
    CUSTOM_PRODUCTS_RULE,
    NEGATIVE_STATEMENT_RULES,
    ONLINE_ONLY_RULE,
    SUBSCRIPTION_RULE,
    TRADE_ACCOUNTS_RULE,
    WHOLESALE_RULE,
)
from app.modules.extraction.domain.field_catalogue import FieldValueType
from app.modules.extraction.domain.models import ExtractorDefinition
from app.modules.extraction.domain.pattern_types import PatternRule, match_pattern_rule

EXTRACTOR_ID = "business.model_signals"
EXTRACTOR_VERSION = "v1"

_BOOLEAN_RULES: tuple[PatternRule, ...] = (
    WHOLESALE_RULE,
    TRADE_ACCOUNTS_RULE,
    CLICK_AND_COLLECT_RULE,
    SUBSCRIPTION_RULE,
    BOOKING_RULE,
    ONLINE_ONLY_RULE,
    CUSTOM_PRODUCTS_RULE,
)


class BusinessModelExtractor:
    def definition(self) -> ExtractorDefinition:
        return ExtractorDefinition(
            extractor_id=EXTRACTOR_ID,
            name="Business-model capability extractor",
            version=EXTRACTOR_VERSION,
            supported_page_types=[],
            output_field_paths=[rule.field_path for rule in _BOOLEAN_RULES],
            priority=80,
        )

    def supports(self, page_context: PageContext) -> bool:
        return True

    def extract(self, page_context: PageContext) -> list[FactCandidateDraft]:
        drafts: list[FactCandidateDraft] = []
        text = page_context.extracted_text

        for rule in _BOOLEAN_RULES:
            for match in match_pattern_rule(rule, text, page_type=page_context.page_type):
                drafts.append(self._draft(page_context, rule, match.matched_text, value=True))

        for negative_rule in NEGATIVE_STATEMENT_RULES.values():
            for match in match_pattern_rule(negative_rule, text, page_type=page_context.page_type):
                drafts.append(
                    self._draft(page_context, negative_rule, match.matched_text, value=False)
                )

        return drafts

    def _draft(
        self, page_context: PageContext, rule: PatternRule, matched_text: str, *, value: bool
    ) -> FactCandidateDraft:
        evidence = build_evidence_draft(
            page_context=page_context,
            field_path=rule.field_path,
            evidence_type=EvidenceType.PAGE_TEXT,
            strength=rule.evidence_strength,
            source_fragment=matched_text,
            extractor_id=EXTRACTOR_ID,
            extractor_version=EXTRACTOR_VERSION,
            raw_value=matched_text,
            normalized_value=str(value),
        )
        return build_candidate_draft(
            field_path=rule.field_path,
            value=value,
            normalized_value=value,
            value_type=FieldValueType.BOOLEAN,
            source_type=FactSourceType.HTML_ELEMENT,
            confidence=rule.base_confidence,
            verification_state=VerificationState.MEASURED,
            evidence_drafts=[evidence],
            qualifiers={"rule_id": rule.rule_id, "source_wording": matched_text},
        )
