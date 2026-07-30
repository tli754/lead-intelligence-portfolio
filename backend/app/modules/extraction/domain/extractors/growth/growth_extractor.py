"""Growth-signal extractors (brief section 11).

Publication date is deliberately distinguished from event date: an
explicit date found near the matched statement is treated as the event
date; `article:published_time` (or, failing that, the page's own
`fetched_at`) is the publication date. The original statement is always
preserved verbatim as the evidence excerpt (`domain/evidence_factory.py`
handles the capping).
"""

import re
from datetime import date, datetime

from app.modules.evidence.domain.enums import EvidenceType
from app.modules.extraction.domain.candidate_builder import (
    build_candidate_draft,
    build_evidence_draft,
)
from app.modules.extraction.domain.enums import FactSourceType, VerificationState
from app.modules.extraction.domain.extractor import FactCandidateDraft, PageContext
from app.modules.extraction.domain.extractors.growth.patterns import PATTERN_RULES
from app.modules.extraction.domain.field_catalogue import FieldValueType
from app.modules.extraction.domain.html_helpers import parse_page_structure
from app.modules.extraction.domain.models import ExtractorDefinition
from app.modules.extraction.domain.pattern_types import match_pattern_rule

EXTRACTOR_ID = "growth.signals"
EXTRACTOR_VERSION = "v1"

_ISO_DATE_PATTERN = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_LONG_DATE_PATTERN = re.compile(
    r"\b((?:January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+\d{1,2},?\s+\d{4})\b"
)


def _parse_date(text: str) -> date | None:
    iso_match = _ISO_DATE_PATTERN.search(text)
    if iso_match:
        try:
            return datetime.strptime(iso_match.group(1), "%Y-%m-%d").date()
        except ValueError:
            return None
    long_match = _LONG_DATE_PATTERN.search(text)
    if long_match:
        cleaned = long_match.group(1).replace(",", "")
        try:
            return datetime.strptime(cleaned, "%B %d %Y").date()
        except ValueError:
            return None
    return None


class GrowthSignalExtractor:
    def definition(self) -> ExtractorDefinition:
        return ExtractorDefinition(
            extractor_id=EXTRACTOR_ID,
            name="Growth-signal extractor",
            version=EXTRACTOR_VERSION,
            supported_page_types=[],
            output_field_paths=sorted({rule.field_path for rule in PATTERN_RULES.values()}),
            priority=50,
        )

    def supports(self, page_context: PageContext) -> bool:
        return True

    def extract(self, page_context: PageContext) -> list[FactCandidateDraft]:
        structure = parse_page_structure(page_context.cleaned_html)
        published_time = structure.meta_tags.get("article:published_time")
        publication_date = _parse_date(published_time) if published_time else None

        drafts: list[FactCandidateDraft] = []
        for rule in PATTERN_RULES.values():
            for match in match_pattern_rule(
                rule, page_context.extracted_text, page_type=page_context.page_type
            ):
                window = f"{match.prefix} {match.matched_text} {match.suffix}"
                event_date = _parse_date(window)
                effective_publication_date = publication_date or page_context.fetched_at.date()

                normalized_value = {
                    "signal_type": rule.rule_id.split(".")[1],
                    "statement": match.matched_text,
                    "event_date": event_date.isoformat() if event_date else None,
                    "publication_date": effective_publication_date.isoformat(),
                    "effective_date": (event_date or effective_publication_date).isoformat(),
                    "status": "reported",
                    "source_url": page_context.source_url,
                }
                evidence = build_evidence_draft(
                    page_context=page_context,
                    field_path=rule.field_path,
                    evidence_type=EvidenceType.PAGE_TEXT,
                    strength=rule.evidence_strength,
                    source_fragment=match.matched_text,
                    prefix_context=match.prefix,
                    suffix_context=match.suffix,
                    extractor_id=EXTRACTOR_ID,
                    extractor_version=EXTRACTOR_VERSION,
                    raw_value=match.matched_text,
                    normalized_value=match.matched_text,
                )
                drafts.append(
                    build_candidate_draft(
                        field_path=rule.field_path,
                        value=normalized_value,
                        normalized_value=normalized_value,
                        value_type=FieldValueType.STRUCTURED_ENTITY_LIST,
                        source_type=FactSourceType.HTML_ELEMENT,
                        confidence=rule.base_confidence,
                        verification_state=VerificationState.MEASURED,
                        evidence_drafts=[evidence],
                        qualifiers={
                            "rule_id": rule.rule_id,
                            "dedup_key": f"{rule.rule_id}|{match.matched_text.lower()}",
                        },
                    )
                )
        return drafts
