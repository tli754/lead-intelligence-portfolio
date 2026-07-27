"""Business logic for the companies module.

Depends only on the `CompanyRepository` interface (never a concrete
MongoDB class), and never imports FastAPI or Motor directly.
"""

from datetime import UTC, datetime

from app.modules.companies.domain import transitions
from app.modules.companies.domain.enums import ProcessingStatus, WorkflowStatus
from app.modules.companies.domain.exceptions import (
    CompanyNotFoundError,
    DuplicateCompanyError,
)
from app.modules.companies.domain.models import Company, CompanyIdentity
from app.modules.companies.domain.normalization import normalize_domain
from app.modules.companies.domain.repository import CompanyPage, CompanyRepository


class CompanyService:
    """Orchestrates company creation, lookup, and status transitions."""

    def __init__(self, repository: CompanyRepository) -> None:
        self._repository = repository

    async def create_company(
        self,
        *,
        domain: str,
        company_name: str | None = None,
        platform: str | None = None,
        country: str | None = None,
        city: str | None = None,
    ) -> Company:
        normalized_domain = normalize_domain(domain)

        if await self._repository.exists_by_normalized_domain(normalized_domain):
            raise DuplicateCompanyError(normalized_domain)

        now = datetime.now(UTC)
        company = Company(
            domain=domain,
            normalized_domain=normalized_domain,
            identity=CompanyIdentity(
                company_name=company_name,
                platform=platform,
                country=country,
                city=city,
            ),
            created_at=now,
            updated_at=now,
        )
        return await self._repository.create(company)

    async def get_company(self, company_id: str) -> Company:
        company = await self._repository.get_by_id(company_id)
        if company is None:
            raise CompanyNotFoundError(company_id)
        return company

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
        return await self._repository.list_companies(
            processing_status=processing_status,
            workflow_status=workflow_status,
            platform=platform,
            country=country,
            page=page,
            page_size=page_size,
        )

    async def change_processing_status(
        self, company_id: str, status: ProcessingStatus
    ) -> Company:
        company = await self._repository.get_by_id(company_id)
        if company is None:
            raise CompanyNotFoundError(company_id)

        transitions.validate_processing_transition(company.processing.status, status)

        updated = await self._repository.update_processing_status(company_id, status)
        if updated is None:
            raise CompanyNotFoundError(company_id)
        return updated

    async def change_workflow_status(self, company_id: str, status: WorkflowStatus) -> Company:
        company = await self._repository.get_by_id(company_id)
        if company is None:
            raise CompanyNotFoundError(company_id)

        transitions.validate_workflow_transition(company.workflow.manual_status, status)

        updated = await self._repository.update_workflow_status(company_id, status)
        if updated is None:
            raise CompanyNotFoundError(company_id)
        return updated

    async def update_latest_discovery_run(
        self, company_id: str, discovery_run_id: str
    ) -> Company:
        updated = await self._repository.update_latest_discovery_run_id(
            company_id, discovery_run_id
        )
        if updated is None:
            raise CompanyNotFoundError(company_id)
        return updated
