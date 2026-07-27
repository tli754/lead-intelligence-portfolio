"""Repository interface for the discovery module.

Pure abstract contract — no MongoDB or FastAPI imports. Implementations
live in `infrastructure/` (e.g. `MongoDiscoveryRepository`).
"""

from abc import ABC, abstractmethod
from typing import NamedTuple

from app.modules.discovery.domain.enums import DiscoverySource, PageType
from app.modules.discovery.domain.models import DiscoveredUrl, DiscoveryRun


class DiscoveredUrlPage(NamedTuple):
    """A page of `list_discovered_urls` results, plus the total matching count."""

    items: list[DiscoveredUrl]
    total: int


class DiscoveryRepository(ABC):
    """Persistence contract for `DiscoveryRun`/`DiscoveredUrl` records."""

    @abstractmethod
    async def create_run(self, run: DiscoveryRun) -> DiscoveryRun: ...

    @abstractmethod
    async def update_run(self, run: DiscoveryRun) -> DiscoveryRun | None: ...

    @abstractmethod
    async def save_discovered_urls(self, urls: list[DiscoveredUrl]) -> list[DiscoveredUrl]: ...

    @abstractmethod
    async def get_run(self, discovery_run_id: str) -> DiscoveryRun | None: ...

    @abstractmethod
    async def get_latest_run_for_company(self, company_id: str) -> DiscoveryRun | None:
        """The most recently *started* run for a company.

        Not in the task's literal section-11 method list, but added as a
        deliberate, documented extension: the task also requires
        `GET /api/companies/{company_id}/discovery-runs/latest`, and
        nothing in the specified method set (`create_run`, `update_run`,
        `save_discovered_urls`, `get_run`, `list_discovered_urls`,
        `find_existing_url`) can serve that endpoint.
        """
        ...

    @abstractmethod
    async def list_discovered_urls(
        self,
        discovery_run_id: str,
        *,
        priority: str | None = None,
        page_type: PageType | None = None,
        source: DiscoverySource | None = None,
        include_excluded: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> DiscoveredUrlPage: ...

    @abstractmethod
    async def find_existing_url(
        self, discovery_run_id: str, normalized_url: str
    ) -> DiscoveredUrl | None:
        """Used for duplicate-safe retry — checked before insert so
        re-running discovery for the same company doesn't create
        duplicate rows for URLs already seen in the same run."""
        ...
