"""Unit tests for the physical-operations extractor family (AC-03, AC-09)."""

from app.modules.discovery.domain.enums import PageType
from app.modules.extraction.domain.extractors.operations.operations_extractor import (
    OperationsExtractor,
)
from app.modules.extraction.domain.field_catalogue import FieldPath

from ..conftest import make_page_context, read_fixture


def test_json_ld_store_location():
    html = read_fixture("store-locator-owned.html")
    page = make_page_context(html=html, page_type=PageType.STORE_LOCATOR)
    candidates = OperationsExtractor().extract(page)
    locations = [c for c in candidates if c.field_path == FieldPath.OPERATIONS_LOCATIONS]
    assert len(locations) == 2
    assert all(c.normalized_value["ownership"] == "owned" for c in locations)


def test_multiple_stores_counted():
    html = read_fixture("store-locator-owned.html")
    page = make_page_context(html=html, page_type=PageType.STORE_LOCATOR)
    candidates = OperationsExtractor().extract(page)
    counts = [c for c in candidates if c.field_path == FieldPath.OPERATIONS_RETAIL_STORE_COUNT]
    assert counts
    assert counts[0].value == 2
    assert counts[0].qualifiers["exact"] is True


def test_warehouse_wording_classification():
    html = read_fixture("warehouse-and-showroom.html")
    page = make_page_context(html=html, page_type=PageType.UNKNOWN)
    candidates = OperationsExtractor().extract(page)
    locations = [c for c in candidates if c.field_path == FieldPath.OPERATIONS_LOCATIONS]
    assert any(c.normalized_value["location_type"] == "warehouse" for c in locations)


def test_showroom_wording_classification():
    html = (
        '<html><body><script type="application/ld+json">'
        '{"@type": "Store", "name": "Design Space"}</script>'
        "<p>Visit our showroom this weekend.</p></body></html>"
    )
    page = make_page_context(html=html, page_type=PageType.UNKNOWN)
    candidates = OperationsExtractor().extract(page)
    locations = [c for c in candidates if c.field_path == FieldPath.OPERATIONS_LOCATIONS]
    assert any(c.normalized_value["location_type"] == "showroom" for c in locations)


def test_pickup_location():
    html = "<html><body><p>Curbside pickup is available at our warehouse.</p></body></html>"
    page = make_page_context(html=html, page_type=PageType.SHIPPING)
    candidates = OperationsExtractor().extract(page)
    pickup = [c for c in candidates if c.field_path == FieldPath.OPERATIONS_PICKUP_AVAILABLE]
    assert pickup
    assert all(c.value is True for c in pickup)


def test_stockist_not_counted_as_owned():
    html = read_fixture("store-locator-stockists.html")
    page = make_page_context(html=html, page_type=PageType.STORE_LOCATOR)
    candidates = OperationsExtractor().extract(page)
    locations = [c for c in candidates if c.field_path == FieldPath.OPERATIONS_LOCATIONS]
    assert locations
    assert all(c.normalized_value["ownership"] == "stockist" for c in locations)
    owned_counts = [
        c for c in candidates if c.field_path == FieldPath.OPERATIONS_RETAIL_STORE_COUNT
    ]
    assert owned_counts == []


def test_duplicate_address_deduplicated_by_key():
    html = read_fixture("store-locator-owned.html")
    page = make_page_context(html=html, page_type=PageType.STORE_LOCATOR, page_id="page-a")
    candidates_a = OperationsExtractor().extract(page)
    page_dup = make_page_context(html=html, page_type=PageType.CONTACT, page_id="page-b")
    candidates_b = OperationsExtractor().extract(page_dup)

    dedup_keys_a = {
        c.qualifiers["dedup_key"]
        for c in candidates_a
        if c.field_path == FieldPath.OPERATIONS_LOCATIONS
    }
    dedup_keys_b = {
        c.qualifiers["dedup_key"]
        for c in candidates_b
        if c.field_path == FieldPath.OPERATIONS_LOCATIONS
    }
    # Same underlying addresses appearing on two different pages produce
    # the same dedup keys — reconciliation (not this extractor) is what
    # actually collapses them into a single `LocationCandidate`.
    assert dedup_keys_a == dedup_keys_b


def test_conflicting_location_types_preserved_independently():
    html = read_fixture("warehouse-and-showroom.html")
    page = make_page_context(html=html, page_type=PageType.UNKNOWN)
    candidates = OperationsExtractor().extract(page)
    types = {
        c.normalized_value["location_type"]
        for c in candidates
        if c.field_path == FieldPath.OPERATIONS_LOCATIONS
    }
    assert "warehouse" in types


def test_deterministic_output_and_input_not_mutated():
    html = read_fixture("store-locator-owned.html")
    page = make_page_context(html=html, page_type=PageType.STORE_LOCATOR)
    extractor = OperationsExtractor()
    before = page.model_dump()
    assert extractor.extract(page) == extractor.extract(page)
    assert page.model_dump() == before
