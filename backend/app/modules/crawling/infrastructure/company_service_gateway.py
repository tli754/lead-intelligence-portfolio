"""The real `CompanyCrawlGateway` adapter, wrapping the Company module's
own public application service.

Never imports `MongoCompanyRepository` or Motor — only `CompanyService`
(`app.modules.companies.application.service`), obtained via dependency
injection in `api/router.py` (which reuses
`app.modules.companies.api.router.get_company_service`, the Company
module's own DI wiring function) — the same reuse pattern
`modules/discovery/infrastructure/company_service_gateway.py` and
`modules/imports/infrastructure/company_service_gateway.py` already
established.
"""

import logging

from app.modules.companies.application.service import CompanyService
from app.modules.companies.domain.enums import ProcessingStatus
from app.modules.companies.domain.exceptions import CompanyNotFoundError
from app.modules.crawling.domain.exceptions import CompanyNotFoundForCrawlError
from app.modules.crawling.domain.gateway import CompanyCrawlGateway

logger = logging.getLogger(__name__)


class CompanyServiceCrawlGateway(CompanyCrawlGateway):
    """Adapts `CompanyService` to the crawling module's narrow gateway port."""

    def __init__(self, company_service: CompanyService) -> None:
        self._company_service = company_service

    async def update_processing_status(self, company_id: str, status: ProcessingStatus) -> None:
        try:
            await self._company_service.change_processing_status(company_id, status)
        except CompanyNotFoundError as error:
            raise CompanyNotFoundForCrawlError(company_id) from error

    async def update_latest_crawl_run(self, company_id: str, crawl_run_id: str) -> None:
        """**Documented, logged no-op** (contract resolution #1):
        `CompanyRepository`/`CompanyService` (in `modules/companies`,
        off-limits to this task) has `update_latest_discovery_run` (a
        Task-005 follow-up) but no equivalent `update_latest_crawl_run`
        yet, even though `CompanyProcessing.latest_crawl_run_id` already
        exists as a field and is already persisted by `model_dump()` — it
        just has no dedicated setter method or MongoDB update path.

        **Required follow-up** (report, do not build — off-limits path):
        add `CompanyRepository.update_latest_crawl_run_id` (interface) +
        `MongoCompanyRepository.update_latest_crawl_run_id`
        (implementation) + `CompanyService.update_latest_crawl_run`,
        mirroring `update_latest_discovery_run` exactly, then swap this
        no-op for a real call.
        """
        logger.info(
            "update_latest_crawl_run is a no-op pending a CompanyService follow-up "
            "(company_id=%s, crawl_run_id=%s)",
            company_id,
            crawl_run_id,
        )
