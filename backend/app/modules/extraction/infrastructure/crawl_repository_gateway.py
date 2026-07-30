"""The real `CrawlExtractionGateway` adapter, wrapping `CrawlRepository`
and `ContentStorage` (both interfaces, never `MongoCrawlRepository`/
`LocalFilesystemContentStorage` concretely) — contract resolution #1.

`list_pages` pages through `CrawlRepository.list_pages_by_run` exhaustively
(it only accepts a single `status`/`page_type` filter, not the brief's
plural `statuses`/`page_types`) and filters in-memory — the same
"loop until exhausted" precedent `DiscoveryRepositoryCrawlGateway.list_discovered_urls`
already established in Task 006 for an identical singular/plural mismatch.

`load_page_content` transparently follows a single `unchanged_from_page_id`
hop when the requested page's own content for `content_kind` is empty —
a page whose `fetch_status == "unchanged"` never re-populates its own
`cleaned_html`/`extracted_text`/`raw_content_reference`; the actual content
lives on the page it points to. Only one hop is ever followed (crawling's
own change-detection never chains more than one, confirmed by
`WebsiteCrawlService`'s `get_latest_page_by_normalized_url` usage always
pointing at the immediately-preceding page) — a residual assumption if
that ever changes, documented here rather than silently made.
"""

from app.modules.crawling.domain.content_storage import ContentStorage
from app.modules.crawling.domain.enums import PageFetchStatus
from app.modules.crawling.domain.models import CrawledPage, CrawlRun
from app.modules.crawling.domain.repository import CrawlRepository
from app.modules.discovery.domain.enums import PageType
from app.modules.extraction.domain.exceptions import CrawlRunNotFoundForExtractionError
from app.modules.extraction.domain.gateway import ContentKind, CrawlExtractionGateway

_PAGE_SIZE = 200


class CrawlRepositoryExtractionGateway(CrawlExtractionGateway):
    def __init__(self, repository: CrawlRepository, content_storage: ContentStorage) -> None:
        self._repository = repository
        self._content_storage = content_storage

    async def get_crawl_run(self, crawl_run_id: str) -> CrawlRun:
        run = await self._repository.get_run(crawl_run_id)
        if run is None:
            raise CrawlRunNotFoundForExtractionError(crawl_run_id)
        return run

    async def list_pages(
        self,
        crawl_run_id: str,
        *,
        statuses: list[PageFetchStatus] | None = None,
        page_types: list[PageType] | None = None,
    ) -> list[CrawledPage]:
        pages: list[CrawledPage] = []
        page_number = 1
        while True:
            result = await self._repository.list_pages_by_run(
                crawl_run_id, include_failed=True, page=page_number, page_size=_PAGE_SIZE
            )
            pages.extend(result.items)
            if len(result.items) < _PAGE_SIZE:
                break
            page_number += 1

        if statuses is not None:
            allowed_statuses = set(statuses)
            pages = [page for page in pages if page.fetch_status in allowed_statuses]
        if page_types is not None:
            allowed_types = set(page_types)
            pages = [page for page in pages if page.page_type in allowed_types]
        return pages

    async def load_page_content(self, page_id: str, content_kind: ContentKind) -> bytes | None:
        page = await self._repository.get_page(page_id)
        if page is None:
            return None

        content = await self._load_from_page(page, content_kind)
        if content is not None:
            return content

        if page.unchanged_from_page_id is not None:
            predecessor = await self._repository.get_page(page.unchanged_from_page_id)
            if predecessor is not None:
                return await self._load_from_page(predecessor, content_kind)
        return None

    async def _load_from_page(self, page: CrawledPage, content_kind: ContentKind) -> bytes | None:
        if content_kind == "raw":
            if page.raw_content_reference is not None:
                return await self._content_storage.load_content(page.raw_content_reference)
            return None
        if content_kind == "cleaned":
            if page.cleaned_html:
                return page.cleaned_html.encode("utf-8")
            if page.content_storage.cleaned_html_reference is not None:
                return await self._content_storage.load_content(
                    page.content_storage.cleaned_html_reference
                )
            return None
        if content_kind == "text":
            if page.extracted_text:
                return page.extracted_text.encode("utf-8")
            if page.content_storage.extracted_text_reference is not None:
                return await self._content_storage.load_content(
                    page.content_storage.extracted_text_reference
                )
            return None
        raise ValueError(f"unsupported content_kind: {content_kind!r}")
