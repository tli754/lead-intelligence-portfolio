"""Enumerations for the crawling module. Pure Python — no FastAPI or MongoDB imports."""

from enum import StrEnum


class CrawlStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PageFetchStatus(StrEnum):
    QUEUED = "queued"
    FETCHING = "fetching"
    FETCHED = "fetched"
    UNCHANGED = "unchanged"
    SKIPPED = "skipped"
    BLOCKED_BY_ROBOTS = "blocked_by_robots"
    REJECTED = "rejected"
    FAILED = "failed"
    BROWSER_REQUIRED = "browser_required"
    BROWSER_FETCHED = "browser_fetched"


class FetchMode(StrEnum):
    HTTP = "http"
    BROWSER = "browser"


class ContentStorageMode(StrEnum):
    INLINE = "inline"
    EXTERNAL = "external"
    NONE = "none"


class BrowserFallbackReason(StrEnum):
    EMPTY_HTML = "empty_html"
    JAVASCRIPT_SHELL = "javascript_shell"
    INSUFFICIENT_TEXT = "insufficient_text"
    CLIENT_RENDERED_MARKER = "client_rendered_marker"
    CHALLENGE_PAGE = "challenge_page"
    UNSUPPORTED_HTTP_RESPONSE = "unsupported_http_response"
    MANUALLY_REQUESTED = "manually_requested"


class BrowserPolicy(StrEnum):
    """How the crawl service should use a `BrowserPageFetcher`, if any.

    A documented addition (contract T1): not one of the brief's section-1
    record models, but a config/policy value required by section 10.
    """

    NEVER = "never"
    DETECT_ONLY = "detect_only"
    FETCH_WHEN_REQUIRED = "fetch_when_required"
    ALWAYS_FOR_SELECTED_PAGE_TYPES = "always_for_selected_page_types"
