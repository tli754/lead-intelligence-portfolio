"""Unit tests for CompanyService, using an in-memory fake repository.

No MongoDB involved — verifies the service's business rules
(normalization, duplicate rejection, not-found handling) in isolation.
"""

import pytest

from app.modules.companies.application.service import CompanyService
from app.modules.companies.domain.enums import ProcessingStatus, WorkflowStatus
from app.modules.companies.domain.exceptions import (
    CompanyNotFoundError,
    DuplicateCompanyError,
)
from app.modules.companies.domain.models import Company
from app.modules.companies.domain.repository import CompanyRepository


class FakeCompanyRepository(CompanyRepository):
    def __init__(self) -> None:
        self._by_id: dict[str, Company] = {}

    async def create(self, company: Company) -> Company:
        self._by_id[company.company_id] = company
        return company

    async def update(self, company_id: str, company: Company) -> Company | None:
        if company_id not in self._by_id:
            return None
        self._by_id[company_id] = company
        return company

    async def get_by_id(self, company_id: str) -> Company | None:
        return self._by_id.get(company_id)

    async def get_by_domain(self, normalized_domain: str) -> Company | None:
        for company in self._by_id.values():
            if company.normalized_domain == normalized_domain:
                return company
        return None

    async def exists(self, normalized_domain: str) -> bool:
        return await self.get_by_domain(normalized_domain) is not None

    async def list(
        self,
        *,
        processing_status: ProcessingStatus | None = None,
        workflow_status: WorkflowStatus | None = None,
        platform: str | None = None,
        country: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Company]:
        companies = list(self._by_id.values())
        if processing_status is not None:
            companies = [c for c in companies if c.processing.status == processing_status]
        if workflow_status is not None:
            companies = [c for c in companies if c.workflow.manual_status == workflow_status]
        if platform is not None:
            companies = [c for c in companies if c.identity.platform == platform]
        if country is not None:
            companies = [c for c in companies if c.identity.country == country]
        return companies[skip : skip + limit]

    async def update_processing_status(
        self, company_id: str, status: ProcessingStatus
    ) -> Company | None:
        company = self._by_id.get(company_id)
        if company is None:
            return None
        updated = company.model_copy(
            update={"processing": company.processing.model_copy(update={"status": status})}
        )
        self._by_id[company_id] = updated
        return updated

    async def update_workflow_status(
        self, company_id: str, status: WorkflowStatus
    ) -> Company | None:
        company = self._by_id.get(company_id)
        if company is None:
            return None
        updated = company.model_copy(
            update={"workflow": company.workflow.model_copy(update={"manual_status": status})}
        )
        self._by_id[company_id] = updated
        return updated


@pytest.fixture
def service() -> CompanyService:
    return CompanyService(FakeCompanyRepository())


class TestCreateCompany:
    async def test_creates_company_with_normalized_domain(self, service: CompanyService) -> None:
        company = await service.create_company(
            domain="https://Example.com/", company_name="Example"
        )
        assert company.normalized_domain == "example.com"
        assert company.domain == "https://Example.com/"
        assert company.identity.company_name == "Example"
        assert company.processing.status == ProcessingStatus.IMPORTED

    async def test_rejects_duplicate_domain(self, service: CompanyService) -> None:
        await service.create_company(domain="example.com")
        with pytest.raises(DuplicateCompanyError):
            await service.create_company(domain="www.example.com")


class TestGetCompany:
    async def test_raises_when_missing(self, service: CompanyService) -> None:
        with pytest.raises(CompanyNotFoundError):
            await service.get_company("missing")

    async def test_returns_created_company(self, service: CompanyService) -> None:
        created = await service.create_company(domain="example.com")
        fetched = await service.get_company(created.company_id)
        assert fetched.company_id == created.company_id


class TestListCompanies:
    async def test_filters_by_platform(self, service: CompanyService) -> None:
        await service.create_company(domain="shopify-store.com", platform="shopify")
        await service.create_company(domain="other-store.com", platform="woocommerce")

        results = await service.list_companies(platform="shopify")
        assert [c.normalized_domain for c in results] == ["shopify-store.com"]


class TestChangeProcessingStatus:
    async def test_updates_status(self, service: CompanyService) -> None:
        created = await service.create_company(domain="example.com")
        updated = await service.change_processing_status(
            created.company_id, ProcessingStatus.CRAWLING
        )
        assert updated.processing.status == ProcessingStatus.CRAWLING

    async def test_raises_when_missing(self, service: CompanyService) -> None:
        with pytest.raises(CompanyNotFoundError):
            await service.change_processing_status("missing", ProcessingStatus.CRAWLING)


class TestChangeWorkflowStatus:
    async def test_updates_status(self, service: CompanyService) -> None:
        created = await service.create_company(domain="example.com")
        updated = await service.change_workflow_status(
            created.company_id, WorkflowStatus.SHORTLISTED
        )
        assert updated.workflow.manual_status == WorkflowStatus.SHORTLISTED

    async def test_raises_when_missing(self, service: CompanyService) -> None:
        with pytest.raises(CompanyNotFoundError):
            await service.change_workflow_status("missing", WorkflowStatus.SHORTLISTED)
