"""Country/city extractor.

Sources, in descending reliability: `PostalAddress` JSON-LD (whether
attached to an `Organization`/`LocalBusiness`/`Store` entity or standalone),
a `<address>` block on a contact page, a footer address block, and — only
ever as a **low-confidence supporting signal, never verified** — the
page's TLD. Conflicting candidates (e.g. a structured address disagreeing
with footer text) are always emitted independently; reconciliation
decides whether to merge or preserve them as a conflict, never this
extractor.
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
from app.modules.extraction.domain.field_catalogue import FieldPath, FieldValueType
from app.modules.extraction.domain.html_helpers import (
    collapse_whitespace,
    flatten_json_ld_entities,
    parse_page_structure,
)
from app.modules.extraction.domain.models import ExtractorDefinition

EXTRACTOR_ID = "identity.country_city"
EXTRACTOR_VERSION = "v1"

_ADDRESS_TAG_PATTERN = re.compile(r"<address[^>]*>(.*?)</address>", re.IGNORECASE | re.DOTALL)
_FOOTER_PATTERN = re.compile(r"<footer[^>]*>(.*?)</footer>", re.IGNORECASE | re.DOTALL)
_TAG_PATTERN = re.compile(r"<[^>]+>")

_COUNTRY_NAME_PATTERN = re.compile(
    r"\b(Australia|New Zealand|United Kingdom|United States(?: of America)?|"
    r"U\.S\.A\.|USA|UK|Canada)\b"
)
_COUNTRY_NORMALIZATION = {
    "australia": "Australia",
    "new zealand": "New Zealand",
    "united kingdom": "United Kingdom",
    "uk": "United Kingdom",
    "united states": "United States",
    "united states of america": "United States",
    "usa": "United States",
    "u.s.a.": "United States",
    "canada": "Canada",
}
_CITY_PATTERN = re.compile(
    r"(?P<city>[A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+){0,2}),?\s+[A-Z]{2,3}\s+\d{4,5}\b"
)
_COUNTRY_TLD_MAP = {
    "au": "Australia",
    "nz": "New Zealand",
    "uk": "United Kingdom",
    "us": "United States",
    "ca": "Canada",
}


def _strip_tags(fragment: str) -> str:
    return collapse_whitespace(_TAG_PATTERN.sub(" ", fragment))


def _tld_country(normalized_url: str) -> str | None:
    host = urlsplit(normalized_url).hostname or ""
    labels = host.split(".")
    if len(labels) < 2:
        return None
    return _COUNTRY_TLD_MAP.get(labels[-1].lower())


class CountryCityExtractor:
    def definition(self) -> ExtractorDefinition:
        return ExtractorDefinition(
            extractor_id=EXTRACTOR_ID,
            name="Country/city extractor",
            version=EXTRACTOR_VERSION,
            supported_page_types=[],
            output_field_paths=[FieldPath.IDENTITY_COUNTRY, FieldPath.IDENTITY_CITY],
            priority=90,
        )

    def supports(self, page_context: PageContext) -> bool:
        return True

    def extract(self, page_context: PageContext) -> list[FactCandidateDraft]:
        drafts: list[FactCandidateDraft] = []
        structure = parse_page_structure(page_context.cleaned_html)
        entities = flatten_json_ld_entities(structure.json_ld_blocks)

        for entity in entities:
            address = entity.get("address")
            if not isinstance(address, dict):
                continue
            entity_type = str(entity.get("@type") or "")
            confidence = 88 if entity_type.lower() in ("store", "localbusiness") else 90
            rule_suffix = (
                "store_json_ld"
                if entity_type.lower() in ("store", "localbusiness")
                else ("organisation_json_ld")
            )
            country = address.get("addressCountry")
            if isinstance(country, str) and country.strip():
                drafts.append(
                    self._candidate(
                        page_context,
                        field_path=FieldPath.IDENTITY_COUNTRY,
                        value=country,
                        confidence=confidence,
                        source_type=FactSourceType.JSON_LD,
                        verification_state=VerificationState.VERIFIED,
                        rule_id=f"identity.country.{rule_suffix}",
                        evidence_type=EvidenceType.JSON_LD,
                        strength=EvidenceStrength.AUTHORITATIVE,
                        source_fragment=country,
                    )
                )
            city = address.get("addressLocality")
            if isinstance(city, str) and city.strip():
                drafts.append(
                    self._candidate(
                        page_context,
                        field_path=FieldPath.IDENTITY_CITY,
                        value=city,
                        confidence=confidence,
                        source_type=FactSourceType.JSON_LD,
                        verification_state=VerificationState.VERIFIED,
                        rule_id=f"identity.city.{rule_suffix}",
                        evidence_type=EvidenceType.JSON_LD,
                        strength=EvidenceStrength.AUTHORITATIVE,
                        source_fragment=city,
                    )
                )

        if page_context.page_type == PageType.CONTACT:
            address_match = _ADDRESS_TAG_PATTERN.search(page_context.cleaned_html)
            if address_match:
                address_text = _strip_tags(address_match.group(1))
                drafts.extend(
                    self._from_text_block(
                        page_context, address_text, confidence=75, source="contact_address_block"
                    )
                )

        footer_match = _FOOTER_PATTERN.search(page_context.cleaned_html)
        if footer_match:
            footer_text = _strip_tags(footer_match.group(1))
            drafts.extend(
                self._from_text_block(
                    page_context, footer_text, confidence=60, source="footer_address"
                )
            )

        tld_country = _tld_country(page_context.normalized_url)
        if tld_country:
            drafts.append(
                self._candidate(
                    page_context,
                    field_path=FieldPath.IDENTITY_COUNTRY,
                    value=tld_country,
                    confidence=25,
                    source_type=FactSourceType.DETERMINISTIC_INFERENCE,
                    verification_state=VerificationState.INFERRED,
                    rule_id="identity.country.tld_inference",
                    evidence_type=EvidenceType.DETERMINISTIC_INFERENCE,
                    strength=EvidenceStrength.WEAK,
                    source_fragment=page_context.normalized_url,
                )
            )

        return drafts

    def _from_text_block(self, page_context, text: str, *, confidence: int, source: str):
        drafts = []
        country_match = _COUNTRY_NAME_PATTERN.search(text)
        if country_match:
            normalized = _COUNTRY_NORMALIZATION.get(
                country_match.group(0).strip().lower(), country_match.group(0).strip()
            )
            drafts.append(
                self._candidate(
                    page_context,
                    field_path=FieldPath.IDENTITY_COUNTRY,
                    value=normalized,
                    confidence=confidence,
                    source_type=FactSourceType.HTML_ELEMENT,
                    verification_state=VerificationState.MEASURED,
                    rule_id=f"identity.country.{source}",
                    evidence_type=EvidenceType.PAGE_TEXT,
                    strength=EvidenceStrength.MODERATE,
                    source_fragment=text,
                )
            )
        city_match = _CITY_PATTERN.search(text)
        if city_match:
            drafts.append(
                self._candidate(
                    page_context,
                    field_path=FieldPath.IDENTITY_CITY,
                    value=city_match.group("city"),
                    confidence=confidence,
                    source_type=FactSourceType.HTML_ELEMENT,
                    verification_state=VerificationState.MEASURED,
                    rule_id=f"identity.city.{source}",
                    evidence_type=EvidenceType.PAGE_TEXT,
                    strength=EvidenceStrength.MODERATE,
                    source_fragment=text,
                )
            )
        return drafts

    def _candidate(
        self,
        page_context: PageContext,
        *,
        field_path: FieldPath,
        value: str,
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
            field_path=field_path,
            evidence_type=evidence_type,
            strength=strength,
            source_fragment=source_fragment,
            extractor_id=EXTRACTOR_ID,
            extractor_version=EXTRACTOR_VERSION,
            raw_value=value,
            normalized_value=value.strip(),
        )
        return build_candidate_draft(
            field_path=field_path,
            value=value,
            normalized_value=value.strip(),
            value_type=FieldValueType.STRING,
            source_type=source_type,
            confidence=confidence,
            verification_state=verification_state,
            evidence_drafts=[evidence],
            qualifiers={"rule_id": rule_id},
        )
