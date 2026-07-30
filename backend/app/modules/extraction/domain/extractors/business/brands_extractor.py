"""Brand-list extractor: explicit brand lists from JSON-LD `brand` fields
and a dedicated brands-navigation page (`PageType.BRANDS`) only — never
guessed from arbitrary product wording."""

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
    flatten_json_ld_entities,
    parse_page_structure,
)
from app.modules.extraction.domain.models import ExtractorDefinition

EXTRACTOR_ID = "business.brands"
EXTRACTOR_VERSION = "v1"


def _brand_names_from_entity(entity: dict) -> list[str]:
    brand = entity.get("brand")
    names: list[str] = []
    if isinstance(brand, str) and brand.strip():
        names.append(brand.strip())
    elif isinstance(brand, dict):
        name = brand.get("name")
        if isinstance(name, str) and name.strip():
            names.append(name.strip())
    return names


class BrandsExtractor:
    def definition(self) -> ExtractorDefinition:
        return ExtractorDefinition(
            extractor_id=EXTRACTOR_ID,
            name="Brand-list extractor",
            version=EXTRACTOR_VERSION,
            supported_page_types=[PageType.BRANDS, PageType.PRODUCT],
            output_field_paths=[FieldPath.BUSINESS_BRANDS],
            priority=60,
        )

    def supports(self, page_context: PageContext) -> bool:
        return page_context.page_type in (PageType.BRANDS, PageType.PRODUCT)

    def extract(self, page_context: PageContext) -> list[FactCandidateDraft]:
        structure = parse_page_structure(page_context.cleaned_html)
        entities = flatten_json_ld_entities(structure.json_ld_blocks)

        brand_names: list[str] = []
        for entity in entities:
            brand_names.extend(_brand_names_from_entity(entity))

        if page_context.page_type == PageType.BRANDS:
            for anchor in structure.anchors:
                href = anchor.get("href", "")
                text = anchor.get("text", "")
                if "/brand" in href.lower() and text:
                    brand_names.append(text)

        deduped = sorted({name for name in brand_names if name})
        if not deduped:
            return []

        drafts = []
        for name in deduped:
            evidence = build_evidence_draft(
                page_context=page_context,
                field_path=FieldPath.BUSINESS_BRANDS,
                evidence_type=EvidenceType.JSON_LD
                if page_context.page_type == PageType.PRODUCT
                else EvidenceType.LINK_TARGET,
                strength=EvidenceStrength.MODERATE,
                source_fragment=name,
                extractor_id=EXTRACTOR_ID,
                extractor_version=EXTRACTOR_VERSION,
                raw_value=name,
                normalized_value=name.lower(),
            )
            drafts.append(
                build_candidate_draft(
                    field_path=FieldPath.BUSINESS_BRANDS,
                    value=name,
                    normalized_value=name.lower(),
                    value_type=FieldValueType.STRING_LIST,
                    source_type=FactSourceType.JSON_LD
                    if page_context.page_type == PageType.PRODUCT
                    else FactSourceType.LINK,
                    confidence=70,
                    verification_state=VerificationState.MEASURED,
                    evidence_drafts=[evidence],
                    qualifiers={
                        "rule_id": "business.brands.explicit_list",
                        "dedup_key": name.lower(),
                    },
                )
            )
        return drafts
