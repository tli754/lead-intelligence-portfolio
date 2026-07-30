"""Catalogue extractors (brief section 7).

**Documented scope limitation:** `PageContext` is scoped to a single page
— this extractor cannot itself aggregate "product count x observed
median variants across the whole site" (brief section 7's SKU-estimate
priority #2), since that requires whole-catalogue context no single-page
`extract()` call has. Where a page's own local data already carries that
aggregate (via `PageContext.page_metadata["known_product_count"]` /
`["observed_median_variants"]` / `["variant_sample_size"]` — an
extraction-owned, narrow dict a future sitemap/aggregation step could
populate), this extractor honors it, applying the "insufficient sample
size stays unknown" rule (`MIN_VARIANT_SAMPLE_SIZE`). Otherwise it
correctly stays silent rather than guessing.
"""

import re

from app.modules.discovery.domain.enums import PageType
from app.modules.evidence.domain.enums import EvidenceStrength, EvidenceType
from app.modules.extraction.domain.candidate_builder import (
    build_candidate_draft,
    build_evidence_draft,
)
from app.modules.extraction.domain.enums import FactSourceType, VerificationState
from app.modules.extraction.domain.extractor import FactCandidateDraft, PageContext
from app.modules.extraction.domain.extractors.catalogue.patterns import (
    BUNDLE_EVIDENCE_RULE,
    CUSTOMIZATION_TEXT_RULE,
)
from app.modules.extraction.domain.field_catalogue import FieldPath, FieldValueType
from app.modules.extraction.domain.html_helpers import (
    flatten_json_ld_entities,
    parse_page_structure,
)
from app.modules.extraction.domain.models import ExtractorDefinition
from app.modules.extraction.domain.pattern_types import match_pattern_rule

EXTRACTOR_ID = "catalogue.product_signals"
EXTRACTOR_VERSION = "v1"

MIN_VARIANT_SAMPLE_SIZE = 5

_PAGINATION_TOTAL_PATTERN = re.compile(r"page\s+\d+\s+of\s+(\d+)", re.IGNORECASE)
_FILE_INPUT_PATTERN = re.compile(r'<input[^>]+type="file"', re.IGNORECASE)
_CUSTOM_INPUT_PATTERN = re.compile(
    r'<input[^>]+(?:name|id|class)="[^"]*(?:engrav|personali[sz]|monogram|custom-text)[^"]*"',
    re.IGNORECASE,
)
_VARIANT_SELECT_PATTERN = re.compile(
    r'<select[^>]+(?:name|id|class)="[^"]*(?:variant|size|colou?r)[^"]*"', re.IGNORECASE
)


