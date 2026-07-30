"""The crawling module's integration points with other modules.

Pure abstract contracts — no MongoDB or FastAPI imports. `ProcessingStatus`,
`DiscoveryRun`, `DiscoveredUrl`, `PageType`, and `DiscoveryPriority` are
imported as pure value types (zero FastAPI/Mongo imports of their own),
reusing each module's existing vocabulary rather than inventing a second,
redundant one — the same precedent `modules/discovery/domain/gateway.py`
already set for `ProcessingStatus`.

All three ports live in this one file, matching how `modules/discovery`
keeps its one gateway in one file (contract T22).
"""

from abc import ABC, abstractmethod

from app.modules.companies.domain.enums import ProcessingStatus
from app.modules.crawling.domain.robots_policy import RobotsPolicyEvaluation
from app.modules.discovery.domain.enums import DiscoveryPriority, PageType
from app.modules.discovery.domain.models import DiscoveredUrl, DiscoveryRun


class CompanyCrawlGateway(ABC):
    """Port the crawling module uses to reach the Company module.

    Never the concrete Mongo repository — only this narrow interface.
    """

    @abstractmethod
    async def update_latest_crawl_run(self, company_id: str, crawl_run_id: str) -> None:
        """Records the given run as the company's latest crawl run.

        **Known gap** (contract resolution #1): the real adapter
        (`infrastructure/company_service_gateway.py`) implements this as a
        documented, logged no-op — `CompanyService` has no
        `update_latest_crawl_run` method yet (mirrors
        `update_latest_discovery_run`, which does exist). See that
        adapter's own docstring for the required follow-up.
        """
        ...

    @abstractmethod
    async def update_processing_status(self, company_id: str, status: ProcessingStatus) -> None:
        """Updates the company's pipeline processing status. Fully real
        today — `CompanyService.change_processing_status` already exists."""
        ...


class DiscoveryCrawlGateway(ABC):
    """Port the crawling module uses to reach the Discovery module.

    Deliberately **not** wrapping `WebsiteDiscoveryService` (it has no
    read/query methods) — wraps the lower-level `DiscoveryRepository`
    interface instead, per contract resolution #2. Exactly two methods;
    `get_robots_policy` is deliberately excluded (robots policy is not
    discovery data at all — see `RobotsPolicyGateway` below and contract
    resolution #3).
    """

    @abstractmethod
    async def get_discovery_run(self, discovery_run_id: str) -> DiscoveryRun:
        """Raises `DiscoveryRunNotFoundForCrawlError` if no such run exists."""
        ...

    @abstractmethod
    async def list_discovered_urls(
        self,
        discovery_run_id: str,
        *,
        priorities: list[DiscoveryPriority] | None = None,
        page_types: list[PageType] | None = None,
        include_excluded: bool = False,
    ) -> list[DiscoveredUrl]:
        """Returns the full, flat, filtered candidate set for one
        discovery run — target selection needs the whole set at once."""
        ...


class RobotsPolicyGateway(ABC):
    """A port owned entirely by this module (contract resolution #3) —
    robots policy is not discovery data; discovery only ever parses
    `robots.txt` structure, never evaluates it against a URL. The real
    adapter (`infrastructure/http_robots_policy_gateway.py`) fetches
    `robots.txt` itself and evaluates it with `domain/robots_policy.py`.
    """

    @abstractmethod
    async def get_policy(
        self, company_id: str, url: str, user_agent: str
    ) -> RobotsPolicyEvaluation:
        """Never raises for a missing/unreachable `robots.txt` — resolves
        to `outcome="unknown"` instead (see the adapter's own docstring)."""
        ...
