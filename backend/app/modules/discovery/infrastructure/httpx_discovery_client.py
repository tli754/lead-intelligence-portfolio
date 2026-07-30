"""The real `HttpDiscoveryClient` adapter, built on `httpx`.

`httpx` is currently a **dev-only** dependency (used only for the ASGI
test client in `backend/tests/conftest.py`) — not yet in
`[project.dependencies]`. It's the only async-HTTP-capable library
already present in this environment and the project's own test
infrastructure already depends on it, so it's the closest thing to
"reuse the existing HTTP pattern" available without adding a brand-new
dependency (which would also require a `pyproject.toml` edit, off-limits
to this module). **Required integration step**: promote `httpx` to
`[project.dependencies]`.

## SSRF / DNS-rebinding: what is and isn't covered here

Every request (the initial URL and each redirect hop) resolves its
hostname and validates every resolved address as public before
connecting. This blocks the common SSRF cases (redirect to
`169.254.169.254`, a link to `10.0.0.5`, etc.).

**Not covered — documented residual risk:** the `getaddrinfo` validation
happens immediately before each request, but `httpx`'s own connection
internally re-resolves the hostname when it actually opens the socket.
A DNS server returning a validated public IP to our check and a private
IP (with a very short TTL) to the moment `httpx` connects would bypass
this — a classic TOCTOU/DNS-rebinding gap. Full closure requires a
custom transport that pins the validated IP at the socket level while
preserving the original `Host`/SNI, which is out of scope for this
ticket (the task explicitly allows documenting this instead of fully
closing it).
"""

import asyncio
import ipaddress
import logging
import socket
from urllib.parse import urlsplit

import httpx

from app.modules.discovery.domain.config import DiscoveryConfig
from app.modules.discovery.domain.exceptions import (
    DisallowedHostError,
    InvalidContentTypeError,
    OversizedResponseError,
    TimeoutFetchError,
    TooManyRedirectsError,
)
from app.modules.discovery.domain.http_client import (
    FetchResult,
    HomepageResolutionResult,
    HttpDiscoveryClient,
)
from app.modules.discovery.domain.models import RedirectHop

logger = logging.getLogger(__name__)

_ALLOWED_SCHEMES = frozenset({"http", "https"})
_REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})

_HTML_CONTENT_TYPES = ("html",)
_TEXT_CONTENT_TYPES = ("text/", "xml")

IpAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


class HttpxDiscoveryClient(HttpDiscoveryClient):
    def __init__(
        self,
        config: DiscoveryConfig | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = config or DiscoveryConfig()
        self._semaphore = asyncio.Semaphore(self._config.max_concurrent_requests)
        # None uses httpx's real network transport. Tests inject an
        # `httpx.MockTransport` here instead of touching the network.
        self._transport = transport

    async def fetch_html(self, url: str) -> FetchResult:
        return await self._fetch(url, accept_content_types=_HTML_CONTENT_TYPES)

    async def fetch_text(self, url: str) -> FetchResult:
        return await self._fetch(url, accept_content_types=_TEXT_CONTENT_TYPES)

    async def fetch_binary(self, url: str) -> FetchResult:
        # No content-type restriction: sitemaps are served under a wide
        # variety of (sometimes misconfigured) content types — the
        # sitemap parser sniffs the body itself rather than trusting the
        # header.
        return await self._fetch(url, accept_content_types=None)

    async def resolve_homepage(self, candidates: list[str]) -> HomepageResolutionResult:
        attempted: list[str] = []
        for candidate in candidates:
            attempted.append(candidate)
            try:
                result = await self._fetch(candidate, accept_content_types=_HTML_CONTENT_TYPES)
            except Exception as error:
                logger.info("homepage candidate failed: %s (%s)", candidate, error)
                continue
            return HomepageResolutionResult(
                success=True,
                homepage_url=result.final_url,
                redirect_history=result.redirect_history,
                html=result.text,
                attempted_candidates=attempted,
            )
        return HomepageResolutionResult(
            success=False,
            failure_reason="all homepage candidates failed",
            attempted_candidates=attempted,
        )

    async def _fetch(
        self, url: str, *, accept_content_types: tuple[str, ...] | None
    ) -> FetchResult:
        redirect_history: list[RedirectHop] = []
        current_url = url

        timeout = httpx.Timeout(
            connect=self._config.connect_timeout_s,
            read=self._config.read_timeout_s,
            write=self._config.connect_timeout_s,
            pool=self._config.connect_timeout_s,
        )

        async with self._semaphore:
            # A fresh client per call — never reused across `_fetch`
            # invocations, so no cookies or auth state ever carry over
            # between requests. `client.cookies.clear()` after every hop
            # (below) additionally guarantees no `Set-Cookie` response
            # from an earlier redirect hop is echoed back on a later one
            # within the *same* call's redirect chain.
            async with httpx.AsyncClient(
                follow_redirects=False, timeout=timeout, transport=self._transport
            ) as client:
                for _ in range(self._config.max_redirects + 1):
                    await self._validate_url_safety(current_url)

                    try:
                        async with client.stream(
                            "GET",
                            current_url,
                            headers={"User-Agent": self._config.user_agent},
                        ) as response:
                            content_type = response.headers.get("content-type")
                            body = await self._read_capped(response, current_url)
                    except httpx.TimeoutException as error:
                        raise TimeoutFetchError(current_url) from error
                    except httpx.HTTPError as error:
                        raise DisallowedHostError(current_url, reason=str(error)) from error
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

                    if accept_content_types is not None:
                        self._validate_content_type(current_url, content_type, accept_content_types)

                    return FetchResult(
                        status_code=response.status_code,
                        content_type=content_type,
                        body=body,
                        final_url=current_url,
                        redirect_history=redirect_history,
                    )

        raise TooManyRedirectsError(url, max_redirects=self._config.max_redirects)

    def _validate_content_type(
        self, url: str, content_type: str | None, accept_content_types: tuple[str, ...]
    ) -> None:
        if content_type is None:
            # Missing content-type is common server misconfiguration —
            # tolerated rather than rejected outright.
            return
        lowered = content_type.lower()
        if not any(marker in lowered for marker in accept_content_types):
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
