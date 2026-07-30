"""Unit tests for the organisation/contact extractor family (AC-03, AC-11, AC-12)."""

from app.modules.discovery.domain.enums import PageType
from app.modules.extraction.domain.extractors.organisation.organisation_extractor import (
    OrganisationExtractor,
)
from app.modules.extraction.domain.field_catalogue import FieldPath

from ..conftest import make_page_context, read_fixture


def test_mailto_email():
    html = read_fixture("contact-address.html")
    page = make_page_context(html=html, page_type=PageType.CONTACT)
    candidates = OrganisationExtractor().extract(page)
    emails = [c for c in candidates if c.field_path == FieldPath.ORGANISATION_EMAILS]
    assert any(c.normalized_value == "hello@example-store.com" for c in emails)


def test_visible_email():
    html = "<html><body><p>Contact sales@example-store.com for enquiries.</p></body></html>"
    page = make_page_context(html=html, page_type=PageType.CONTACT)
    candidates = OrganisationExtractor().extract(page)
    emails = [c for c in candidates if c.field_path == FieldPath.ORGANISATION_EMAILS]
    assert any(c.normalized_value == "sales@example-store.com" for c in emails)


def test_tel_phone():
    html = read_fixture("contact-address.html")
    page = make_page_context(html=html, page_type=PageType.CONTACT)
    candidates = OrganisationExtractor().extract(page)
    phones = [c for c in candidates if c.field_path == FieldPath.ORGANISATION_PHONE_NUMBERS]
    assert phones


def test_named_person_and_role_categorization():
    html = read_fixture("about-team.html")
    page = make_page_context(html=html, page_type=PageType.TEAM)
    candidates = OrganisationExtractor().extract(page)
    people = [c for c in candidates if c.field_path == FieldPath.ORGANISATION_PEOPLE]
    names = {c.normalized_value["name"] for c in people}
    assert "Priya Nair" in names
    assert "Sam Whitfield" in names
    roles = {c.normalized_value["name"]: c.normalized_value["role_category"] for c in people}
    assert roles["Priya Nair"] == "ecommerce"
    assert roles["Sam Whitfield"] == "founder"


def test_internal_it_detected():
    html = read_fixture("careers-technology.html")
    page = make_page_context(html=html, page_type=PageType.CAREERS)
    candidates = OrganisationExtractor().extract(page)
    it_status = [c for c in candidates if c.field_path == FieldPath.ORGANISATION_INTERNAL_IT_STATUS]
    assert any(c.normalized_value == "detected" for c in it_status)


def test_no_internal_it_inference_from_absence():
    html = "<html><body><p>Welcome to our store.</p></body></html>"
    page = make_page_context(html=html, page_type=PageType.HOMEPAGE)
    candidates = OrganisationExtractor().extract(page)
    it_status = [c for c in candidates if c.field_path == FieldPath.ORGANISATION_INTERNAL_IT_STATUS]
    assert all(c.normalized_value != "not_detected" for c in it_status)


def test_recommended_contact_ordering():
    html = read_fixture("about-team.html")
    page = make_page_context(html=html, page_type=PageType.TEAM)
    candidates = OrganisationExtractor().extract(page)
    recommended = [
        c
        for c in candidates
        if c.field_path == FieldPath.ORGANISATION_RECOMMENDED_CONTACT_CANDIDATES
    ]
    assert len(recommended) > 1
    ecommerce_priority = next(
        c.qualifiers["sort_key"]
        for c in recommended
        if c.normalized_value["role_category"] == "ecommerce"
    )
    founder_priority = next(
        c.qualifiers["sort_key"]
        for c in recommended
        if c.normalized_value["role_category"] == "founder"
    )
    assert ecommerce_priority < founder_priority


def test_deterministic_output_and_input_not_mutated():
    html = read_fixture("about-team.html")
    page = make_page_context(html=html, page_type=PageType.TEAM)
    extractor = OrganisationExtractor()
    before = page.model_dump()
    assert extractor.extract(page) == extractor.extract(page)
    assert page.model_dump() == before