class CatalogueExtractor:
    def definition(self) -> ExtractorDefinition:
        return ExtractorDefinition(
            extractor_id=EXTRACTOR_ID,
            name="Catalogue extractor",
            version=EXTRACTOR_VERSION,
            supported_page_types=[],
            output_field_paths=[
                FieldPath.CATALOGUE_PRODUCT_COUNT,
                FieldPath.CATALOGUE_PRODUCT_COUNT_ESTIMATE,
                FieldPath.CATALOGUE_SKU_COUNT_ESTIMATE,
                FieldPath.CATALOGUE_VARIANT_EVIDENCE,
                FieldPath.CATALOGUE_COLLECTION_COUNT,
                FieldPath.CATALOGUE_BUNDLE_EVIDENCE,
                FieldPath.CATALOGUE_CUSTOMIZATION_EVIDENCE,
            ],
            priority=55,
        )

    def supports(self, page_context: PageContext) -> bool:
        return True

    def extract(self, page_context: PageContext) -> list[FactCandidateDraft]:
        drafts: list[FactCandidateDraft] = []
        drafts.extend(self._product_count(page_context))
        drafts.extend(self._sku_count_estimate(page_context))
        drafts.extend(self._collection_count(page_context))
        drafts.extend(self._variant_evidence(page_context))
        drafts.extend(
            self._pattern_signal(
                page_context, BUNDLE_EVIDENCE_RULE, FieldPath.CATALOGUE_BUNDLE_EVIDENCE
            )
        )
        drafts.extend(self._customization_evidence(page_context))
        return drafts

    # --- Product count (5-step priority) --------------------------------

    def _product_count(self, page_context: PageContext) -> list[FactCandidateDraft]:
        meta = page_context.page_metadata

        sitemap_count = meta.get("sitemap_product_url_count")
        if isinstance(sitemap_count, int):
            return [
                self._numeric_candidate(
                    page_context,
                    field_path=FieldPath.CATALOGUE_PRODUCT_COUNT,
                    count=sitemap_count,
                    confidence=90,
                    source_type=FactSourceType.SITEMAP_SUMMARY,
                    rule_id="catalogue.product_count.sitemap_url_classification",
                    exact=True,
                )
            ]

        if page_context.page_type in (PageType.COLLECTION, PageType.CATEGORY):
            structure = parse_page_structure(page_context.cleaned_html)
            entities = flatten_json_ld_entities(structure.json_ld_blocks)
            for entity in entities:
                number_of_items = entity.get("numberOfItems")
                if isinstance(number_of_items, int):
                    return [
                        self._numeric_candidate(
                            page_context,
                            field_path=FieldPath.CATALOGUE_PRODUCT_COUNT,
                            count=number_of_items,
                            confidence=82,
                            source_type=FactSourceType.JSON_LD,
                            rule_id="catalogue.product_count.platform_total_json_ld",
                            exact=True,
                        )
                    ]

            product_links = self._distinct_product_links(structure)
            pagination_match = _PAGINATION_TOTAL_PATTERN.search(page_context.extracted_text)
            if pagination_match and product_links:
                last_page = int(pagination_match.group(1))
                estimate = last_page * len(product_links)
                return [
                    self._numeric_candidate(
                        page_context,
                        field_path=FieldPath.CATALOGUE_PRODUCT_COUNT_ESTIMATE,
                        count=estimate,
                        confidence=60,
                        source_type=FactSourceType.DETERMINISTIC_INFERENCE,
                        rule_id="catalogue.product_count.pagination_derived_estimate",
                        exact=False,
                        estimation_method="pagination_derived",
                        sample_size=len(product_links),
                    )
                ]

            if product_links:
                return [
                    self._numeric_candidate(
                        page_context,
                        field_path=FieldPath.CATALOGUE_PRODUCT_COUNT_ESTIMATE,
                        count=len(product_links),
                        confidence=40,
                        source_type=FactSourceType.DETERMINISTIC_INFERENCE,
                        rule_id="catalogue.product_count.sampled_collection_estimate",
                        exact=False,
                        estimation_method="sampled_collection",
                        sample_size=len(product_links),
                    )
                ]

        return []

    def _distinct_product_links(self, structure) -> list[str]:
        hrefs = {
            anchor["href"]
            for anchor in structure.anchors
            if "/products/" in anchor.get("href", "") or "/product/" in anchor.get("href", "")
        }
        return sorted(hrefs)

    # --- SKU-count estimate ------------------------------------------------

    def _sku_count_estimate(self, page_context: PageContext) -> list[FactCandidateDraft]:
        meta = page_context.page_metadata
        product_count = meta.get("known_product_count")
        median_variants = meta.get("observed_median_variants")
        sample_size = meta.get("variant_sample_size", 0)
        if not product_count or not median_variants or sample_size < MIN_VARIANT_SAMPLE_SIZE:
            return []
        estimate = int(round(float(product_count) * float(median_variants)))
        return [
            self._numeric_candidate(
                page_context,
                field_path=FieldPath.CATALOGUE_SKU_COUNT_ESTIMATE,
                count=estimate,
                confidence=55,
                source_type=FactSourceType.DETERMINISTIC_INFERENCE,
                rule_id="catalogue.sku_count_estimate.product_count_x_median_variants",
                exact=False,
                estimation_method="product_count_x_median_variants",
                sample_size=sample_size,
            )
        ]

    # --- Collection count ----------------------------------------------------

    def _collection_count(self, page_context: PageContext) -> list[FactCandidateDraft]:
        meta = page_context.page_metadata
        sitemap_count = meta.get("sitemap_collection_url_count")
        if isinstance(sitemap_count, int):
            return [
                self._numeric_candidate(
                    page_context,
                    field_path=FieldPath.CATALOGUE_COLLECTION_COUNT,
                    count=sitemap_count,
                    confidence=88,
                    source_type=FactSourceType.SITEMAP_SUMMARY,
                    rule_id="catalogue.collection_count.sitemap_url_classification",
                    exact=True,
                )
            ]

        structure = parse_page_structure(page_context.cleaned_html)
        hrefs = {
            anchor["href"]
            for anchor in structure.anchors
            if re.search(r"/(collections|categor(?:y|ies))/", anchor.get("href", ""))
        }
        if not hrefs:
            return []
        return [
            self._numeric_candidate(
                page_context,
                field_path=FieldPath.CATALOGUE_COLLECTION_COUNT,
                count=len(hrefs),
                confidence=50,
                source_type=FactSourceType.DETERMINISTIC_INFERENCE,
                rule_id="catalogue.collection_count.navigation_link_count",
                exact=False,
                estimation_method="counted_navigation_links",
                sample_size=len(hrefs),
            )
        ]

    # --- Variant evidence ------------------------------------------------

    def _variant_evidence(self, page_context: PageContext) -> list[FactCandidateDraft]:
        if page_context.page_type != PageType.PRODUCT:
            return []
        has_selector = bool(_VARIANT_SELECT_PATTERN.search(page_context.cleaned_html))

        structure = parse_page_structure(page_context.cleaned_html)
        entities = flatten_json_ld_entities(structure.json_ld_blocks)
        has_multiple_offers = any(
            isinstance(entity.get("offers"), list) and len(entity["offers"]) > 1
            for entity in entities
        )

        if not (has_selector or has_multiple_offers):
            return []
        source_fragment = "variant selector control" if has_selector else "multiple JSON-LD offers"
        evidence = build_evidence_draft(
            page_context=page_context,
            field_path=FieldPath.CATALOGUE_VARIANT_EVIDENCE,
            evidence_type=EvidenceType.HTML_ATTRIBUTE if has_selector else EvidenceType.JSON_LD,
            strength=EvidenceStrength.MODERATE,
            source_fragment=source_fragment,
            extractor_id=EXTRACTOR_ID,
            extractor_version=EXTRACTOR_VERSION,
            raw_value=source_fragment,
            normalized_value="true",
        )
        return [
            build_candidate_draft(
                field_path=FieldPath.CATALOGUE_VARIANT_EVIDENCE,
                value=True,
                normalized_value=True,
                value_type=FieldValueType.BOOLEAN,
                source_type=FactSourceType.HTML_ELEMENT if has_selector else FactSourceType.JSON_LD,
                confidence=68,
                verification_state=VerificationState.MEASURED,
                evidence_drafts=[evidence],
                qualifiers={"rule_id": "catalogue.variant_evidence.selector_or_offers"},
            )
        ]

    # --- Customization evidence --------------------------------------------

    def _customization_evidence(self, page_context: PageContext) -> list[FactCandidateDraft]:
        drafts = self._pattern_signal(
            page_context, CUSTOMIZATION_TEXT_RULE, FieldPath.CATALOGUE_CUSTOMIZATION_EVIDENCE
        )
        html = page_context.cleaned_html
        form_signal = _FILE_INPUT_PATTERN.search(html) or _CUSTOM_INPUT_PATTERN.search(html)
        if form_signal:
            evidence = build_evidence_draft(
                page_context=page_context,
                field_path=FieldPath.CATALOGUE_CUSTOMIZATION_EVIDENCE,
                evidence_type=EvidenceType.FORM_FIELD,
                strength=EvidenceStrength.STRONG,
                source_fragment=form_signal.group(0),
                extractor_id=EXTRACTOR_ID,
                extractor_version=EXTRACTOR_VERSION,
                raw_value=form_signal.group(0),
                normalized_value="true",
            )
            drafts.append(
                build_candidate_draft(
                    field_path=FieldPath.CATALOGUE_CUSTOMIZATION_EVIDENCE,
                    value=True,
                    normalized_value=True,
                    value_type=FieldValueType.BOOLEAN,
                    source_type=FactSourceType.FORM,
                    confidence=75,
                    verification_state=VerificationState.MEASURED,
                    evidence_drafts=[evidence],
                    qualifiers={"rule_id": "catalogue.customization_evidence.form_control"},
                )
            )
        return drafts

    # --- Shared helpers -----------------------------------------------------

    def _pattern_signal(self, page_context, rule, field_path) -> list[FactCandidateDraft]:
        drafts = []
        for match in match_pattern_rule(
            rule, page_context.extracted_text, page_type=page_context.page_type
        ):
            evidence = build_evidence_draft(
                page_context=page_context,
                field_path=field_path,
                evidence_type=EvidenceType.PAGE_TEXT,
                strength=rule.evidence_strength,
                source_fragment=match.matched_text,
                extractor_id=EXTRACTOR_ID,
                extractor_version=EXTRACTOR_VERSION,
                raw_value=match.matched_text,
                normalized_value="true",
            )
            drafts.append(
                build_candidate_draft(
                    field_path=field_path,
                    value=True,
                    normalized_value=True,
                    value_type=FieldValueType.BOOLEAN,
                    source_type=FactSourceType.HTML_ELEMENT,
                    confidence=rule.base_confidence,
                    verification_state=VerificationState.MEASURED,
                    evidence_drafts=[evidence],
                    qualifiers={"rule_id": rule.rule_id},
                )
            )
        return drafts

    def _numeric_candidate(
        self,
        page_context: PageContext,
        *,
        field_path: FieldPath,
        count: int,
        confidence: int,
        source_type: FactSourceType,
        rule_id: str,
        exact: bool,
        estimation_method: str | None = None,
        sample_size: int | None = None,
    ) -> FactCandidateDraft:
        qualifiers = {"rule_id": rule_id, "exact": exact}
        if exact:
            qualifiers["estimation_method"] = "exact"
        else:
            qualifiers["estimation_method"] = estimation_method
            qualifiers["sample_size"] = sample_size
        evidence = build_evidence_draft(
            page_context=page_context,
            field_path=field_path,
            evidence_type=EvidenceType.SITEMAP_METADATA
            if source_type == FactSourceType.SITEMAP_SUMMARY
            else EvidenceType.PAGE_METADATA,
            strength=EvidenceStrength.STRONG if exact else EvidenceStrength.WEAK,
            source_fragment=f"count={count}",
            extractor_id=EXTRACTOR_ID,
            extractor_version=EXTRACTOR_VERSION,
            raw_value=str(count),
            normalized_value=str(count),
        )
        return build_candidate_draft(
            field_path=field_path,
            value=count,
            normalized_value=count,
            value_type=FieldValueType.INTEGER,
            source_type=source_type,
            confidence=confidence,
            verification_state=VerificationState.MEASURED if exact else VerificationState.INFERRED,
            evidence_drafts=[evidence],
            qualifiers=qualifiers,
        )
