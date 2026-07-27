"""Organisation/contact extractors (brief section 10).

One `Extractor` implementation covers emails, phones, named people (with
role categorization), `internal_it_status`, and priority-ordered
`recommended_contact_candidates` — all derived from the same single-pass
`parse_page_structure` result, avoiding five separate HTML parses per page.
"""

import re

from app.modules.evidence.domain.enums import EvidenceStrength, EvidenceType
from app.modules.extraction.domain.candidate_builder import (
    build_candidate_draft,
    build_evidence_draft,
)
from app.modules.extraction.domain.enums import FactSourceType, VerificationState
from app.modules.extraction.domain.extractor import FactCandidateDraft, PageContext
from app.modules.extraction.domain.extractors.organisation.patterns import (
    EMAIL_TEXT_PATTERN,
    EXTERNAL_AGENCY_RULE,
    INTERNAL_IT_DETECTED_RULE,
    PHONE_TEXT_PATTERN,
)
from app.modules.extraction.domain.field_catalogue import FieldPath, FieldValueType
from app.modules.extraction.domain.html_helpers import (
    collapse_whitespace,
    flatten_json_ld_entities,
    json_ld_entities_of_type,
    parse_page_structure,
)
from app.modules.extraction.domain.models import ExtractorDefinition
from app.modules.extraction.domain.pattern_types import match_pattern_rule

EXTRACTOR_ID = "organisation.contact_signals"
EXTRACTOR_VERSION = "v1"

_TEAM_BLOCK_PATTERN = re.compile(
    r'class="[^"]*(?:team-member|person)[^"]*"[^>]*>(.*?)(?=class="[^"]*(?:team-member|person)|\Z)',
    re.IGNORECASE | re.DOTALL,
)
_NAME_PATTERN = re.compile(r"<h[1-6][^>]*>(.*?)</h[1-6]>", re.IGNORECASE | re.DOTALL)
_ROLE_PATTERN = re.compile(
    r'class="[^"]*(?:role|title)[^"]*"[^>]*>(.*?)</', re.IGNORECASE | re.DOTALL
)
_TAG_PATTERN = re.compile(r"<[^>]+>")

_ROLE_CATEGORY_KEYWORDS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bfounder\b", re.IGNORECASE), "founder"),
    (re.compile(r"\bowner\b", re.IGNORECASE), "owner"),
    (
        re.compile(r"\b(?:e-?commerce|online\s+store)\b", re.IGNORECASE),
        "ecommerce",
    ),
    (
        re.compile(r"\b(?:operations|logistics|warehouse\s+manager)\b", re.IGNORECASE),
        "operations",
    ),
    (re.compile(r"\b(?:marketing|brand)\b", re.IGNORECASE), "marketing"),
    (
        re.compile(r"\b(?:technology|engineering|developer|it\s+manager|cto)\b", re.IGNORECASE),
        "technology",
    ),
    (re.compile(r"\b(?:customer\s+service|support)\b", re.IGNORECASE), "customer_service"),
    (re.compile(r"\b(?:sales|account\s+manager)\b", re.IGNORECASE), "sales"),
    (
        re.compile(r"\b(?:ceo|cfo|coo|chief|president|director|executive)\b", re.IGNORECASE),
        "executive",
    ),
)

# Brief section 10's explicit priority order for recommended contacts.
_CONTACT_PRIORITY_BY_ROLE = {
    "ecommerce": 1,
    "operations": 2,
    "owner": 3,
    "founder": 3,
    "technology": 4,
    "marketing": 5,
}
_DEFAULT_CONTACT_PRIORITY = 9


def _role_category(role_title: str) -> str:
    for pattern, category in _ROLE_CATEGORY_KEYWORDS:
        if pattern.search(role_title):
            return category
    return "unknown"


def _strip_tags(fragment: str) -> str:
    return collapse_whitespace(_TAG_PATTERN.sub(" ", fragment))


