"""Ports for fetching one page over HTTP or a real browser.

Pure abstract contracts — no `httpx`/Playwright import here (those are
confined to `infrastructure/`). SSRF/size/timeout/redirect safety is the
concrete HTTP adapter's responsibility; this file only defines the shape
callers depend on.
"""

from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel

from app.modules.crawling.domain.models import HttpMetadata

FetchOutcome = Literal["fetched", "not_modified"]


class PageFetchRequest(BaseModel):
    url: str
    previous_etag: str | None = None
    previous_last_modified: str | None = None
    expected_content_type: str | None = None
    attempt: int = 1


class PageFetchResult(BaseModel):
    """The outcome of one successful `fetch_page` call.

    Every *failure* mode (timeout, oversized response, disallowed host,
    too many redirects, invalid content type) is represented by a typed
    `CrawlFetchError` subclass raised by the adapter — never returned
    here as a result value — so `outcome` only ever distinguishes between
    the two *non-error* shapes a request can resolve to: a fresh body
    (`"fetched"`) or a conditional-request short-circuit (`"not_modified"`,
    `body=None`).
    """

    status_code: int
    http_metadata: HttpMetadata
    body: bytes | None
    final_url: str
    outcome: FetchOutcome


class RenderedPageResult(BaseModel):
    html: str | None
    final_url: str | None
    duration_ms: int
    succeeded: bool
    error: str | None = None


class PageFetcher(ABC):
    """All failures raise a `CrawlFetchError` subclass — never a bare/
    unclassified exception (matching `HttpDiscoveryClient`'s discipline)."""

    @abstractmethod
    async def fetch_page(self, request: PageFetchRequest) -> PageFetchResult: ...


class BrowserPageFetcher(ABC):
    """A rendered-page fetch never raises — a failure is represented by
    `RenderedPageResult.succeeded=False` so a browser-fetch failure can
    never discard an already-successful HTTP result (section 14's
    failure-isolation requirement)."""

    @abstractmethod
    async def fetch_rendered_page(self, request: PageFetchRequest) -> RenderedPageResult: ...
