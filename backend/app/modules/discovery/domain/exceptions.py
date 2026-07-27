"""Domain-level errors for the discovery module."""


class DiscoveryDomainError(Exception):
    """Base class for discovery-module domain errors."""


class CompanyNotFoundForDiscoveryError(DiscoveryDomainError):
    def __init__(self, company_id: str) -> None:
        super().__init__(f"no company with company_id={company_id!r}")
        self.company_id = company_id


class DiscoveryRunNotFoundError(DiscoveryDomainError):
    def __init__(self, discovery_run_id: str) -> None:
        super().__init__(f"no discovery run with discovery_run_id={discovery_run_id!r}")
        self.discovery_run_id = discovery_run_id


class HomepageResolutionFailedError(DiscoveryDomainError):
    """The one error that aborts an entire discovery run — without a
    homepage, discovery cannot continue reliably."""

    def __init__(self, reason: str, *, attempts: list[str]) -> None:
        super().__init__(f"homepage resolution failed: {reason} (tried: {', '.join(attempts)})")
        self.reason = reason
        self.attempts = attempts


class DiscoveryFetchError(DiscoveryDomainError):
    """Base class for a single-request fetch failure. Non-fatal at the
    run level — callers catch this per step (robots, one sitemap, etc.)."""


class TimeoutFetchError(DiscoveryFetchError):
    def __init__(self, url: str) -> None:
        super().__init__(f"request to {url!r} timed out")
        self.url = url


class OversizedResponseError(DiscoveryFetchError):
    def __init__(self, url: str, *, max_size: int) -> None:
        super().__init__(f"response from {url!r} exceeded the {max_size}-byte limit")
        self.url = url
        self.max_size = max_size


class DisallowedHostError(DiscoveryFetchError):
    def __init__(self, url: str, *, reason: str) -> None:
        super().__init__(f"request to {url!r} rejected: {reason}")
        self.url = url
        self.reason = reason


class TooManyRedirectsError(DiscoveryFetchError):
    def __init__(self, url: str, *, max_redirects: int) -> None:
        super().__init__(f"request to {url!r} exceeded {max_redirects} redirects")
        self.url = url
        self.max_redirects = max_redirects


class InvalidContentTypeError(DiscoveryFetchError):
    def __init__(self, url: str, *, content_type: str | None) -> None:
        super().__init__(f"response from {url!r} had unacceptable content type {content_type!r}")
        self.url = url
        self.content_type = content_type
