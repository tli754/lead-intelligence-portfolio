"""Physical-operations extractors (brief section 8).

Emits one `operations.locations` candidate per structured-data location
entity (deduplicated at reconciliation time by normalized address+name —
never counting the same footer/contact address twice), plus page-level
count candidates for `retail_store_count`/`showroom_count`/
`warehouse_count`/`office_count` only when a page is authoritative enough
to be treated as a full list (a store-locator / warehouse-and-showroom
page), and `pickup_available`/`returns_location_count` from explicit
wording. Stockists (third-party retailers) are tagged with a distinct
`location_type`/ownership qualifier and never counted as owned stores.
"""

from app.modules.discovery.domain.enums import PageType
from app.modules.evidence.domain.enums import EvidenceStrength, EvidenceType
from app.modules.extraction.domain.candidate_builder import (
    build_candidate_draft,
    build_evidence_draft,
)
from app.modules.extraction.domain.enums import FactSourceType, VerificationState
from app.modules.extraction.domain.extractor import FactCandidateDraft, PageContext
from app.modules.extraction.domain.extractors.operations.patterns import (
    PICKUP_AVAILABLE_RULE,
    SHOWROOM_WORDING_RULE,
    STOCKIST_WORDING_RULE,
    WAREHOUSE_WORDING_RULE,
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

EXTRACTOR_ID = "operations.physical_locations"
EXTRACTOR_VERSION = "v1"

_COUNT_FIELD_BY_LOCATION_TYPE = {
    "retail_store": FieldPath.OPERATIONS_RETAIL_STORE_COUNT,
    "showroom": FieldPath.OPERATIONS_SHOWROOM_COUNT,
    "warehouse": FieldPath.OPERATIONS_WAREHOUSE_COUNT,
    "office": FieldPath.OPERATIONS_OFFICE_COUNT,
}


def _normalize_address(entity: dict) -> str:
    address = entity.get("address")
    parts: list[str] = []
    if isinstance(address, dict):
        for key in (
            "streetAddress",
            "addressLocality",
            "addressRegion",
            "postalCode",
            "addressCountry",
        ):
            value = address.get(key)
            if isinstance(value, str):
                parts.append(value)
    elif isinstance(address, str):
        parts.append(address)
    return collapse_whitespace(" ".join(parts)).lower()


def _classify_location_type(entity: dict, page_text: str) -> str:
    name = str(entity.get("name") or "").lower()
    entity_type = str(entity.get("@type") or "").lower()
    if "warehouse" in name:
        return "warehouse"
    if "showroom" in name:
        return "showroom"
    if "office" in name or entity_type == "corporation":
        return "office"
    # No type-revealing wording on the entity itself — fall back to the
    # surrounding page's own explicit wording (brief section 8's "explicit
    # warehouse/showroom wording" source).
    if match_pattern_rule(WAREHOUSE_WORDING_RULE, page_text):
        return "warehouse"
    if match_pattern_rule(SHOWROOM_WORDING_RULE, page_text):
        return "showroom"
    return "retail_store"


class OperationsExtractor:
    def definition(self) -> ExtractorDefinition:
        return ExtractorDefinition(
            extractor_id=EXTRACTOR_ID,
            name="Physical-operations extractor",
            version=EXTRACTOR_VERSION,
            supported_page_types=[],
            output_field_paths=[
                FieldPath.OPERATIONS_RETAIL_STORE_COUNT,
                FieldPath.OPERATIONS_SHOWROOM_COUNT,
                FieldPath.OPERATIONS_WAREHOUSE_COUNT,
                FieldPath.OPERATIONS_OFFICE_COUNT,
                FieldPath.OPERATIONS_PICKUP_AVAILABLE,
                FieldPath.OPERATIONS_RETURNS_LOCATION_COUNT,
                FieldPath.OPERATIONS_LOCATIONS,
            ],
            priority=70,
        )

    def supports(self, page_context: PageContext) -> bool:
        return True

    def extract(self, page_context: PageContext) -> list[FactCandidateDraft]:
        structure = parse_page_structure(page_context.cleaned_html)
        entities = flatten_json_ld_entities(structure.json_ld_blocks)
        store_entities = json_ld_entities_of_type(entities, "Store", "LocalBusiness")

        is_stockist_page = bool(
            match_pattern_rule(
                STOCKIST_WORDING_RULE, page_context.extracted_text, page_type=page_context.page_type
            )
        )
        ownership = "stockist" if is_stockist_page else "owned"

        drafts: list[FactCandidateDraft] = []
        location_types: list[str] = []
        for entity in store_entities:
            location_type = _classify_location_type(entity, page_context.extracted_text)
            location_types.append(location_type)
            drafts.append(self._location_candidate(page_context, entity, location_type, ownership))

        drafts.extend(self._page_level_counts(page_context, location_types, ownership))
        drafts.extend(self._pickup_available(page_context))
        drafts.extend(self._returns_location_count(page_context, store_entities))
        return drafts

    def _location_candidate(
        self, page_context: PageContext, entity: dict, location_type: str, ownership: str
    ) -> FactCandidateDraft:
        raw_address = entity.get("address")
        address: dict = raw_address if isinstance(raw_address, dict) else {}
        raw_geo = entity.get("geo")
        geo: dict = raw_geo if isinstance(raw_geo, dict) else {}
        name = entity.get("name") or ""
        normalized_key = _normalize_address(entity) or collapse_whitespace(str(name)).lower()
        value = {
            "location_type": location_type,
            "ownership": ownership,
            "name": name,
            "address_line": address.get("streetAddress"),
            "suburb": None,
            "city": address.get("addressLocality"),
            "region": address.get("addressRegion"),
            "postal_code": address.get("postalCode"),
            "country": address.get("addressCountry"),
            "phone": entity.get("telephone"),
            "latitude": geo.get("latitude"),
            "longitude": geo.get("longitude"),
            "source_wording": name,
        }
        evidence = build_evidence_draft(
            page_context=page_context,
            field_path=FieldPath.OPERATIONS_LOCATIONS,
            evidence_type=EvidenceType.JSON_LD,
            strength=EvidenceStrength.STRONG,
            source_fragment=f"{name} {normalized_key}".strip(),
            extractor_id=EXTRACTOR_ID,
            extractor_version=EXTRACTOR_VERSION,
            raw_value=str(name),
            normalized_value=normalized_key,
        )
        return build_candidate_draft(
            field_path=FieldPath.OPERATIONS_LOCATIONS,
            value=value,
            normalized_value=value,
            value_type=FieldValueType.STRUCTURED_ENTITY_LIST,
            source_type=FactSourceType.JSON_LD,
            confidence=82 if ownership == "owned" else 70,
            verification_state=VerificationState.VERIFIED
            if ownership == "owned"
            else VerificationState.MEASURED,
            evidence_drafts=[evidence],
            qualifiers={
                "rule_id": "operations.locations.structured_data",
                "dedup_key": normalized_key,
                "ownership": ownership,
            },
        )

    def _page_level_counts(
        self, page_context: PageContext, location_types: list[str], ownership: str
    ) -> list[FactCandidateDraft]:
        if ownership != "owned" or page_context.page_type not in (
            PageType.STORE_LOCATOR,
            PageType.CONTACT,
        ):
            return []
        drafts = []
        for location_type, field_path in _COUNT_FIELD_BY_LOCATION_TYPE.items():
            count = location_types.count(location_type)
            if count == 0:
                continue
            evidence = build_evidence_draft(
                page_context=page_context,
                field_path=field_path,
                evidence_type=EvidenceType.JSON_LD,
                strength=EvidenceStrength.STRONG,
                source_fragment=f"{count} {location_type} location(s) listed",
                extractor_id=EXTRACTOR_ID,
                extractor_version=EXTRACTOR_VERSION,
                raw_value=str(count),
                normalized_value=str(count),
            )
            drafts.append(
                build_candidate_draft(
                    field_path=field_path,
                    value=count,
                    normalized_value=count,
                    value_type=FieldValueType.INTEGER,
                    source_type=FactSourceType.JSON_LD,
                    confidence=78,
                    verification_state=VerificationState.MEASURED,
                    evidence_drafts=[evidence],
                    qualifiers={
                        "rule_id": f"operations.{location_type}_count.store_locator_listing",
                        "exact": True,
                        "estimation_method": "exact",
                    },
                )
            )
        return drafts

    def _pickup_available(self, page_context: PageContext) -> list[FactCandidateDraft]:
        drafts = []
        for match in match_pattern_rule(
            PICKUP_AVAILABLE_RULE, page_context.extracted_text, page_type=page_context.page_type
        ):
            evidence = build_evidence_draft(
                page_context=page_context,
                field_path=FieldPath.OPERATIONS_PICKUP_AVAILABLE,
                evidence_type=EvidenceType.PAGE_TEXT,
                strength=PICKUP_AVAILABLE_RULE.evidence_strength,
                source_fragment=match.matched_text,
                extractor_id=EXTRACTOR_ID,
                extractor_version=EXTRACTOR_VERSION,
                raw_value=match.matched_text,
                normalized_value="true",
            )
            drafts.append(
                build_candidate_draft(
                    field_path=FieldPath.OPERATIONS_PICKUP_AVAILABLE,
                    value=True,
                    normalized_value=True,
                    value_type=FieldValueType.BOOLEAN,
                    source_type=FactSourceType.HTML_ELEMENT,
                    confidence=PICKUP_AVAILABLE_RULE.base_confidence,
                    verification_state=VerificationState.MEASURED,
                    evidence_drafts=[evidence],
                    qualifiers={"rule_id": PICKUP_AVAILABLE_RULE.rule_id},
                )
            )
        return drafts

    def _returns_location_count(
        self, page_context: PageContext, store_entities: list[dict]
    ) -> list[FactCandidateDraft]:
        if page_context.page_type != PageType.RETURNS or not store_entities:
            return []
        count = len(store_entities)
        evidence = build_evidence_draft(
            page_context=page_context,
            field_path=FieldPath.OPERATIONS_RETURNS_LOCATION_COUNT,
            evidence_type=EvidenceType.JSON_LD,
            strength=EvidenceStrength.MODERATE,
            source_fragment=f"{count} returns location(s) listed",
            extractor_id=EXTRACTOR_ID,
            extractor_version=EXTRACTOR_VERSION,
            raw_value=str(count),
            normalized_value=str(count),
        )
        return [
            build_candidate_draft(
                field_path=FieldPath.OPERATIONS_RETURNS_LOCATION_COUNT,
                value=count,
                normalized_value=count,
                value_type=FieldValueType.INTEGER,
                source_type=FactSourceType.JSON_LD,
                confidence=70,
                verification_state=VerificationState.MEASURED,
                evidence_drafts=[evidence],
                qualifiers={
                    "rule_id": "operations.returns_location_count.returns_page_listing",
                    "exact": True,
                    "estimation_method": "exact",
                },
            )
        ]
