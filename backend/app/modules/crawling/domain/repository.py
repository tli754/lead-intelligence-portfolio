"""Repository interface for the crawling module.

Pure abstract contract — no MongoDB or FastAPI imports. Implementations
live in `infrastructure/` (e.g. `MongoCrawlRepository`).
"""

from abc import ABC, abstractmethod
from typing import NamedTuple

from app.modules.crawling.domain.enums import FetchMode, PageFetchStatus
from app.modules.crawling.domain.models import CrawledPage, CrawlRun, CrawlTarget
from app.modules.discovery.domain.enums import DiscoveryPriority, PageType


class CrawlRunPage(NamedTuple):
    items: list[CrawlRun]
    total: int


class CrawlTargetPage(NamedTuple):
    """A page of `list_targets_by_run` results, plus the total matching count."""

    items: list[CrawlTarget]
    total: int


class CrawledPagePage(NamedTuple):
    """A page of `list_pages_by_run` results, plus the total matching count."""

    items: list[CrawledPage]
    total: int


class CrawlRepository(ABC):
    """Persistence contract for `CrawlRun`/`CrawlTarget`/`CrawledPage` records.

    Beyond the task brief's literal method list, this adds:
    `find_active_run` (needed to serve section 16's "duplicate active run
    requests return the existing run or a typed conflict" — nothing in
    the brief's literal method set can otherwise answer that) and
    `list_targets_by_run`/`list_runs_by_company` paginated variants
    (needed to serve the `GET .../targets` list endpoint and general
    run-listing, matching `DiscoveredUrlPage`'s existing precedent in
    `modules/discovery`).
    """

    # --- Runs ---------------------------------------------------------

    @abstractmethod
    async def create_run(self, run: CrawlRun) -> CrawlRun: ...

    @abstractmethod
    async def update_run(self, run: CrawlRun) -> CrawlRun | None:
        """Uses an optimistic-concurrency filter on `document_version` —
        a stale caller's write is rejected (returns `None`) rather than
        silently overwriting a newer state."""
        ...

    @abstractmethod
    async def get_run(self, crawl_run_id: str) -> CrawlRun | None: ...

    @abstractmethod
    async def list_runs_by_company(
        self, company_id: str, *, page: int = 1, page_size: int = 20
    ) -> CrawlRunPage: ...

    @abstractmethod
    async def find_active_run(self, company_id: str, idempotency_key: str) -> CrawlRun | None:
        """Returns a `queued`/`running` run matching `idempotency_key`, if
        one exists — used to serve section 16's duplicate-active-run
        conflict check."""
        ...

    @abstractmethod
    async def mark_run_cancelled(self, crawl_run_id: str) -> CrawlRun | None: ...

    # --- Targets --------------------------------------------------------

    @abstractmethod
    async def save_target(self, target: CrawlTarget) -> CrawlTarget:
        """Upserts by `(crawl_run_id, normalized_url)` — exactly one row
        per pair, per section 16."""
        ...

    @abstractmethod
    async def update_target(self, target: CrawlTarget) -> CrawlTarget | None:
        """Uses an optimistic-concurrency filter on `document_version`."""
        ...

    @abstractmethod
    async def find_target_by_url(
        self, crawl_run_id: str, normalized_url: str
    ) -> CrawlTarget | None: ...

    @abstractmethod
    async def list_targets_by_run(
        self,
        crawl_run_id: str,
        *,
        status: PageFetchStatus | None = None,
        page_type: PageType | None = None,
        priority: DiscoveryPriority | None = None,
        fetch_mode: FetchMode | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> CrawlTargetPage: ...

    # --- Pages ------------------------------------------------------------

    @abstractmethod
    async def save_page(self, page: CrawledPage) -> CrawledPage:
        """Upserts by `(crawl_run_id, normalized_url)` — retrying a failed
        page never duplicates its page record (section 16)."""
        ...

    @abstractmethod
    async def get_page(self, page_id: str) -> CrawledPage | None: ...

    @abstractmethod
    async def list_pages_by_run(
        self,
        crawl_run_id: str,
        *,
        status: PageFetchStatus | None = None,
        page_type: PageType | None = None,
        priority: DiscoveryPriority | None = None,
        fetch_mode: FetchMode | None = None,
        browser_required: bool | None = None,
        include_failed: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> CrawledPagePage: ...

    @abstractmethod
    async def get_latest_page_by_normalized_url(
        self, company_id: str, normalized_url: str
    ) -> CrawledPage | None:
        """Used for conditional-fetch/change-detection — the previous
        page record (if any) for the same normalized URL, regardless of
        which run produced it."""
        ...
