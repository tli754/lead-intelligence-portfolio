"""Company-name extractor: the 7-step priority chain from brief section 5.

1. Organisation JSON-LD name
2. WebSite JSON-LD name
3. Open Graph `og:site_name`
4. homepage `<title>` pattern
5. logo `alt` text
6. about-page heading
7. domain fallback (low-confidence inference)

Every signal actually present on the page is emitted as its own candidate
— reconciliation (source-priority ranking, `domain/reconciliation.py`)
picks the winner across candidates/pages, rather than this extractor
guessing which single signal to prefer. AC-04's fixtures each carry only
one signal, so this still resolves to "the" expected candidate per test.
"""

import re
from urllib.parse import urlsplit

from app.modules.discovery.domain.enums import PageType
from app.modules.evidence.domain.enums import EvidenceStrength, EvidenceType
from app.modules.extraction.domain.candidate_builder import (
    build_candidate_draft,
    build_evidence_draft,
)
from app.modules.extraction.domain.enums import FactSourceType, VerificationState
from app.modules.extraction.domain.extractor import FactCandidateDraft, PageContext
from app.modules.extraction.domain.extractors.identity.patterns import TITLE_SEPARATOR_PATTERN
from app.modules.extraction.domain.field_catalogue import FieldPath, FieldValueType
from app.modules.extraction.domain.html_helpers import (
    flatten_json_ld_entities,
    json_ld_entities_of_type,
    parse_page_structure,
)
from app.modules.extraction.domain.models import ExtractorDefinition

EXTRACTOR_ID = "identity.company_name"
EXTRACTOR_VERSION = "v1"

_H1_PATTERN = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)
_TAG_PATTERN = re.compile(r"<[^>]+>")
_LOGO_MARKER_PATTERN = re.compile(r"logo", re.IGNORECASE)


def _strip_tags(fragment: str) -> str:
    return re.sub(r"\s+", " ", _TAG_PATTERN.sub(" ", fragment)).strip()


def _domain_fallback_name(normalized_url: str) -> str:
    host = urlsplit(normalized_url).hostname or normalized_url
    labels = host.split(".")
    root = labels[-2] if len(labels) >= 2 else labels[0]
    words = re.split(r"[-_]", root)
    return " ".join(word.capitalize() for word in words if word)


