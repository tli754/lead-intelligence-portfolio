"""The real `DiscoveryCrawlGateway` adapter.

Wraps the **`DiscoveryRepository` interface** (never `MongoDiscoveryRepository`
concretely), obtained by importing the already-public `get_discovery_repository`
function from `app.modules.discovery.api.router` — the same mechanical
pattern already used elsewhere for `get_company_service` (import a plain
DI function from another module's `api/router.py`, wire it into this
module's own FastAPI dependency chain).

**Why this wraps a repository, not a service** (contract resolution #2):
`WebsiteDiscoveryService` has no read/query methods (`get_run`,
`list_discovered_urls`) to wrap — only `DiscoveryRepository` (the
persistence interface, one layer lower) has them. This is a deliberate,
documented, one-layer-lower exception to the "wrap a service" ideal,
justified because discovery has no query-capable service to wrap and
`modules/discovery/**` is off-limits to this task. Requires zero changes
to `modules/discovery/**`.

`list_discovered_urls` pages through the wrapped repository's own
paginated method internally (a large internal page size, looped until
exhausted) to return one flat, filtered list — target selection needs the
full candidate set at once. `priorities`/`page_types` filtering happens
client-side after fetching everything (unfiltered) once, since
`DiscoveryRepository.list_discovered_urls` only accepts a single
`priority`/`page_type` value per call, not a list.
"""

from app.modules.crawling.domain.exceptions import DiscoveryRunNotFoundForCrawlError
from app.modules.crawling.domain.gateway import DiscoveryCrawlGateway
from app.modules.discovery.domain.enums import DiscoveryPriority, PageType
from app.modules.discovery.domain.models import DiscoveredUrl, DiscoveryRun
from app.modules.discovery.domain.repository import DiscoveryRepository

_INTERNAL_PAGE_SIZE = 500


class DiscoveryRepositoryCrawlGateway(DiscoveryCrawlGateway):
    def __init__(self, discovery_repository: DiscoveryRepository) -> None:
        self._repository = discovery_repository

    async def get_discovery_run(self, discovery_run_id: str) -> DiscoveryRun:
        run = await self._repository.get_run(discovery_run_id)
        if run is None:
            raise DiscoveryRunNotFoundForCrawlError(discovery_run_id)
        return run

    async def list_discovered_urls(
        self,
        discovery_run_id: str,
        *,
        priorities: list[DiscoveryPriority] | None = None,
        page_types: list[PageType] | None = None,
        include_excluded: bool = False,
    ) -> list[DiscoveredUrl]:
        all_urls: list[DiscoveredUrl] = []
        page_number = 1
        while True:
            result = await self._repository.list_discovered_urls(
                discovery_run_id,
                include_excluded=include_excluded,
                page=page_number,
                page_size=_INTERNAL_PAGE_SIZE,
            )
            all_urls.extend(result.items)
            if not result.items or len(all_urls) >= result.total:
                break
            page_number += 1

        if priorities is not None:
            allowed_priorities = set(priorities)
            all_urls = [url for url in all_urls if url.priority in allowed_priorities]
        if page_types is not None:
            allowed_page_types = set(page_types)
            all_urls = [url for url in all_urls if url.page_type in allowed_page_types]

        return all_urls
