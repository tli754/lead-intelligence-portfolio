"""The imports module's only integration point with companies.

Pure abstract contract — no MongoDB or FastAPI imports, and critically no
dependency on any concrete Company persistence. Implementations
(`infrastructure.company_service_gateway.CompanyServiceImportGateway` for
the real Company module, `FakeCompanyImportGateway` in tests) live
outside `domain/`.
"""

from abc import ABC, abstractmethod


class CompanyAlreadyExistsError(Exception):
    """Raised by `create_imported_company` when the domain already exists."""

    def __init__(self, normalized_domain: str) -> None:
        super().__init__(f"a company with normalized_domain={normalized_domain!r} already exists")
        self.normalized_domain = normalized_domain


class CompanyImportGateway(ABC):
    """Port the imports module uses to reach the Company module.

    Never the concrete Mongo repository — only this narrow interface.
    """

    @abstractmethod
    async def exists_by_domain(self, normalized_domain: str) -> bool | None:
        """Returns whether a company with this domain already exists.

        `None` means the gateway cannot answer without performing a
        write (see the real adapter's docstring) — callers should treat
        that as "unknown", not "false".
        """
        ...

    @abstractmethod
    async def create_imported_company(
        self,
        *,
        normalized_domain: str,
        platform: str | None,
        country: str | None,
        city: str | None,
    ) -> None:
        """Creates a company from an imported row.

        Raises `CompanyAlreadyExistsError` if the domain already exists —
        callers treat that as "skipped", not a failure. Any other
        exception is a genuine per-row failure.
        """
        ...