class CompanyNameExtractor:
    def definition(self) -> ExtractorDefinition:
        return ExtractorDefinition(
            extractor_id=EXTRACTOR_ID,
            name="Company name extractor",
            version=EXTRACTOR_VERSION,
            supported_page_types=[PageType.HOMEPAGE, PageType.ABOUT],
            output_field_paths=[FieldPath.IDENTITY_COMPANY_NAME],
            priority=100,
        )

    def supports(self, page_context: PageContext) -> bool:
        return page_context.page_type in (PageType.HOMEPAGE, PageType.ABOUT)

    def extract(self, page_context: PageContext) -> list[FactCandidateDraft]:
        drafts: list[FactCandidateDraft] = []
        structure = parse_page_structure(page_context.cleaned_html)
        entities = flatten_json_ld_entities(structure.json_ld_blocks)

        drafts.extend(self._from_json_ld(page_context, entities, "Organization", confidence=92))
        drafts.extend(self._from_json_ld(page_context, entities, "WebSite", confidence=85))
        drafts.extend(self._from_open_graph(page_context, structure.meta_tags))
        if page_context.page_type == PageType.HOMEPAGE and structure.title:
            drafts.extend(self._from_title(page_context, structure.title))
        drafts.extend(self._from_logo_alt(page_context, structure.images))
        if page_context.page_type == PageType.ABOUT:
            drafts.extend(self._from_about_heading(page_context))
        drafts.extend(self._from_domain_fallback(page_context))
        return drafts

    def _make_candidate(
        self,
        page_context: PageContext,
        *,
        name: str,
        confidence: int,
        source_type: FactSourceType,
        verification_state: VerificationState,
        rule_id: str,
        evidence_type: EvidenceType,
        strength: EvidenceStrength,
        source_fragment: str,
    ) -> FactCandidateDraft:
        evidence = build_evidence_draft(
            page_context=page_context,
            field_path=FieldPath.IDENTITY_COMPANY_NAME,
            evidence_type=evidence_type,
            strength=strength,
            source_fragment=source_fragment,
            extractor_id=EXTRACTOR_ID,
            extractor_version=EXTRACTOR_VERSION,
            raw_value=name,
            normalized_value=name.strip(),
        )
        return build_candidate_draft(
            field_path=FieldPath.IDENTITY_COMPANY_NAME,
            value=name,
            normalized_value=name.strip(),
            value_type=FieldValueType.STRING,
            source_type=source_type,
            confidence=confidence,
            verification_state=verification_state,
            evidence_drafts=[evidence],
            qualifiers={"rule_id": rule_id},
        )

    def _from_json_ld(self, page_context, entities, type_name: str, *, confidence: int):
        matches = json_ld_entities_of_type(entities, type_name)
        drafts = []
        for entity in matches:
            name = entity.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            drafts.append(
                self._make_candidate(
                    page_context,
                    name=name,
                    confidence=confidence,
                    source_type=FactSourceType.JSON_LD,
                    verification_state=VerificationState.VERIFIED,
                    rule_id=f"identity.company_name.{type_name.lower()}_json_ld",
                    evidence_type=EvidenceType.JSON_LD,
                    strength=EvidenceStrength.AUTHORITATIVE,
                    source_fragment=name,
                )
            )
        return drafts

    def _from_open_graph(self, page_context, meta_tags: dict[str, str]):
        site_name = meta_tags.get("og:site_name")
        if not site_name or not site_name.strip():
            return []
        return [
            self._make_candidate(
                page_context,
                name=site_name,
                confidence=78,
                source_type=FactSourceType.OPEN_GRAPH,
                verification_state=VerificationState.MEASURED,
                rule_id="identity.company_name.open_graph_site_name",
                evidence_type=EvidenceType.META_TAG,
                strength=EvidenceStrength.STRONG,
                source_fragment=site_name,
            )
        ]

    def _from_title(self, page_context, title: str):
        pattern = TITLE_SEPARATOR_PATTERN.positive_patterns[0]
        match = pattern.match(title)
        if not match:
            return []
        candidate_name = match.group("name").strip()
        if not candidate_name:
            return []
        return [
            self._make_candidate(
                page_context,
                name=candidate_name,
                confidence=TITLE_SEPARATOR_PATTERN.base_confidence,
                source_type=FactSourceType.HTML_ELEMENT,
                verification_state=VerificationState.INFERRED,
                rule_id=TITLE_SEPARATOR_PATTERN.rule_id,
                evidence_type=EvidenceType.PAGE_TEXT,
                strength=TITLE_SEPARATOR_PATTERN.evidence_strength,
                source_fragment=title,
            )
        ]

    def _from_logo_alt(self, page_context, images: list[dict[str, str]]):
        drafts = []
        for image in images:
            marker_text = f"{image.get('class', '')} {image.get('id', '')} {image.get('src', '')}"
            alt = image.get("alt", "").strip()
            if not alt or not _LOGO_MARKER_PATTERN.search(marker_text):
                continue
            if alt.lower() == "logo":
                continue
            drafts.append(
                self._make_candidate(
                    page_context,
                    name=alt,
                    confidence=50,
                    source_type=FactSourceType.HTML_ELEMENT,
                    verification_state=VerificationState.INFERRED,
                    rule_id="identity.company_name.logo_alt_text",
                    evidence_type=EvidenceType.HTML_ATTRIBUTE,
                    strength=EvidenceStrength.WEAK,
                    source_fragment=alt,
                )
            )
            break  # first matching logo image only
        return drafts

    def _from_about_heading(self, page_context):
        match = _H1_PATTERN.search(page_context.cleaned_html)
        if not match:
            return []
        heading = _strip_tags(match.group(1))
        if not heading:
            return []
        return [
            self._make_candidate(
                page_context,
                name=heading,
                confidence=50,
                source_type=FactSourceType.HTML_ELEMENT,
                verification_state=VerificationState.INFERRED,
                rule_id="identity.company_name.about_page_heading",
                evidence_type=EvidenceType.PAGE_TEXT,
                strength=EvidenceStrength.WEAK,
                source_fragment=heading,
            )
        ]

    def _from_domain_fallback(self, page_context):
        name = _domain_fallback_name(page_context.normalized_url)
        if not name:
            return []
        return [
            self._make_candidate(
                page_context,
                name=name,
                confidence=20,
                source_type=FactSourceType.DETERMINISTIC_INFERENCE,
                verification_state=VerificationState.INFERRED,
                rule_id="identity.company_name.domain_fallback",
                evidence_type=EvidenceType.DETERMINISTIC_INFERENCE,
                strength=EvidenceStrength.WEAK,
                source_fragment=page_context.normalized_url,
            )
        ]
