"""Trading-name extractor.

Sources: JSON-LD `alternateName`, explicit "trading as" wording, and
footer legal text specifically (treated as more reliable than an
in-body mention). Kept as a distinct `FieldPath` from
`identity.company_name` — legal/primary name and trading name are never
conflated (brief section 5's explicit requirement).
"""

import re

from app.modules.evidence.domain.enums import EvidenceStrength, EvidenceType
from app.modules.extraction.domain.candidate_builder import (
    build_candidate_draft,
    build_evidence_draft,
)
from app.modules.extraction.domain.enums import FactSourceType, VerificationState
from app.modules.extraction.domain.extractor import FactCandidateDraft, PageContext
from app.modules.extraction.domain.extractors.identity.patterns import TRADING_AS_PATTERN
from app.modules.extraction.domain.field_catalogue import FieldPath, FieldValueType
from app.modules.extraction.domain.html_helpers import (
    collapse_whitespace,
    flatten_json_ld_entities,
    json_ld_entities_of_type,
    parse_page_structure,
)
from app.modules.extraction.domain.models import ExtractorDefinition
from app.modules.extraction.domain.pattern_types import match_pattern_rule

EXTRACTOR_ID = "identity.trading_name"
EXTRACTOR_VERSION = "v1"

_FOOTER_PATTERN = re.compile(r"<footer[^>]*>(.*?)</footer>", re.IGNORECASE | re.DOTALL)
_TAG_PATTERN = re.compile(r"<[^>]+>")


def _footer_text(cleaned_html: str) -> str | None:
    match = _FOOTER_PATTERN.search(cleaned_html)
    if not match:
        return None
    return collapse_whitespace(_TAG_PATTERN.sub(" ", match.group(1)))


class TradingNameExtractor:
    def definition(self) -> ExtractorDefinition:
        return ExtractorDefinition(
            extractor_id=EXTRACTOR_ID,
            name="Trading-name extractor",
            version=EXTRACTOR_VERSION,
            supported_page_types=[],
            output_field_paths=[FieldPath.IDENTITY_TRADING_NAME],
            priority=90,
        )

    def supports(self, page_context: PageContext) -> bool:
        return True

    def extract(self, page_context: PageContext) -> list[FactCandidateDraft]:
        drafts: list[FactCandidateDraft] = []
        structure = parse_page_structure(page_context.cleaned_html)
        entities = flatten_json_ld_entities(structure.json_ld_blocks)

        for entity in json_ld_entities_of_type(entities, "Organization"):
            alternate_name = entity.get("alternateName")
            if isinstance(alternate_name, str) and alternate_name.strip():
                drafts.append(self._candidate(page_context, alternate_name, source="json_ld"))

        footer_text = _footer_text(page_context.cleaned_html)
        if footer_text:
            for match in match_pattern_rule(
                TRADING_AS_PATTERN, footer_text, page_type=page_context.page_type
            ):
                name = self._captured_name(match.matched_text)
                if name:
                    drafts.append(self._candidate(page_context, name, source="footer"))

        for match in match_pattern_rule(
            TRADING_AS_PATTERN, page_context.extracted_text, page_type=page_context.page_type
        ):
            name = self._captured_name(match.matched_text)
            if name:
                drafts.append(self._candidate(page_context, name, source="body"))

        return drafts

    def _captured_name(self, matched_text: str) -> str | None:
        match = TRADING_AS_PATTERN.positive_patterns[0].search(matched_text)
        return match.group("name").strip() if match else None

    def _candidate(
        self, page_context: PageContext, name: str, *, source: str
    ) -> FactCandidateDraft:
        confidence = {"json_ld": 80, "footer": 75, "body": 60}[source]
        source_type = FactSourceType.JSON_LD if source == "json_ld" else FactSourceType.HTML_ELEMENT
        verification_state = (
            VerificationState.VERIFIED if source == "json_ld" else VerificationState.MEASURED
        )
        rule_id = {
            "json_ld": "identity.trading_name.alternate_name_json_ld",
            "footer": "identity.trading_name.footer_legal_text",
            "body": TRADING_AS_PATTERN.rule_id,
        }[source]
        evidence = build_evidence_draft(
            page_context=page_context,
            field_path=FieldPath.IDENTITY_TRADING_NAME,
            evidence_type=(EvidenceType.JSON_LD if source == "json_ld" else EvidenceType.PAGE_TEXT),
            strength=(
                EvidenceStrength.AUTHORITATIVE if source == "json_ld" else EvidenceStrength.MODERATE
            ),
            source_fragment=name,
            extractor_id=EXTRACTOR_ID,
            extractor_version=EXTRACTOR_VERSION,
            raw_value=name,
            normalized_value=name.strip(),
        )
        return build_candidate_draft(
            field_path=FieldPath.IDENTITY_TRADING_NAME,
            value=name,
            normalized_value=name.strip(),
            value_type=FieldValueType.STRING,
            source_type=source_type,
            confidence=confidence,
            verification_state=verification_state,
            evidence_drafts=[evidence],
            qualifiers={"rule_id": rule_id, "source": source},
        )
