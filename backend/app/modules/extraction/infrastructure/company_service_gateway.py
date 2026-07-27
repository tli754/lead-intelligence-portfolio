"""The real `CompanyExtractionGateway` adapter, wrapping the Company
module's own public application service.

Never imports `MongoCompanyRepository`/Motor — only `CompanyService`
(`app.modules.companies.application.service`), obtained via dependency
injection in `api/router.py` (reusing
`app.modules.companies.api.router.get_company_service`) — the same reuse
pattern `CompanyServiceCrawlGateway`/`CompanyServiceImportGateway` already
established.
"""

import logging

from app.modules.companies.application.service import CompanyService
from app.modules.companies.domain.enums import ProcessingStatus
from app.modules.companies.domain.exceptions import CompanyNotFoundError
from app.modules.extraction.domain.company_projection import CompanyFactsProjection
from app.modules.extraction.domain.exceptions import CompanyNotFoundForExtractionError
from app.modules.extraction.domain.gateway import CompanyExtractionGateway

logger = logging.getLogger(__name__)


class CompanyServiceExtractionGateway(CompanyExtractionGateway):
    """Adapts `CompanyService` to the extraction module's narrow gateway port."""

    def __init__(self, company_service: CompanyService) -> None:
        self._company_service = company_service

    async def update_processing_status(self, company_id: str, status: ProcessingStatus) -> None:
        try:
            await self._company_service.change_processing_status(company_id, status)
        except CompanyNotFoundError as error:
            raise CompanyNotFoundForExtractionError(company_id) from error

    async def update_latest_extraction_run(self, company_id: str, extraction_run_id: str) -> None:
        """**Documented, logged no-op** (contract resolution #2):
        `CompanyRepository`/`CompanyService` (in `modules/companies`,
        off-limits to this task) has `update_latest_discovery_run` but no
        equivalent `update_latest_extraction_run` yet, even though
        `CompanyProcessing.latest_extraction_run_id` already exists as a
        field and is already persisted by `model_dump()` — it just has no
        dedicated setter method or MongoDB update path.

        **Required follow-up** (report, do not build — off-limits path):
        add `CompanyRepository.update_latest_extraction_run_id` (interface)
        + `MongoCompanyRepository.update_latest_extraction_run_id`
        (implementation) + `CompanyService.update_latest_extraction_run`,
        mirroring `update_latest_discovery_run` exactly, then swap this
        no-op for a real call.
        """
        logger.info(
            "update_latest_extraction_run is a no-op pending a CompanyService follow-up "
            "(company_id=%s, extraction_run_id=%s)",
            company_id,
            extraction_run_id,
        )

    async def project_latest_facts(
        self, company_id: str, projection: CompanyFactsProjection
    ) -> None:
        """**Documented, logged no-op** (contract resolution #3) — a
        *larger* gap than `update_latest_extraction_run`: no field exists
        yet on `Company`/`CompanyProcessing` at all (not `latest_facts`,
        not any placeholder) to write into — closing this gap requires a
        new domain field, a new `CompanyRepository` method, a MongoDB
        migration/backfill consideration, and a schema-shape decision
        (flattened by field-path vs. nested by domain-group), none of
        which this task can do (`modules/companies/**` is off-limits).

        **Required follow-up** (report, do not build — larger scope than
        a mirrored setter): design and add a `latest_facts`-shaped field
        to `Company`/`CompanyProcessing`, a `CompanyRepository.update_latest_facts`
        method, and `CompanyService.update_latest_facts`, then switch this
        method from a no-op to a real call. The projection value itself is
        still fully constructed by `modules/extraction/domain/company_projection.py`
        and passed here — only the durable write into the Company module
        is missing; the same data remains fully available via this
        module's own `GET /api/companies/{company_id}/facts`.
        """
        field_count = sum(
            len(getattr(projection, group))
            for group in (
                "identity",
                "business",
                "catalogue",
                "operations",
                "technology",
                "organisation",
                "growth",
            )
        )
        logger.info(
            "project_latest_facts is a no-op pending a larger CompanyService follow-up "
            "(company_id=%s, projected_field_count=%s)",
            company_id,
            field_count,
        )
