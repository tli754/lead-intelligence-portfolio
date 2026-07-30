"""Tests for `CompanyServiceCrawlGateway` — the real `CompanyCrawlGateway`
adapter over `CompanyService`.

Wires the *real* `CompanyService` (and, through it, the real
`transitions.py` validation) over an in-memory fake `CompanyRepository` —
no MongoDB needed, but a genuine `CompanyService` instance rather than a
gateway-level fake, so this actually exercises the adapter's own
translation logic instead of a fake that already speaks the crawling
module's vocabulary.

Regression coverage for a gap an evaluation found: `update_processing_status`
used to let `CompanyService`'s own `CompanyNotFoundError` propagate
unchanged, instead of translating it into the crawling module's
`CompanyNotFoundForCrawlError` — meaning the router's `CompanyNotFoundForCrawlError`
-> 404 handling was dead code against the real adapter (it only worked
against gateway-level fakes that raise the crawling-specific type
directly).
"""

from datetime import UTC, datetime

import pytest

from app.modules.companies.application.service import CompanyService
from app.modules.companies.domain.enums import ProcessingStatus, WorkflowStatus
from app.modules.companies.domain.models import Company
from app.modules.companies.domain.repository import CompanyPage, CompanyRepository
from app.modules.crawling.domain.exceptions import CompanyNotFoundForCrawlError
from app.modules.crawling.infrastructure.company_service_gateway import (
    CompanyServiceCrawlGateway,
)


class InMemoryCompanyRepository(CompanyRepository):
    def __init__(self) -> None:
        self._companies: dict[str, Company] = {}

    async def create(self, company: Company) -> Company:
        self._companies[company.company_id] = company
        return company

    async def update(self, company_id: str, company: Company) -> Company | None:
        if company_id not in self._companies:
            return None
        self._companies[company_id] = company
        return company

    async def get_by_id(self, company_id: str) -> Company | None:
        return self._companies.get(company_id)

    async def get_by_normalized_domain(self, normalized_domain: str) -> Company | None:
        for company in self._companies.values():
            if company.normalized_domain == normalized_domain:
                return company
        return None

    async def exists_by_normalized_domain(self, normalized_domain: str) -> bool:
        return await self.get_by_normalized_domain(normalized_domain) is not None

    async def list_companies(
        self,
        *,
        processing_status: ProcessingStatus | None = None,
        workflow_status: WorkflowStatus | None = None,
        platform: str | None = None,
        country: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> CompanyPage:
        items = list(self._companies.values())
        return CompanyPage(items=items, total=len(items))

    async def update_processing_status(
        self, company_id: str, status: ProcessingStatus
    ) -> Company | None:
        company = self._companies.get(company_id)
        if company is None:
            return None
        company.processing.status = status
        return company

    async def update_workflow_status(
        self, company_id: str, status: WorkflowStatus
    ) -> Company | None:
        company = self._companies.get(company_id)
        if company is None:
            return None
        company.workflow.manual_status = status
        return company

    async def update_latest_discovery_run_id(
        self, company_id: str, discovery_run_id: str
    ) -> Company | None:
        company = self._companies.get(company_id)
        if company is None:
            return None
        company.processing.latest_discovery_run_id = discovery_run_id
        return company


def _seed_company(
    repository: InMemoryCompanyRepository, *, company_id: str, status: ProcessingStatus
) -> None:
    now = datetime.now(UTC)
    company = Company(
        company_id=company_id,
        domain="example.com",
        normalized_domain="example.com",
        created_at=now,
        updated_at=now,
    )
    company.processing.status = status
    repository._companies[company_id] = company


class TestUpdateProcessingStatus:
    async def test_known_company_advances_status(self) -> None:
        repository = InMemoryCompanyRepository()
        _seed_company(repository, company_id="company-1", status=ProcessingStatus.DISCOVERED)
        gateway = CompanyServiceCrawlGateway(CompanyService(repository))

        await gateway.update_processing_status("company-1", ProcessingStatus.CRAWLING)

        assert repository._companies["company-1"].processing.status == ProcessingStatus.CRAWLING

    async def test_unknown_company_raises_crawl_specific_error(self) -> None:
        repository = InMemoryCompanyRepository()
        gateway = CompanyServiceCrawlGateway(CompanyService(repository))

        with pytest.raises(CompanyNotFoundForCrawlError) as excinfo:
            await gateway.update_processing_status("no-such-company", ProcessingStatus.CRAWLING)

        assert excinfo.value.company_id == "no-such-company"


class TestUpdateLatestCrawlRun:
    async def test_is_a_documented_no_op(self) -> None:
        """Per contract resolution #1: `CompanyService.update_latest_crawl_run`
        doesn't exist yet, so this must not raise even for an unknown company."""
        repository = InMemoryCompanyRepository()
        gateway = CompanyServiceCrawlGateway(CompanyService(repository))

        await gateway.update_latest_crawl_run("no-such-company", "crawl_run_1")
