"""Unit tests for the identity extractor family (AC-03, AC-04, AC-05)."""

from app.modules.discovery.domain.enums import PageType
from app.modules.extraction.domain.enums import FactSourceType, VerificationState
from app.modules.extraction.domain.extractors.identity.company_name_extractor import (
    CompanyNameExtractor,
)
from app.modules.extraction.domain.extractors.identity.country_city_extractor import (
    CountryCityExtractor,
)
from app.modules.extraction.domain.extractors.identity.language_extractor import LanguageExtractor
from app.modules.extraction.domain.extractors.identity.trading_name_extractor import (
    TradingNameExtractor,
)
from app.modules.extraction.domain.field_catalogue import FieldPath

from ..conftest import make_page_context, read_fixture


def test_company_name_priority_chain():
    jsonld_html = read_fixture("homepage-jsonld-organisation.html")
    jsonld_page = make_page_context(html=jsonld_html, page_type=PageType.HOMEPAGE)
    jsonld_candidates = CompanyNameExtractor().extract(jsonld_page)
    jsonld_winner = max(jsonld_candidates, key=lambda c: c.confidence)
    assert jsonld_winner.source_type == FactSourceType.JSON_LD
    assert jsonld_winner.normalized_value == "Southbank Trading Co"

    custom_html = read_fixture("homepage-custom.html")
    custom_page = make_page_context(html=custom_html, page_type=PageType.HOMEPAGE)
    custom_candidates = CompanyNameExtractor().extract(custom_page)
    custom_winner = max(custom_candidates, key=lambda c: c.confidence)
    assert custom_winner.source_type != FactSourceType.JSON_LD
    assert custom_winner.confidence < jsonld_winner.confidence


def test_deterministic_output_and_input_not_mutated():
    html = read_fixture("homepage-shopify.html")
    page = make_page_context(html=html, page_type=PageType.HOMEPAGE)
    extractor = CompanyNameExtractor()
    before = page.model_dump()
    first = extractor.extract(page)
    second = extractor.extract(page)
    assert first == second
    assert page.model_dump() == before


def test_conflicting_city_preserved():
    html = read_fixture("contact-multiple-locations.html")
    page = make_page_context(html=html, page_type=PageType.CONTACT)
    candidates = CountryCityExtractor().extract(page)
    cities = {c.normalized_value for c in candidates if c.field_path == FieldPath.IDENTITY_CITY}
    assert "Melbourne" in cities
    assert "Sydney" in cities


def test_tld_never_verified():
    html = "<html><head><title>Home</title></head><body>Welcome</body></html>"
    page = make_page_context(
        html=html,
        page_type=PageType.HOMEPAGE,
        source_url="https://example.com.au/",
        normalized_url="https://example.com.au/",
    )
    candidates = CountryCityExtractor().extract(page)
    tld_candidates = [c for c in candidates if c.field_path == FieldPath.IDENTITY_COUNTRY]
    assert tld_candidates
    for candidate in tld_candidates:
        assert candidate.verification_state != VerificationState.VERIFIED


def test_trading_name_from_about_page():
    html = read_fixture("about-company.html")
    page = make_page_context(html=html, page_type=PageType.ABOUT)
    candidates = TradingNameExtractor().extract(page)
    assert candidates
    assert any("Willow" in str(c.normalized_value) for c in candidates)


def test_legal_and_trading_name_distinguishable():
    assert FieldPath.IDENTITY_COMPANY_NAME != FieldPath.IDENTITY_TRADING_NAME


def test_language_from_html_lang():
    html = read_fixture("homepage-shopify.html")
    page = make_page_context(html=html, page_type=PageType.HOMEPAGE)
    candidates = LanguageExtractor().extract(page)
    assert any(c.normalized_value == "en" for c in candidates)


def test_no_city_from_phone_number():
    html = "<html><body><p>Call us on +61 3 9999 9999</p></body></html>"
    page = make_page_context(html=html, page_type=PageType.CONTACT)
    candidates = CountryCityExtractor().extract(page)
    city_candidates = [c for c in candidates if c.field_path == FieldPath.IDENTITY_CITY]
    assert city_candidates == []