class OrganisationExtractor:
    def definition(self) -> ExtractorDefinition:
        return ExtractorDefinition(
            extractor_id=EXTRACTOR_ID,
            name="Organisation/contact extractor",
            version=EXTRACTOR_VERSION,
            supported_page_types=[],
            output_field_paths=[
                FieldPath.ORGANISATION_EMAILS,
                FieldPath.ORGANISATION_PHONE_NUMBERS,
                FieldPath.ORGANISATION_PEOPLE,
                FieldPath.ORGANISATION_INTERNAL_IT_STATUS,
                FieldPath.ORGANISATION_RECOMMENDED_CONTACT_CANDIDATES,
            ],
            priority=70,
        )

    def supports(self, page_context: PageContext) -> bool:
        return True

    def extract(self, page_context: PageContext) -> list[FactCandidateDraft]:
        structure = parse_page_structure(page_context.cleaned_html)
        entities = flatten_json_ld_entities(structure.json_ld_blocks)

        drafts: list[FactCandidateDraft] = []
        drafts.extend(self._emails(page_context, structure, entities))
        drafts.extend(self._phones(page_context, structure, entities))

        people = self._people(page_context, entities)
        drafts.extend(self._people_candidates(page_context, people))
        drafts.extend(self._recommended_contact_candidates(page_context, people))
        drafts.extend(self._internal_it_status(page_context))
        return drafts

    # --- Emails --------------------------------------------------------

    def _emails(self, page_context, structure, entities) -> list[FactCandidateDraft]:
        found: set[str] = set()
        drafts = []
        for anchor in structure.anchors:
            href = anchor.get("href", "")
            if href.lower().startswith("mailto:"):
                email = href.split(":", 1)[1].split("?")[0].strip()
                if email and email.lower() not in found:
                    found.add(email.lower())
                    drafts.append(
                        self._contact_candidate(
                            page_context,
                            field_path=FieldPath.ORGANISATION_EMAILS,
                            value=email,
                            confidence=82,
                            source_type=FactSourceType.LINK,
                            rule_id="organisation.emails.mailto_link",
                            evidence_type=EvidenceType.LINK_TARGET,
                        )
                    )
        for entity in entities:
            email = entity.get("email")
            if isinstance(email, str) and email.strip() and email.lower() not in found:
                found.add(email.lower())
                drafts.append(
                    self._contact_candidate(
                        page_context,
                        field_path=FieldPath.ORGANISATION_EMAILS,
                        value=email.strip(),
                        confidence=85,
                        source_type=FactSourceType.JSON_LD,
                        rule_id="organisation.emails.structured_data",
                        evidence_type=EvidenceType.JSON_LD,
                    )
                )
        for match in EMAIL_TEXT_PATTERN.finditer(page_context.extracted_text):
            email = match.group(0)
            if email.lower() not in found:
                found.add(email.lower())
                drafts.append(
                    self._contact_candidate(
                        page_context,
                        field_path=FieldPath.ORGANISATION_EMAILS,
                        value=email,
                        confidence=70,
                        source_type=FactSourceType.HTML_ELEMENT,
                        rule_id="organisation.emails.visible_text",
                        evidence_type=EvidenceType.PAGE_TEXT,
                    )
                )
        return drafts

    # --- Phones ---------------------------------------------------------

    def _phones(self, page_context, structure, entities) -> list[FactCandidateDraft]:
        found: set[str] = set()
        drafts = []
        for anchor in structure.anchors:
            href = anchor.get("href", "")
            if href.lower().startswith("tel:"):
                phone = href.split(":", 1)[1].strip()
                normalized = re.sub(r"[^\d+]", "", phone)
                if normalized and normalized not in found:
                    found.add(normalized)
                    drafts.append(
                        self._contact_candidate(
                            page_context,
                            field_path=FieldPath.ORGANISATION_PHONE_NUMBERS,
                            value=phone,
                            confidence=80,
                            source_type=FactSourceType.LINK,
                            rule_id="organisation.phone_numbers.tel_link",
                            evidence_type=EvidenceType.LINK_TARGET,
                            normalized_value=normalized,
                        )
                    )
        for entity in entities:
            phone = entity.get("telephone")
            if isinstance(phone, str) and phone.strip():
                normalized = re.sub(r"[^\d+]", "", phone)
                if normalized and normalized not in found:
                    found.add(normalized)
                    drafts.append(
                        self._contact_candidate(
                            page_context,
                            field_path=FieldPath.ORGANISATION_PHONE_NUMBERS,
                            value=phone.strip(),
                            confidence=85,
                            source_type=FactSourceType.JSON_LD,
                            rule_id="organisation.phone_numbers.structured_data",
                            evidence_type=EvidenceType.JSON_LD,
                            normalized_value=normalized,
                        )
                    )
        for match in PHONE_TEXT_PATTERN.finditer(page_context.extracted_text):
            candidate_text = match.group(0)
            normalized = re.sub(r"[^\d+]", "", candidate_text)
            digit_count = len(re.sub(r"\D", "", normalized))
            if not (7 <= digit_count <= 15) or normalized in found:
                continue
            found.add(normalized)
            drafts.append(
                self._contact_candidate(
                    page_context,
                    field_path=FieldPath.ORGANISATION_PHONE_NUMBERS,
                    value=candidate_text.strip(),
                    confidence=65,
                    source_type=FactSourceType.HTML_ELEMENT,
                    rule_id="organisation.phone_numbers.visible_text",
                    evidence_type=EvidenceType.PAGE_TEXT,
                    normalized_value=normalized,
                )
            )
        return drafts

    def _contact_candidate(
        self,
        page_context,
        *,
        field_path: FieldPath,
        value: str,
        confidence: int,
        source_type: FactSourceType,
        rule_id: str,
        evidence_type: EvidenceType,
        normalized_value: str | None = None,
    ) -> FactCandidateDraft:
        normalized = normalized_value if normalized_value is not None else value.strip().lower()
        evidence = build_evidence_draft(
            page_context=page_context,
            field_path=field_path,
            evidence_type=evidence_type,
            strength=EvidenceStrength.MODERATE,
            source_fragment=value,
            extractor_id=EXTRACTOR_ID,
            extractor_version=EXTRACTOR_VERSION,
            raw_value=value,
            normalized_value=normalized,
            is_business_contact_fact=True,
        )
        return build_candidate_draft(
            field_path=field_path,
            value=value,
            normalized_value=normalized,
            value_type=FieldValueType.STRING_LIST,
            source_type=source_type,
            confidence=confidence,
            verification_state=VerificationState.MEASURED,
            evidence_drafts=[evidence],
            qualifiers={"rule_id": rule_id, "dedup_key": normalized},
        )

    # --- People ----------------------------------------------------------

    def _people(self, page_context, entities) -> list[dict]:
        people: list[dict] = []
        for entity in json_ld_entities_of_type(entities, "Person"):
            name = entity.get("name")
            if isinstance(name, str) and name.strip():
                people.append(
                    {
                        "name": name.strip(),
                        "role_title": entity.get("jobTitle") or "",
                        "email": entity.get("email"),
                        "phone": entity.get("telephone"),
                        "source": "json_ld",
                    }
                )

        for block_match in _TEAM_BLOCK_PATTERN.finditer(page_context.cleaned_html):
            block = block_match.group(1)
            name_match = _NAME_PATTERN.search(block)
            role_match = _ROLE_PATTERN.search(block)
            if not name_match:
                continue
            name = _strip_tags(name_match.group(1))
            role_title = _strip_tags(role_match.group(1)) if role_match else ""
            if not name:
                continue
            people.append(
                {
                    "name": name,
                    "role_title": role_title,
                    "email": None,
                    "phone": None,
                    "source": "team_block",
                }
            )
        return people

    def _people_candidates(self, page_context, people: list[dict]) -> list[FactCandidateDraft]:
        drafts = []
        for person in people:
            role_category = _role_category(person["role_title"])
            confidence = 80 if person["source"] == "json_ld" else 68
            source_type = (
                FactSourceType.JSON_LD
                if person["source"] == "json_ld"
                else FactSourceType.HTML_ELEMENT
            )
            normalized_value = {
                "name": person["name"],
                "role_title": person["role_title"],
                "role_category": role_category,
                "email": person["email"],
                "phone": person["phone"],
                "source_url": page_context.source_url,
            }
            evidence = build_evidence_draft(
                page_context=page_context,
                field_path=FieldPath.ORGANISATION_PEOPLE,
                evidence_type=(
                    EvidenceType.JSON_LD
                    if person["source"] == "json_ld"
                    else EvidenceType.PAGE_TEXT
                ),
                strength=EvidenceStrength.MODERATE,
                source_fragment=f"{person['name']} — {person['role_title']}".strip(" —"),
                extractor_id=EXTRACTOR_ID,
                extractor_version=EXTRACTOR_VERSION,
                raw_value=person["name"],
                normalized_value=person["name"].lower(),
            )
            drafts.append(
                build_candidate_draft(
                    field_path=FieldPath.ORGANISATION_PEOPLE,
                    value=normalized_value,
                    normalized_value=normalized_value,
                    value_type=FieldValueType.STRUCTURED_ENTITY_LIST,
                    source_type=source_type,
                    confidence=confidence,
                    verification_state=VerificationState.MEASURED,
                    evidence_drafts=[evidence],
                    qualifiers={
                        "rule_id": "organisation.people.named_person_with_role",
                        "dedup_key": f"{person['name'].lower()}|{role_category}",
                    },
                )
            )
        return drafts

    def _recommended_contact_candidates(
        self, page_context, people: list[dict]
    ) -> list[FactCandidateDraft]:
        drafts = []
        for person in people:
            role_category = _role_category(person["role_title"])
            priority = _CONTACT_PRIORITY_BY_ROLE.get(role_category, _DEFAULT_CONTACT_PRIORITY)
            normalized_value = {
                "name": person["name"],
                "role_title": person["role_title"],
                "role_category": role_category,
                "priority": priority,
                "source_url": page_context.source_url,
            }
            evidence = build_evidence_draft(
                page_context=page_context,
                field_path=FieldPath.ORGANISATION_RECOMMENDED_CONTACT_CANDIDATES,
                evidence_type=EvidenceType.PAGE_TEXT,
                strength=EvidenceStrength.WEAK,
                source_fragment=f"{person['name']} — {person['role_title']}".strip(" —"),
                extractor_id=EXTRACTOR_ID,
                extractor_version=EXTRACTOR_VERSION,
                raw_value=person["name"],
                normalized_value=person["name"].lower(),
            )
            drafts.append(
                build_candidate_draft(
                    field_path=FieldPath.ORGANISATION_RECOMMENDED_CONTACT_CANDIDATES,
                    value=normalized_value,
                    normalized_value=normalized_value,
                    value_type=FieldValueType.STRUCTURED_ENTITY_LIST,
                    source_type=FactSourceType.DETERMINISTIC_INFERENCE,
                    confidence=55,
                    verification_state=VerificationState.INFERRED,
                    evidence_drafts=[evidence],
                    qualifiers={
                        "rule_id": "organisation.recommended_contact_candidates.priority_ranked",
                        "dedup_key": f"{person['name'].lower()}|{role_category}",
                        "sort_key": priority,
                    },
                )
            )
        return drafts

    # --- Internal IT status ----------------------------------------------

    def _internal_it_status(self, page_context) -> list[FactCandidateDraft]:
        drafts = []
        for match in match_pattern_rule(
            INTERNAL_IT_DETECTED_RULE, page_context.extracted_text, page_type=page_context.page_type
        ):
            evidence = build_evidence_draft(
                page_context=page_context,
                field_path=FieldPath.ORGANISATION_INTERNAL_IT_STATUS,
                evidence_type=EvidenceType.PAGE_TEXT,
                strength=INTERNAL_IT_DETECTED_RULE.evidence_strength,
                source_fragment=match.matched_text,
                extractor_id=EXTRACTOR_ID,
                extractor_version=EXTRACTOR_VERSION,
                raw_value=match.matched_text,
                normalized_value="detected",
            )
            drafts.append(
                build_candidate_draft(
                    field_path=FieldPath.ORGANISATION_INTERNAL_IT_STATUS,
                    value="detected",
                    normalized_value="detected",
                    value_type=FieldValueType.ENUM,
                    source_type=FactSourceType.HTML_ELEMENT,
                    confidence=INTERNAL_IT_DETECTED_RULE.base_confidence,
                    verification_state=VerificationState.MEASURED,
                    evidence_drafts=[evidence],
                    qualifiers={"rule_id": INTERNAL_IT_DETECTED_RULE.rule_id},
                )
            )
        # Agency-credit wording is recorded only as supporting metadata on
        # any `detected` candidate already found — never emitted on its
        # own, and never used to assert `not_detected` (brief's explicit
        # "do not prove no internal IT").
        for match in match_pattern_rule(
            EXTERNAL_AGENCY_RULE, page_context.extracted_text, page_type=page_context.page_type
        ):
            for draft in drafts:
                draft.qualifiers.setdefault("external_agency_credit", match.matched_text)
        return drafts
