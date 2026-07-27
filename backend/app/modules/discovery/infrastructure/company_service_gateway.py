"""The real `CompanyDiscoveryGateway` adapter, wrapping the Company
module's own public application service.

Never imports `MongoCompanyRepository` or Motor — only `CompanyService`
(`app.modules.companies.application.service`), obtained via dependency
injection in `api/router.py` (which reuses
`app.modules.companies.api.router.get_company_service`, the Company
module's own DI wiring function — the same reuse pattern
`modules/imports/infrastructure/company_service_gateway.py` already
established). This file is the only place the discovery module touches
anything from `app.modules.companies` besides the pure `ProcessingStatus`
enum already imported in `domain/gateway.py`.
"""

from app.modules.companies.application.service import CompanyService
from app.modules.companies.domain.enums import ProcessingStatus
from app.modules.companies.domain.exceptions import CompanyNotFoundError
from app.modules.discovery.domain.exceptions import CompanyNotFoundForDiscoveryError
from app.modules.discovery.domain.gateway import CompanyDiscoveryGateway


class CompanyServiceDiscoveryGateway(CompanyDiscoveryGateway):
    """Adapts `CompanyService` to the discovery module's narrow gateway port."""

    def __init__(self, company_service: CompanyService) -> None:
        self._company_service = company_service

    async def get_company_domain(self, company_id: str) -> str:
        try:
            company = await self._company_service.get_company(company_id)
        except CompanyNotFoundError as error:
            raise CompanyNotFoundForDiscoveryError(company_id) from error
        return company.normalized_domain

    async def update_processing_status(self, company_id: str, status: ProcessingStatus) -> None:
        await self._company_service.change_processing_status(company_id, status)

    async def update_latest_discovery_run(self, company_id: str, discovery_run_id: str) -> None:
        await self._company_service.update_latest_discovery_run(company_id, discovery_run_id)
