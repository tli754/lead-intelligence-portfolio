"""Unit tests for the technology-signal extractor family (AC-03, AC-10)."""

from app.modules.discovery.domain.enums import PageType
from app.modules.extraction.domain.extractors.technology.signatures import (
    TECHNOLOGY_SIGNATURES_VERSION,
)
from app.modules.extraction.domain.extractors.technology.technology_extractor import (
    TechnologyExtractor,
)
from app.modules.extraction.domain.field_catalogue import FieldPath

from ..conftest import make_page_context, read_fixture


def test_signature_detection_rule_ids():
    html = read_fixture("technology-signatures.html")
    page = make_page_context(html=html, page_type=PageType.HOMEPAGE)
    candidates = TechnologyExtractor().extract(page)
    assert candidates
    for candidate in candidates:
        assert candidate.qualifiers.get("rule_id")
        assert (
            candidate.qualifiers.get("technology_signatures_version")
            == TECHNOLOGY_SIGNATURES_VERSION
        )

    technologies = {c.normalized_value for c in candidates}
    assert "shopify" in technologies
    assert "stripe" in technologies
    assert "yotpo" in technologies
    assert "intercom" in technologies
    assert "google_tag_manager" in technologies


def test_generic_cdn_no_false_positive():
    html = '<html><head><script src="https://d3js.org/d3.v7.min.js"></script></head><body>Home</body></html>'
    page = make_page_context(html=html, page_type=PageType.HOMEPAGE)
    candidates = TechnologyExtractor().extract(page)
    commerce = [c for c in candidates if c.field_path == FieldPath.TECHNOLOGY_COMMERCE_PLATFORM]
    assert commerce == []


def test_multiple_agreeing_signals_across_pages():
    html = read_fixture("homepage-shopify.html")
    page1 = make_page_context(html=html, page_type=PageType.HOMEPAGE, page_id="p1")
    page2 = make_page_context(html=html, page_type=PageType.HOMEPAGE, page_id="p2")
    candidates_1 = TechnologyExtractor().extract(page1)
    candidates_2 = TechnologyExtractor().extract(page2)
    shopify_1 = [c for c in candidates_1 if c.normalized_value == "shopify"]
    shopify_2 = [c for c in candidates_2 if c.normalized_value == "shopify"]
    assert shopify_1 and shopify_2


def test_conflicting_platform_markers_both_detected():
    html = read_fixture("technology-conflicting-platforms.html")
    page = make_page_context(html=html, page_type=PageType.HOMEPAGE)
    candidates = TechnologyExtractor().extract(page)
    commerce = {
        c.normalized_value
        for c in candidates
        if c.field_path == FieldPath.TECHNOLOGY_COMMERCE_PLATFORM
    }
    crm = {c.normalized_value for c in candidates if c.field_path == FieldPath.TECHNOLOGY_CRM}
    assert "shopify" in commerce
    assert "hubspot" in crm


def test_framework_versus_commerce_distinction():
    html = '<html><body data-reactroot="">Home</body></html>'
    page = make_page_context(html=html, page_type=PageType.HOMEPAGE)
    candidates = TechnologyExtractor().extract(page)
    frameworks = [c for c in candidates if c.field_path == FieldPath.TECHNOLOGY_FRAMEWORKS]
    commerce = [c for c in candidates if c.field_path == FieldPath.TECHNOLOGY_COMMERCE_PLATFORM]
    assert frameworks
    assert commerce == []


def test_absence_remains_unknown():
    html = "<html><body>Plain page with no scripts.</body></html>"
    page = make_page_context(html=html, page_type=PageType.HOMEPAGE)
    candidates = TechnologyExtractor().extract(page)
    assert candidates == []


def test_deterministic_output_and_input_not_mutated():
    html = read_fixture("technology-signatures.html")
    page = make_page_context(html=html, page_type=PageType.HOMEPAGE)
    extractor = TechnologyExtractor()
    before = page.model_dump()
    assert extractor.extract(page) == extractor.extract(page)
    assert page.model_dump() == before
