"""Language extractor: `html[lang]` and `content-language` meta only.

No third-party language-detection library is invoked — brief section 5's
explicit "deterministic text-language marker only if already available
locally" (i.e. never a new dependency for this).
"""

from app.modules.evidence.domain.enums import EvidenceStrength, EvidenceType
from app.modules.extraction.domain.candidate_builder import (
    build_candidate_draft,
    build_evidence_draft,
)
from app.modules.extraction.domain.enums import FactSourceType, VerificationState
from app.modules.extraction.domain.extractor import FactCandidateDraft, PageContext
from app.modules.extraction.domain.field_catalogue import FieldPath, FieldValueType
from app.modules.extraction.domain.html_helpers import parse_page_structure
from app.modules.extraction.domain.models import ExtractorDefinition

EXTRACTOR_ID = "identity.language"
EXTRACTOR_VERSION = "v1"


class LanguageExtractor:
    def definition(self) -> ExtractorDefinition:
        return ExtractorDefinition(
            extractor_id=EXTRACTOR_ID,
            name="Language extractor",
            version=EXTRACTOR_VERSION,
            supported_page_types=[],
            output_field_paths=[FieldPath.IDENTITY_LANGUAGE],
            priority=50,
        )

    def supports(self, page_context: PageContext) -> bool:
        return True

    def extract(self, page_context: PageContext) -> list[FactCandidateDraft]:
        structure = parse_page_structure(page_context.cleaned_html)
        drafts: list[FactCandidateDraft] = []

        if structure.html_lang:
            drafts.append(
                self._candidate(
                    page_context, structure.html_lang, source="html_lang", confidence=70
                )
            )

        content_language = structure.meta_tags.get("content-language") or structure.meta_tags.get(
            "http-equiv=content-language"
        )
        if content_language:
            drafts.append(
                self._candidate(
                    page_context, content_language, source="content_language_meta", confidence=60
                )
            )

        return drafts

    def _candidate(
        self, page_context: PageContext, language: str, *, source: str, confidence: int
    ) -> FactCandidateDraft:
        normalized = language.strip().split("-")[0].lower()
        evidence = build_evidence_draft(
            page_context=page_context,
            field_path=FieldPath.IDENTITY_LANGUAGE,
            evidence_type=EvidenceType.HTML_ATTRIBUTE
            if source == "html_lang"
            else EvidenceType.META_TAG,
            strength=EvidenceStrength.MODERATE,
            source_fragment=language,
            extractor_id=EXTRACTOR_ID,
            extractor_version=EXTRACTOR_VERSION,
            raw_value=language,
            normalized_value=normalized,
        )
        return build_candidate_draft(
            field_path=FieldPath.IDENTITY_LANGUAGE,
            value=language,
            normalized_value=normalized,
            value_type=FieldValueType.STRING,
            source_type=FactSourceType.HTML_ELEMENT
            if source == "html_lang"
            else FactSourceType.META_TAG,
            confidence=confidence,
            verification_state=VerificationState.MEASURED,
            evidence_drafts=[evidence],
            qualifiers={"rule_id": f"identity.language.{source}"},
        )
