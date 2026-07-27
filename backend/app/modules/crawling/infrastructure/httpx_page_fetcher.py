"""The real `PageFetcher` adapter, built directly on `HttpxDiscoveryClient`'s
already-established SSRF pattern (`modules/discovery/infrastructure/
httpx_discovery_client.py`) — a fresh `httpx.AsyncClient` per call with
`follow_redirects=False`, a manual redirect loop revalidating every hop,
`client.cookies.clear()` after every hop, streamed+size-capped body
reads, and literal-IP-or-`getaddrinfo`-based address validation rejecting
private/loopback/link-local/multicast/reserved/unspecified addresses
(`localhost`/`*.localhost` rejected by name before DNS). This file is
independent of discovery's module (no cross-module infrastructure
import — each module owns its own HTTP client), duplicated deliberately
per the architecture's module-boundary rules.

Extended beyond discovery's client with: GET-only (never configurable);
`Authorization`/cookie headers never set; credentials in the URL
rejected outright; conditional (`If-None-Match`/`If-Modified-Since`)
requests, mapping a `304` straight to `outcome="not_modified"`;
`Accept-Encoding: gzip` only, deliberately never `br` (see module-level
note below); bounded exponential backoff+jitter honoring a capped
`Retry-After` header on retryable statuses; an allowlisted response-
header pass-through; and an overall per-call timeout budget in addition
to discovery's per-hop connect/read timeouts.

## Brotli is out of scope

No Brotli-capable package (`brotli`/`brotlicffi`) is a dependency of this
repository, and `pyproject.toml` is off-limits to this module. Resolution:
this fetcher never advertises `br` in `Accept-Encoding` (only `gzip`), so
a compliant server never sends a Brotli-encoded response in the first
place. If a server sends `Content-Encoding: br` unprompted anyway, it is
not decoded (httpx would raise attempting to do so) — a documented
residual gap, not silently mishandled.

## DNS-rebinding / TOCTOU: what is and isn't covered here

Identical residual risk to `HttpxDiscoveryClient`'s own module docstring,
copied forward rather than silently repeated: the safety check happens
immediately before each request, but `httpx`'s own connection internally
re-resolves the hostname when it actually opens the socket. A DNS server
returning a validated public IP to our check and a private IP (with a
very short TTL) to the moment `httpx` connects would bypass this. Full
closure needs a custom transport pinning the validated IP at the socket
level, out of scope for this task.
"""

import asyncio
import ipaddress
import logging
import socket
import time
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

import httpx

from app.modules.crawling.domain.config import CrawlConfig
from app.modules.crawling.domain.exceptions import (
    DisallowedHostError,
    InvalidContentTypeError,
    OversizedResponseError,
    TimeoutFetchError,
    TooManyRedirectsError,
)
from app.modules.crawling.domain.models import HttpMetadata, RedirectHop
from app.modules.crawling.domain.page_fetcher import PageFetcher, PageFetchRequest, PageFetchResult
from app.modules.crawling.domain.retry_policy import compute_backoff_delay, is_transient_failure

logger = logging.getLogger(__name__)

_ALLOWED_SCHEMES = frozenset({"http", "https"})
_REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})
_NOT_MODIFIED = 304

IpAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
AsyncSleep = Callable[[float], Awaitable[None]]


class _RawFetchResult:
    """Internal, pre-classification result of one redirect-following
    request — not yet decided as retryable/terminal by the caller."""

    __slots__ = ("status_code", "headers", "body", "final_url", "redirect_history", "duration_ms")

    def __init__(
        self,
        *,
        status_code: int,
        headers: httpx.Headers,
        body: bytes | None,
        final_url: str,
        redirect_history: list[RedirectHop],
        duration_ms: int,
    ) -> None:
        self.status_code = status_code
        self.headers = headers
        self.body = body
        self.final_url = final_url
        self.redirect_history = redirect_history
        self.duration_ms = duration_ms


