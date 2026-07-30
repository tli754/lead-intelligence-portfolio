"""Unit tests for the business-model extractor family (AC-03, AC-06, AC-07)."""

from app.modules.discovery.domain.enums import PageType
from app.modules.extraction.domain.extractors.business.brands_extractor import BrandsExtractor
from app.modules.extraction.domain.extractors.business.business_model_extractor import (
    BusinessModelExtractor,
)
from app.modules.extraction.domain.field_catalogue import FieldPath

from ..conftest import make_page_context, read_fixture


def test_wholesale_positive():
    html = read_fixture("wholesale-explicit.html")
    page = make_page_context(html=html, page_type=PageType.WHOLESALE)
    candidates = BusinessModelExtractor().extract(page)
    wholesale = [c for c in candidates if c.field_path == FieldPath.BUSINESS_WHOLESALE]
    assert wholesale
    assert all(c.confidence >= 70 for c in wholesale)


def test_wholesale_false_positive_rejected():
    html = read_fixture("wholesale-false-positive.html")
    page = make_page_context(html=html, page_type=PageType.UNKNOWN)
    candidates = BusinessModelExtractor().extract(page)
    wholesale = [c for c in candidates if c.field_path == FieldPath.BUSINESS_WHOLESALE]
    trade = [c for c in candidates if c.field_path == FieldPath.BUSINESS_TRADE_ACCOUNTS]
    assert wholesale == []
    assert trade == []


def test_trade_account_positive():
    html = read_fixture("trade-account.html")
    page = make_page_context(html=html, page_type=PageType.TRADE)
    candidates = BusinessModelExtractor().extract(page)
    trade = [c for c in candidates if c.field_path == FieldPath.BUSINESS_TRADE_ACCOUNTS]
    assert trade


def test_click_and_collect_positive():
    html = read_fixture("click-and-collect.html")
    page = make_page_context(html=html, page_type=PageType.SHIPPING)
    candidates = BusinessModelExtractor().extract(page)
    matches = [c for c in candidates if c.field_path == FieldPath.BUSINESS_CLICK_AND_COLLECT]
    assert matches


def test_subscription_positive():
    html = read_fixture("subscription.html")
    page = make_page_context(html=html, page_type=PageType.SUBSCRIPTION)
    candidates = BusinessModelExtractor().extract(page)
    matches = [c for c in candidates if c.field_path == FieldPath.BUSINESS_SUBSCRIPTION]
    assert matches


def test_booking_positive():
    html = "<html><body><p>Book appointment online, or use our booking form.</p></body></html>"
    page = make_page_context(html=html, page_type=PageType.UNKNOWN)
    candidates = BusinessModelExtractor().extract(page)
    matches = [c for c in candidates if c.field_path == FieldPath.BUSINESS_BOOKING]
    assert matches


def test_explicit_online_only():
    html = read_fixture("online-only-explicit.html")
    page = make_page_context(html=html, page_type=PageType.ABOUT)
    candidates = BusinessModelExtractor().extract(page)
    matches = [c for c in candidates if c.field_path == FieldPath.BUSINESS_ONLINE_ONLY]
    assert matches
    assert all(c.value is True for c in matches)


def test_no_online_only_inference_from_missing_stores():
    html = "<html><body><p>Welcome to our shop.</p></body></html>"
    page = make_page_context(html=html, page_type=PageType.HOMEPAGE)
    candidates = BusinessModelExtractor().extract(page)
    matches = [c for c in candidates if c.field_path == FieldPath.BUSINESS_ONLINE_ONLY]
    assert matches == []


def test_custom_product_positive():
    html = read_fixture("product-customization.html")
    page = make_page_context(html=html, page_type=PageType.PRODUCT)
    candidates = BusinessModelExtractor().extract(page)
    matches = [c for c in candidates if c.field_path == FieldPath.BUSINESS_CUSTOM_PRODUCTS]
    assert matches


def test_brand_extraction():
    html = read_fixture("product-variants.html")
    page = make_page_context(html=html, page_type=PageType.PRODUCT)
    candidates = BrandsExtractor().extract(page)
    assert any(c.normalized_value == "alpine supply co" for c in candidates)


def test_deterministic_output_and_input_not_mutated():
    html = read_fixture("wholesale-explicit.html")
    page = make_page_context(html=html, page_type=PageType.WHOLESALE)
    extractor = BusinessModelExtractor()
    before = page.model_dump()
    assert extractor.extract(page) == extractor.extract(page)
    assert page.model_dump() == before
