"""Domain-level errors for the crawling module."""


class CrawlDomainError(Exception):
    """Base class for crawling-module domain errors."""


class CompanyNotFoundForCrawlError(CrawlDomainError):
    def __init__(self, company_id: str) -> None:
        super().__init__(f"no company with company_id={company_id!r}")
        self.company_id = company_id


class DiscoveryRunNotFoundForCrawlError(CrawlDomainError):
    def __init__(self, discovery_run_id: str) -> None:
        super().__init__(f"no discovery run with discovery_run_id={discovery_run_id!r}")
        self.discovery_run_id = discovery_run_id


class CrawlRunNotFoundError(CrawlDomainError):
    def __init__(self, crawl_run_id: str) -> None:
        super().__init__(f"no crawl run with crawl_run_id={crawl_run_id!r}")
        self.crawl_run_id = crawl_run_id


class CrawlTargetNotFoundError(CrawlDomainError):
    def __init__(self, crawl_target_id: str) -> None:
        super().__init__(f"no crawl target with crawl_target_id={crawl_target_id!r}")
        self.crawl_target_id = crawl_target_id


class PageNotFoundError(CrawlDomainError):
    def __init__(self, page_id: str) -> None:
        super().__init__(f"no page with page_id={page_id!r}")
        self.page_id = page_id


class DuplicateActiveCrawlRunError(CrawlDomainError):
    """Raised instead of silently returning the existing run under a 200.

    The router translates this to HTTP 409 Conflict, carrying the
    existing run's id/status in the error body — mirroring
    `DuplicateCompanyError`'s and `InvalidStatusTransitionError`'s
    existing 409 precedent in `modules/companies`.
    """

    def __init__(self, *, existing_crawl_run_id: str, status: str) -> None:
        super().__init__(
            f"an active crawl run {existing_crawl_run_id!r} (status={status!r}) "
            "already exists for this company/discovery-run/options combination"
        )
        self.existing_crawl_run_id = existing_crawl_run_id
        self.status = status


class CrawlFetchError(CrawlDomainError):
    """Base class for a single-request fetch failure. Non-fatal at the
    run level — the crawl service catches this per target and records a
    page-level failure/warning rather than aborting the whole run."""


class TimeoutFetchError(CrawlFetchError):
    def __init__(self, url: str) -> None:
        super().__init__(f"request to {url!r} timed out")
        self.url = url


class OversizedResponseError(CrawlFetchError):
    def __init__(self, url: str, *, max_size: int) -> None:
        super().__init__(f"response from {url!r} exceeded the {max_size}-byte limit")
        self.url = url
        self.max_size = max_size


class DisallowedHostError(CrawlFetchError):
    def __init__(self, url: str, *, reason: str) -> None:
        super().__init__(f"request to {url!r} rejected: {reason}")
        self.url = url
        self.reason = reason


class TooManyRedirectsError(CrawlFetchError):
    def __init__(self, url: str, *, max_redirects: int) -> None:
        super().__init__(f"request to {url!r} exceeded {max_redirects} redirects")
        self.url = url
        self.max_redirects = max_redirects


class InvalidContentTypeError(CrawlFetchError):
    """Raised by the HTTP fetcher when a response's content type isn't
    acceptable for what was requested (an HTTP-layer rejection, before
    any body content has been interpreted)."""

    def __init__(self, url: str, *, content_type: str | None) -> None:
        super().__init__(f"response from {url!r} had unacceptable content type {content_type!r}")
        self.url = url
        self.content_type = content_type


class EmptyResponseError(CrawlFetchError):
    """A documented addition beyond T4's literal exception list — AC-18
    explicitly names this error for an empty response body, a distinct
    case from `NonHtmlResponseError`'s binary-signature/content-type
    rejections."""

    def __init__(self, url: str, *, reason: str) -> None:
        super().__init__(f"response from {url!r} is empty: {reason}")
        self.url = url
        self.reason = reason


class NonHtmlResponseError(CrawlFetchError):
    """Raised by `domain/html_validator.py` when an already-fetched body
    is clearly not page content (binary signature, image/pdf/zip/
    executable/media content type) — a content-interpretation rejection,
    distinct from `InvalidContentTypeError`'s HTTP-layer header check."""

    def __init__(self, url: str, *, reason: str) -> None:
        super().__init__(f"response from {url!r} is not a page: {reason}")
        self.url = url
        self.reason = reason


class StorageIntegrityError(CrawlDomainError):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class UnsafeStoragePathError(CrawlDomainError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
