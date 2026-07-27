"""Technology-signal extractor family (brief section 9).

Combines crawling's own already-computed `PageContext.raw_technology_signals`
(script hosts / generator meta / framework markers crawling's cleaner and
metadata extractor already surfaced) with this extractor's own additional
pattern-matching over `cleaned_html` for markers crawling doesn't already
detect (specific payment/CRM/ERP/reviews/support/loyalty script hosts,
inline widget markers). Generic CDN usage is never listed as a signature
for any product, so it can never produce a false-positive commerce/CRM/etc.
candidate. Agreement across multiple pages is a reconciliation-time
concern (`set_union` merge strategy), not decided per-page here.
"""

import re
from urllib.parse import urlsplit

from app.modules.evidence.domain.enums import EvidenceStrength, EvidenceType
from app.modules.extraction.domain.candidate_builder import (
    build_candidate_draft,
    build_evidence_draft,
)
from app.modules.extraction.domain.enums import FactSourceType, VerificationState
from app.modules.extraction.domain.extractor import FactCandidateDraft, PageContext
from app.modules.extraction.domain.extractors.technology.signatures import (
    TECHNOLOGY_SIGNATURES,
    TECHNOLOGY_SIGNATURES_VERSION,
    TechnologySignature,
)
from app.modules.extraction.domain.field_catalogue import FieldPath, FieldValueType
from app.modules.extraction.domain.models import ExtractorDefinition

EXTRACTOR_ID = "technology.signatures"
EXTRACTOR_VERSION = "v1"

_SCRIPT_SRC_PATTERN = re.compile(r'<script[^>]+src="([^"]+)"', re.IGNORECASE)

AI_SIGNAL_MARKERS: tuple[str, ...] = (
    "chatgpt",
    "openai",
    "ai-powered",
    "ai powered",
    "ai chatbot",
)


def _script_hosts(cleaned_html: str) -> set[str]:
    hosts = set()
    for src in _SCRIPT_SRC_PATTERN.findall(cleaned_html):
        host = urlsplit(src).hostname
        if host:
            hosts.add(host.lower())
    return hosts


class TechnologyExtractor:
    def definition(self) -> ExtractorDefinition:
        return ExtractorDefinition(
            extractor_id=EXTRACTOR_ID,
            name="Technology-signature extractor",
            version=EXTRACTOR_VERSION,
            supported_page_types=[],
            output_field_paths=sorted({sig.field_path for sig in TECHNOLOGY_SIGNATURES}),
            priority=60,
        )

    def supports(self, page_context: PageContext) -> bool:
        return True

    def extract(self, page_context: PageContext) -> list[FactCandidateDraft]:
        raw_signals = page_context.raw_technology_signals or {}
        hosts = {str(h).lower() for h in raw_signals.get("script_source_hosts", []) or []}
        hosts |= _script_hosts(page_context.cleaned_html)
        generator = str(raw_signals.get("generator") or "").lower()
        html_lower = page_context.cleaned_html.lower()

        drafts: list[FactCandidateDraft] = []
        for signature in TECHNOLOGY_SIGNATURES:
            match = self._find_match(
                signature, hosts=hosts, generator=generator, html_lower=html_lower
            )
            if match is None:
                continue
            matched_marker, evidence_type, source_type = match
            drafts.append(
                self._candidate(page_context, signature, matched_marker, evidence_type, source_type)
            )

        drafts.extend(self._ai_signals(page_context, html_lower))
        return drafts

    def _find_match(
        self, signature: TechnologySignature, *, hosts: set[str], generator: str, html_lower: str
    ) -> tuple[str, EvidenceType, FactSourceType] | None:
        for marker in signature.host_markers:
            if any(marker in host for host in hosts):
                return marker, EvidenceType.SCRIPT_MARKER, FactSourceType.SCRIPT_MARKER
        for marker in signature.generator_markers:
            if marker in generator:
                return marker, EvidenceType.META_TAG, FactSourceType.META_TAG
        for marker in signature.html_markers:
            if marker in html_lower:
                return marker, EvidenceType.HTML_ATTRIBUTE, FactSourceType.HTML_ELEMENT
        return None

    def _candidate(
        self,
        page_context: PageContext,
        signature: TechnologySignature,
        matched_marker: str,
        evidence_type: EvidenceType,
        source_type: FactSourceType,
    ) -> FactCandidateDraft:
        evidence = build_evidence_draft(
            page_context=page_context,
            field_path=signature.field_path,
            evidence_type=evidence_type,
            strength=signature.evidence_strength,
            source_fragment=matched_marker,
            extractor_id=EXTRACTOR_ID,
            extractor_version=EXTRACTOR_VERSION,
            raw_value=matched_marker,
            normalized_value=signature.technology,
        )
        return build_candidate_draft(
            field_path=signature.field_path,
            value=signature.technology,
            normalized_value=signature.technology,
            value_type=FieldValueType.STRING_LIST,
            source_type=source_type,
            confidence=signature.base_confidence,
            verification_state=VerificationState.MEASURED,
            evidence_drafts=[evidence],
            qualifiers={
                "rule_id": signature.rule_id,
                "dedup_key": signature.technology,
                "technology_signatures_version": TECHNOLOGY_SIGNATURES_VERSION,
            },
        )

    def _ai_signals(self, page_context: PageContext, html_lower: str) -> list[FactCandidateDraft]:
        drafts = []
        for marker in AI_SIGNAL_MARKERS:
            if marker not in html_lower:
                continue
            evidence = build_evidence_draft(
                page_context=page_context,
                field_path=FieldPath.TECHNOLOGY_AI_SIGNALS,
                evidence_type=EvidenceType.HTML_ATTRIBUTE,
                strength=EvidenceStrength.WEAK,
                source_fragment=marker,
                extractor_id=EXTRACTOR_ID,
                extractor_version=EXTRACTOR_VERSION,
                raw_value=marker,
                normalized_value=marker,
            )
            drafts.append(
                build_candidate_draft(
                    field_path=FieldPath.TECHNOLOGY_AI_SIGNALS,
                    value=marker,
                    normalized_value=marker,
                    value_type=FieldValueType.STRING_LIST,
                    source_type=FactSourceType.HTML_ELEMENT,
                    confidence=55,
                    verification_state=VerificationState.INFERRED,
                    evidence_drafts=[evidence],
                    qualifiers={
                        "rule_id": "technology.ai_signals.keyword_marker",
                        "dedup_key": marker,
                        "technology_signatures_version": TECHNOLOGY_SIGNATURES_VERSION,
                    },
                )
            )
            break  # one AI-signal candidate is enough per page
        return drafts
