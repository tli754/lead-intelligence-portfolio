"""Repository interface for the companies module.

Pure abstract contract — no MongoDB or FastAPI imports. Implementations
live in `infrastructure/` (e.g. `MongoCompanyRepository`), so the
`application` layer can depend on this interface without knowing how or
where `Company` records are actually persisted.
"""

from abc import ABC, abstractmethod
from typing import NamedTuple

from app.modules.companies.domain.enums import ProcessingStatus, WorkflowStatus
from app.modules.companies.domain.models import Company


class CompanyPage(NamedTuple):
    """A page of `list_companies` results, plus the total matching count."""

    items: list[Company]
    total: int


class CompanyRepository(ABC):
    """Persistence contract for `Company` records."""

    @abstractmethod
    async def create(self, company: Company) -> Company: ...

    @abstractmethod
    async def update(self, company_id: str, company: Company) -> Company | None: ...

    @abstractmethod
    async def get_by_id(self, company_id: str) -> Company | None: ...

    @abstractmethod
    async def get_by_normalized_domain(self, normalized_domain: str) -> Company | None: ...

    @abstractmethod
    async def exists_by_normalized_domain(self, normalized_domain: str) -> bool: ...

    @abstractmethod
    async def list_companies(
        self,
        *,
        processing_status: ProcessingStatus | None = None,
        workflow_status: WorkflowStatus | None = None,
        platform: str | None = None,
        country: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> CompanyPage: ...

    @abstractmethod
    async def update_processing_status(
        self, company_id: str, status: ProcessingStatus
    ) -> Company | None: ...

    @abstractmethod
    async def update_workflow_status(
        self, company_id: str, status: WorkflowStatus
    ) -> Company | None: ...

    @abstractmethod
    async def update_latest_discovery_run_id(
        self, company_id: str, discovery_run_id: str
    ) -> Company | None: ...
