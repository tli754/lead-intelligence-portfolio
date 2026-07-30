"""Regression tests for how `WebsiteDiscoveryService` interacts with the
*real* companies-module processing-status transition graph.

Unlike the rest of `backend/tests/integration/discovery/`, this file does
not use `FakeCompanyDiscoveryGateway` — that fake unconditionally accepts
any status update, so it can never exercise `transitions.py`'s real
validation. Instead this wires the real `CompanyService` and the real
`CompanyServiceDiscoveryGateway` adapter over an in-memory fake
`CompanyRepository`, giving genuine `InvalidStatusTransitionError`
behaviour without needing real MongoDB (following the same "fakes only
at the outermost persistence boundary" approach `modules/imports`
already established).

This reproduces a bug an evaluation caught: running discovery on a
company already past the `discovering` step (e.g. one that previously
completed discovery) used to raise `InvalidStatusTransitionError`
uncaught, since the companies module's transition graph doesn't allow
`discovered -> discovering`. `WebsiteDiscoveryService._advance_processing_status`
now swallows that disagreement instead of crashing the run.
"""

from datetime import UTC, datetime

from app.modules.companies.application.service import CompanyService
from app.modules.companies.domain.enums import ProcessingStatus, WorkflowStatus
from app.modules.companies.domain.models import Company
from app.modules.companies.domain.repository import CompanyPage, CompanyRepository
from app.modules.discovery.application.website_discovery_service import WebsiteDiscoveryService
from app.modules.discovery.domain.enums import DiscoveryStatus
from app.modules.discovery.infrastructure.company_service_gateway import (
    CompanyServiceDiscoveryGateway,
)

from .conftest import FakeDiscoveryRepository, FakeHttpDiscoveryClient


class InMemoryCompanyRepository(CompanyRepository):
    """Enough of `CompanyRepository` to back a real `CompanyService` in
    tests, with no MongoDB involved."""

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


def _real_service(
    repository: InMemoryCompanyRepository, *, discovery_repository: FakeDiscoveryRepository
) -> WebsiteDiscoveryService:
    gateway = CompanyServiceDiscoveryGateway(CompanyService(repository))
    return WebsiteDiscoveryService(
        company_gateway=gateway,
        discovery_repository=discovery_repository,
        http_client=FakeHttpDiscoveryClient(),
    )


class TestRerunOnAlreadyDiscoveredCompany:
    async def test_does_not_raise_and_completes(self) -> None:
        repository = InMemoryCompanyRepository()
        _seed_company(repository, company_id="company-1", status=ProcessingStatus.DISCOVERED)
        service = _real_service(repository, discovery_repository=FakeDiscoveryRepository())

        run = await service.run_discovery("company-1")

        assert run.status in (DiscoveryStatus.COMPLETED, DiscoveryStatus.COMPLETED_WITH_WARNINGS)

    async def test_processing_status_is_left_unchanged(self) -> None:
        repository = InMemoryCompanyRepository()
        _seed_company(repository, company_id="company-1", status=ProcessingStatus.DISCOVERED)
        service = _real_service(repository, discovery_repository=FakeDiscoveryRepository())

        await service.run_discovery("company-1")

        assert repository._companies["company-1"].processing.status == ProcessingStatus.DISCOVERED


class TestRerunOnCompanyPastDiscovery:
    async def test_crawling_company_does_not_raise(self) -> None:
        repository = InMemoryCompanyRepository()
        _seed_company(repository, company_id="company-1", status=ProcessingStatus.CRAWLING)
        service = _real_service(repository, discovery_repository=FakeDiscoveryRepository())

        run = await service.run_discovery("company-1")

        assert run.status in (DiscoveryStatus.COMPLETED, DiscoveryStatus.COMPLETED_WITH_WARNINGS)
        # Discovery cannot move a company backwards from `crawling` to
        # `discovered` either -- also swallowed, not raised.
        assert repository._companies["company-1"].processing.status == ProcessingStatus.CRAWLING


class TestFirstRunFromRestingState:
    async def test_imported_company_still_advances_normally(self) -> None:
        """The fix must not weaken the happy path: a fresh company should
        still visibly move through discovering -> discovered."""
        repository = InMemoryCompanyRepository()
        _seed_company(repository, company_id="company-1", status=ProcessingStatus.IMPORTED)
        service = _real_service(repository, discovery_repository=FakeDiscoveryRepository())

        run = await service.run_discovery("company-1")

        assert run.status in (DiscoveryStatus.COMPLETED, DiscoveryStatus.COMPLETED_WITH_WARNINGS)
        assert repository._companies["company-1"].processing.status == ProcessingStatus.DISCOVERED

    async def test_homepage_failure_from_imported_marks_company_failed(self) -> None:
        repository = InMemoryCompanyRepository()
        _seed_company(repository, company_id="company-1", status=ProcessingStatus.IMPORTED)
        gateway = CompanyServiceDiscoveryGateway(CompanyService(repository))
        service = WebsiteDiscoveryService(
            company_gateway=gateway,
            discovery_repository=FakeDiscoveryRepository(),
            http_client=FakeHttpDiscoveryClient(homepage_success=False),
        )

        run = await service.run_discovery("company-1")

        assert run.status == DiscoveryStatus.FAILED
        assert repository._companies["company-1"].processing.status == ProcessingStatus.FAILED
