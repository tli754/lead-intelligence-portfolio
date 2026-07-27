"""Unit tests for CompanyImportService, using a fake in-memory repository.

No MongoDB involved here — repository behaviour is covered separately in
test_repository.py.
"""

from app.domains.companies.models import Company
from app.domains.companies.service import CompanyImportService


class FakeCompanyRepository:
    """In-memory stand-in for CompanyRepository."""

    def __init__(self, existing_domains: set[str] | None = None) -> None:
        self.existing_domains = existing_domains or set()
        self.inserted: list[Company] = []

    async def get_existing_domains(self, domains: list[str]) -> set[str]:
        return {domain for domain in domains if domain in self.existing_domains}

    async def insert_many(self, companies: list[Company]) -> list[Company]:
        self.inserted.extend(companies)
        return companies


async def test_in_paste_duplicate_only_creates_one_company() -> None:
    """AC-04."""
    repository = FakeCompanyRepository()
    service = CompanyImportService(repository)

    response = await service.import_companies("example.com\nEXAMPLE.com")

    assert response.created_count == 1
    assert response.skipped_duplicate_in_paste == ["example.com"]
    assert [company.domain for company in response.created] == ["example.com"]


async def test_existing_in_db_domain_is_skipped_not_recreated() -> None:
    """AC-05."""
    repository = FakeCompanyRepository(existing_domains={"example.com"})
    service = CompanyImportService(repository)

    response = await service.import_companies("example.com\nother.com")

    assert response.created_count == 1
    assert [company.domain for company in response.created] == ["other.com"]
    assert response.skipped_existing_in_db == ["example.com"]
    assert repository.inserted == response.created


async def test_domain_list_source_tag() -> None:
    repository = FakeCompanyRepository()
    service = CompanyImportService(repository)

    response = await service.import_companies("example.com")

    assert response.detected_format == "domain_list"
    assert response.created[0].source == "paste_domain_list"


async def test_storeleads_html_source_tag() -> None:
    repository = FakeCompanyRepository()
    service = CompanyImportService(repository)
    html = (
        '<vaadin-grid-cell-content slot="x">'
        '<div class="default">example.com</div>'
        '<a class="tdu pc cpoint" href="https://example.com">https://example.com</a>'
    )

    response = await service.import_companies(html)

    assert response.detected_format == "storeleads_html"
    assert response.created[0].source == "paste_storeleads_html"
    assert response.created[0].url == "https://example.com"


async def test_response_counts_are_consistent() -> None:
    repository = FakeCompanyRepository(existing_domains={"already.com"})
    service = CompanyImportService(repository)
    raw_text = "new.com\nnew.com\nalready.com\nnot a domain!!"

    response = await service.import_companies(raw_text)

    assert response.total_rows_detected == 4
    assert response.created_count == 1
    assert [company.domain for company in response.created] == ["new.com"]
    assert response.skipped_duplicate_in_paste == ["new.com"]
    assert response.skipped_existing_in_db == ["already.com"]
    assert len(response.skipped_invalid) == 1
    assert response.skipped_invalid[0].raw_value == "not a domain!!"
