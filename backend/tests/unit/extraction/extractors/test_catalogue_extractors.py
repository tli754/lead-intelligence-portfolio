"""Unit tests for the catalogue extractor family (AC-03, AC-08)."""

from app.modules.discovery.domain.enums import PageType
from app.modules.extraction.domain.extractors.catalogue.catalogue_extractor import (
    MIN_VARIANT_SAMPLE_SIZE,
    CatalogueExtractor,
)
from app.modules.extraction.domain.field_catalogue import FieldPath

from ..conftest import make_page_context, read_fixture


def test_exact_sitemap_count_priority():
    html = "<html><body>Products</body></html>"
    page = make_page_context(
        html=html, page_type=PageType.COLLECTION, page_metadata={"sitemap_product_url_count": 240}
    )
    candidates = CatalogueExtractor().extract(page)
    exact = [c for c in candidates if c.field_path == FieldPath.CATALOGUE_PRODUCT_COUNT]
    assert exact
    assert exact[0].value == 240
    assert exact[0].qualifiers["exact"] is True


def test_pagination_estimate():
    html = read_fixture("collection-pagination.html")
    page = make_page_context(html=html, page_type=PageType.COLLECTION)
    candidates = CatalogueExtractor().extract(page)
    estimate = [c for c in candidates if c.field_path == FieldPath.CATALOGUE_PRODUCT_COUNT_ESTIMATE]
    assert estimate
    assert estimate[0].qualifiers["estimation_method"] == "pagination_derived"
    assert estimate[0].qualifiers["exact"] is False


def test_variant_extraction():
    html = read_fixture("product-variants.html")
    page = make_page_context(html=html, page_type=PageType.PRODUCT)
    candidates = CatalogueExtractor().extract(page)
    variants = [c for c in candidates if c.field_path == FieldPath.CATALOGUE_VARIANT_EVIDENCE]
    assert variants
    assert all(c.value is True for c in variants)


def test_sku_estimate_with_sufficient_sample():
    html = "<html><body>Product</body></html>"
    page = make_page_context(
        html=html,
        page_type=PageType.PRODUCT,
        page_metadata={
            "known_product_count": 100,
            "observed_median_variants": 3,
            "variant_sample_size": MIN_VARIANT_SAMPLE_SIZE,
        },
    )
    candidates = CatalogueExtractor().extract(page)
    sku = [c for c in candidates if c.field_path == FieldPath.CATALOGUE_SKU_COUNT_ESTIMATE]
    assert sku
    assert sku[0].value == 300


def test_insufficient_sample_remains_unknown():
    html = "<html><body>Product</body></html>"
    page = make_page_context(
        html=html,
        page_type=PageType.PRODUCT,
        page_metadata={
            "known_product_count": 100,
            "observed_median_variants": 3,
            "variant_sample_size": 1,
        },
    )
    candidates = CatalogueExtractor().extract(page)
    sku = [c for c in candidates if c.field_path == FieldPath.CATALOGUE_SKU_COUNT_ESTIMATE]
    assert sku == []


def test_collection_count_from_navigation():
    html = read_fixture("collection-pagination.html")
    page = make_page_context(html=html, page_type=PageType.COLLECTION)
    candidates = CatalogueExtractor().extract(page)
    collections = [c for c in candidates if c.field_path == FieldPath.CATALOGUE_COLLECTION_COUNT]
    assert collections
    assert collections[0].value == 2


def test_bundle_signal():
    html = read_fixture("product-variants.html")
    page = make_page_context(html=html, page_type=PageType.PRODUCT)
    candidates = CatalogueExtractor().extract(page)
    bundle = [c for c in candidates if c.field_path == FieldPath.CATALOGUE_BUNDLE_EVIDENCE]
    assert bundle


def test_customization_form():
    html = read_fixture("product-customization.html")
    page = make_page_context(html=html, page_type=PageType.PRODUCT)
    candidates = CatalogueExtractor().extract(page)
    customization = [
        c for c in candidates if c.field_path == FieldPath.CATALOGUE_CUSTOMIZATION_EVIDENCE
    ]
    assert customization
    assert any(c.confidence >= 70 for c in customization)


def test_collection_urls_never_counted_as_products():
    html = read_fixture("collection-pagination.html")
    page = make_page_context(html=html, page_type=PageType.COLLECTION)
    candidates = CatalogueExtractor().extract(page)
    estimate = next(
        c for c in candidates if c.field_path == FieldPath.CATALOGUE_PRODUCT_COUNT_ESTIMATE
    )
    # 3 product links x 4 pages = 12 — collection links must not inflate this.
    assert estimate.value == 12


def test_deterministic_output_and_input_not_mutated():
    html = read_fixture("product-variants.html")
    page = make_page_context(html=html, page_type=PageType.PRODUCT)
    extractor = CatalogueExtractor()
    before = page.model_dump()
    assert extractor.extract(page) == extractor.extract(page)
    assert page.model_dump() == before
