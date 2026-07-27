"""The discovery module's only integration point with companies.

Pure abstract contract — no MongoDB or FastAPI imports, and no
dependency on any concrete Company persistence. `ProcessingStatus` is
imported as a pure value type (a `StrEnum` with zero FastAPI/Mongo
imports of its own) — reusing the Company module's existing status
vocabulary rather than inventing a second, redundant one, consistent
with how `modules/imports` already imports a Company domain exception
type across this same module boundary.
"""

from abc import ABC, abstractmethod

from app.modules.companies.domain.enums import ProcessingStatus


class CompanyDiscoveryGateway(ABC):
    """Port the discovery module uses to reach the Company module.

    Never the concrete Mongo repository — only this narrow interface.
    """

    @abstractmethod
    async def get_company_domain(self, company_id: str) -> str:
        """Returns the company's normalized domain.

        Raises `CompanyNotFoundForDiscoveryError` if no such company
        exists.
        """
        ...

    @abstractmethod
    async def update_latest_discovery_run(self, company_id: str, discovery_run_id: str) -> None:
        """Records the given run as the company's latest discovery run."""
        ...

    @abstractmethod
    async def update_processing_status(self, company_id: str, status: ProcessingStatus) -> None:
        """Updates the company's pipeline processing status."""
        ...