class HttpxPageFetcher(PageFetcher):
    def __init__(
        self,
        config: CrawlConfig | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: AsyncSleep | None = None,
        jitter_source: Callable[[], float] | None = None,
    ) -> None:
        self._config = config or CrawlConfig()
        # None uses httpx's real network transport. Tests inject an
        # `httpx.MockTransport` here instead of touching the network.
        self._transport = transport
        self._sleep = sleep or asyncio.sleep
        self._jitter_source = jitter_source

    async def fetch_page(self, request: PageFetchRequest) -> PageFetchResult:
        deadline = time.monotonic() + self._config.total_timeout_s
        try:
            return await asyncio.wait_for(
                self._fetch_with_retries(request, deadline=deadline),
                timeout=self._config.total_timeout_s,
            )
        except TimeoutError as error:
            raise TimeoutFetchError(request.url) from error

    async def _fetch_with_retries(
        self, request: PageFetchRequest, *, deadline: float
    ) -> PageFetchResult:
        last_result: _RawFetchResult | None = None
        last_error: TimeoutFetchError | None = None

        for attempt in range(1, self._config.max_attempts + 1):
            try:
                raw = await self._fetch_once(request)
            except TimeoutFetchError as error:
                last_error = error
                if attempt >= self._config.max_attempts or not is_transient_failure(None, error):
                    raise
                await self._wait_before_retry(attempt, retry_after_s=None)
                continue

            last_result = raw
            if raw.status_code == _NOT_MODIFIED:
                return self._to_page_fetch_result(raw, outcome="not_modified", body=None)

            if (
                is_transient_failure(
                    raw.status_code,
                    None,
                    retryable_status_codes=self._config.retryable_status_codes,
                )
                and attempt < self._config.max_attempts
            ):
                retry_after_s = _parse_retry_after(raw.headers.get("retry-after"))
                await self._wait_before_retry(attempt, retry_after_s=retry_after_s)
                continue

            return self._to_page_fetch_result(raw, outcome="fetched", body=raw.body)

        if last_result is not None:
            return self._to_page_fetch_result(last_result, outcome="fetched", body=last_result.body)
        assert last_error is not None  # every loop exit path sets one of these
        raise last_error

    async def _wait_before_retry(self, attempt: int, *, retry_after_s: float | None) -> None:
        if retry_after_s is not None:
            delay = min(retry_after_s, self._config.max_retry_after_s)
        else:
            kwargs: dict = {
                "base_delay_s": self._config.retry_base_delay_s,
                "max_delay_s": self._config.retry_max_delay_s,
            }
            if self._jitter_source is not None:
                kwargs["jitter_source"] = self._jitter_source
            delay = compute_backoff_delay(attempt, **kwargs)
        await self._sleep(delay)

    def _to_page_fetch_result(
        self, raw: _RawFetchResult, *, outcome: str, body: bytes | None
    ) -> PageFetchResult:
        allowlisted = {
            key.lower(): value
            for key, value in raw.headers.items()
            if key.lower() in self._config.response_headers_allowlist
        }
        http_metadata = HttpMetadata(
            status_code=raw.status_code,
            content_type=raw.headers.get("content-type"),
            content_length=_parse_int(raw.headers.get("content-length")),
            etag=raw.headers.get("etag"),
            last_modified=raw.headers.get("last-modified"),
            redirect_history=raw.redirect_history,
            response_headers_allowlist=allowlisted,
            duration_ms=raw.duration_ms,
            remote_ip_validation_result="validated",
        )
        return PageFetchResult(
            status_code=raw.status_code,
            http_metadata=http_metadata,
            body=body,
            final_url=raw.final_url,
            outcome=outcome,  # type: ignore[arg-type]
        )

    async def _fetch_once(self, request: PageFetchRequest) -> _RawFetchResult:
        redirect_history: list[RedirectHop] = []
        current_url = request.url
        start = time.monotonic()

        timeout = httpx.Timeout(
            connect=self._config.connect_timeout_s,
            read=self._config.read_timeout_s,
            write=self._config.connect_timeout_s,
            pool=self._config.connect_timeout_s,
        )

        headers = {"User-Agent": self._config.user_agent, "Accept-Encoding": "gzip"}
        if request.previous_etag:
            headers["If-None-Match"] = request.previous_etag
        if request.previous_last_modified:
            headers["If-Modified-Since"] = request.previous_last_modified

        async with httpx.AsyncClient(
            follow_redirects=False, timeout=timeout, transport=self._transport
        ) as client:
            for _ in range(self._config.max_redirects + 1):
                await self._validate_url_safety(current_url)

                try:
                    async with client.stream("GET", current_url, headers=headers) as response:
                        content_type = response.headers.get("content-type")
                        body = (
                            None
                            if response.status_code == _NOT_MODIFIED
                            else await self._read_capped(response, current_url)
                        )
                        response_headers = response.headers
                except httpx.TimeoutException as error:
                    raise TimeoutFetchError(current_url) from error
                except httpx.HTTPError as error:
                    raise TimeoutFetchError(current_url) from error
                finally:
                    client.cookies.clear()

                if response.status_code in _REDIRECT_STATUS_CODES:
                    location = response.headers.get("location")
                    if not location:
                        raise DisallowedHostError(
                            current_url, reason="redirect with no Location header"
                        )
                    next_url = str(httpx.URL(current_url).join(location))
                    redirect_history.append(
                        RedirectHop(url=current_url, status_code=response.status_code)
                    )
                    current_url = next_url
                    continue

                if 200 <= response.status_code < 300:
                    # Content-type validation only applies to a genuine
                    # page response — error/status pages (4xx/5xx) are
                    # exempt, since they're not the content being crawled.
                    self._validate_content_type(
                        current_url, content_type, expected=request.expected_content_type
                    )

                duration_ms = int((time.monotonic() - start) * 1000)
                return _RawFetchResult(
                    status_code=response.status_code,
                    headers=response_headers,
                    body=body,
                    final_url=current_url,
                    redirect_history=redirect_history,
                    duration_ms=duration_ms,
                )

        raise TooManyRedirectsError(request.url, max_redirects=self._config.max_redirects)

    def _validate_content_type(
        self, url: str, content_type: str | None, *, expected: str | None
    ) -> None:
        if content_type is None:
            return  # Missing content-type is common server misconfiguration — tolerated.
        lowered = content_type.lower()
        if "html" in lowered:
            return
        if expected == "text/plain" and "text/" in lowered:
            return
        raise InvalidContentTypeError(url, content_type=content_type)

    async def _read_capped(self, response: httpx.Response, url: str) -> bytes:
        chunks: list[bytes] = []
        total = 0
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > self._config.max_response_size_bytes:
                raise OversizedResponseError(url, max_size=self._config.max_response_size_bytes)
            chunks.append(chunk)
        return b"".join(chunks)

    async def _validate_url_safety(self, url: str) -> None:
        parts = urlsplit(url)
        scheme = parts.scheme.lower()
        if scheme not in _ALLOWED_SCHEMES:
            raise DisallowedHostError(url, reason=f"unsupported scheme: {scheme or '(none)'}")

        if parts.username is not None or parts.password is not None:
            raise DisallowedHostError(url, reason="credentials in URL are not allowed")

        hostname = parts.hostname
        if not hostname:
            raise DisallowedHostError(url, reason="missing host")

        if hostname == "localhost" or hostname.endswith(".localhost"):
            raise DisallowedHostError(url, reason="localhost is not allowed")

        addresses = self._literal_ip(hostname)
        if addresses is None:
            addresses = await self._resolve_all(hostname)
            if not addresses:
                raise DisallowedHostError(
                    url, reason="DNS resolution failed or returned no addresses"
                )

        for address in addresses:
            if _is_disallowed_address(address):
                raise DisallowedHostError(
                    url, reason=f"resolved address {address} is private/internal"
                )

    def _literal_ip(self, hostname: str) -> list[IpAddress] | None:
        try:
            return [ipaddress.ip_address(hostname)]
        except ValueError:
            return None

    async def _resolve_all(self, hostname: str) -> list[IpAddress]:
        loop = asyncio.get_event_loop()
        try:
            infos = await loop.getaddrinfo(hostname, None)
        except socket.gaierror:
            return []

        addresses: list[IpAddress] = []
        for info in infos:
            raw_ip = info[4][0]
            try:
                addresses.append(ipaddress.ip_address(raw_ip))
            except ValueError:
                continue
        return addresses


def _is_disallowed_address(address: IpAddress) -> bool:
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_retry_after(value: str | None) -> float | None:
    """Only numeric (seconds) `Retry-After` values are supported — the
    HTTP-date form is not parsed, a documented limitation rather than a
    silent failure (falls back to computed backoff in that case)."""
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None
