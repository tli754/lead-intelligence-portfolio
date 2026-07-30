"""The real `CompanyImportGateway` adapter, wrapping the Company module's
own public application service.

Never imports `MongoCompanyRepository` or Motor — only `CompanyService`
(`app.modules.companies.application.service`), obtained via dependency
injection in `api/router.py` (which reuses
`app.modules.companies.api.router.get_company_service`, the Company
module's own DI wiring function). This file is the *only* place the
imports module touches anything from `app.modules.companies`.
"""

from app.modules.companies.application.service import CompanyService
from app.modules.companies.domain.exceptions import DuplicateCompanyError
from app.modules.imports.domain.gateway import CompanyAlreadyExistsError, CompanyImportGateway


class CompanyServiceImportGateway(CompanyImportGateway):
    """Adapts `CompanyService` to the imports module's narrow gateway port."""

    def __init__(self, company_service: CompanyService) -> None:
        self._company_service = company_service

    async def exists_by_domain(self, normalized_domain: str) -> bool | None:
        """Always returns `None` ("unknown").

        `CompanyService` has no public, non-mutating way to look up a
        company by domain today (only `create_company`, which mutates,
        internally checks this). Returning `None` here is the honest
        answer rather than guessing — see this module's execution-plan
        doc for the "required follow-up outside allowed paths" this
        implies for `CompanyService`. Import-time safety does not depend
        on this: `create_imported_company` below is race-free regardless.
        """
        return None

    async def create_imported_company(
        self,
        *,
        normalized_domain: str,
        platform: str | None,
        country: str | None,
        city: str | None,
    ) -> None:
        try:
            await self._company_service.create_company(
                domain=normalized_domain,
                platform=platform,
                country=country,
                city=city,
            )
        except DuplicateCompanyError as error:
            raise CompanyAlreadyExistsError(normalized_domain) from error
