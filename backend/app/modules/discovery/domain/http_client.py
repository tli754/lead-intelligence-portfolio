"""Port for fetching content over HTTP(S) during discovery.

Pure abstract contract — no `httpx` import here (that's confined to
`infrastructure/httpx_discovery_client.py`). SSRF/size/timeout/redirect
safety is the concrete adapter's responsibility; this file only defines
the shape callers depend on.
"""

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from app.modules.discovery.domain.models import RedirectHop


class FetchResult(BaseModel):
    status_code: int
    content_type: str | None
    body: bytes
    final_url: str
    redirect_history: list[RedirectHop] = Field(default_factory=list)

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


class HomepageResolutionResult(BaseModel):
    success: bool
    homepage_url: str | None = None
    redirect_history: list[RedirectHop] = Field(default_factory=list)
    html: str | None = None
    failure_reason: str | None = None
    attempted_candidates: list[str] = Field(default_factory=list)


class HttpDiscoveryClient(ABC):
    """All four methods raise a `DiscoveryFetchError` subclass on failure
    (timeout, oversized response, disallowed host, too many redirects, or
    an unacceptable content type) — never a bare/unclassified exception."""

    @abstractmethod
    async def fetch_html(self, url: str) -> FetchResult:
        """Fetches `url`, requiring an HTML content type."""
        ...

    @abstractmethod
    async def fetch_text(self, url: str) -> FetchResult:
        """Fetches `url` as text (robots.txt, plain-text sitemaps) — more
        lenient content-type acceptance than `fetch_html`."""
        ...

    @abstractmethod
    async def fetch_binary(self, url: str) -> FetchResult:
        """Fetches `url` as raw bytes (e.g. a possibly-gzipped sitemap)."""
        ...

    @abstractmethod
    async def resolve_homepage(self, candidates: list[str]) -> HomepageResolutionResult:
        """Tries each candidate URL in order, returning the first that
        resolves successfully over a validated redirect chain. Never
        raises — a total failure across every candidate is represented
        by `HomepageResolutionResult.success=False`."""
        ...
