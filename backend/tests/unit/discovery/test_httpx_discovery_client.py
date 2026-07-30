"""Tests for `HttpxDiscoveryClient` — the SSRF/safety-critical HTTP
adapter used for homepage resolution, robots.txt, and sitemap fetching.

Uses `httpx.MockTransport` so nothing here touches the real network.
DNS resolution for non-literal hostnames is monkeypatched to a fixed
public address (`_fake_public_dns` below) so tests are deterministic and
don't depend on real DNS either — only literal IPs in test URLs (used
for the private-host-rejection cases) exercise the real `ipaddress`
validation logic.
"""

import ipaddress
from collections.abc import Callable

import httpx
import pytest

from app.modules.discovery.domain.config import DiscoveryConfig
from app.modules.discovery.domain.exceptions import (
    DisallowedHostError,
    InvalidContentTypeError,
    OversizedResponseError,
    TimeoutFetchError,
    TooManyRedirectsError,
)
from app.modules.discovery.infrastructure.httpx_discovery_client import (
    HttpxDiscoveryClient,
    IpAddress,
)

_PUBLIC_IP = ipaddress.ip_address("93.184.216.34")

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture(autouse=True)
def _fake_public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _resolve_all(self: HttpxDiscoveryClient, hostname: str) -> list[IpAddress]:
        return [_PUBLIC_IP]

    monkeypatch.setattr(HttpxDiscoveryClient, "_resolve_all", _resolve_all)


def _make_client(
    handler: Handler, *, config: DiscoveryConfig | None = None
) -> HttpxDiscoveryClient:
    transport = httpx.MockTransport(handler)
    return HttpxDiscoveryClient(config or DiscoveryConfig(), transport=transport)


def _html(
    status_code: int = 200, body: bytes = b"<html><body>ok</body></html>"
) -> httpx.Response:
    headers = {"content-type": "text/html; charset=utf-8"}
    return httpx.Response(status_code, content=body, headers=headers)


def _redirect(location: str, status_code: int = 302) -> httpx.Response:
    return httpx.Response(status_code, headers={"location": location})


class TestResolveHomepage:
    async def test_https_succeeds_first(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert str(request.url) == "https://good.test/"
            return _html()

        client = _make_client(handler)
        result = await client.resolve_homepage(
            [
                "https://good.test/",
                "https://www.good.test/",
                "http://good.test/",
                "http://www.good.test/",
            ]
        )

        assert result.success is True
        assert result.homepage_url == "https://good.test/"
        assert result.attempted_candidates == ["https://good.test/"]

    async def test_www_fallback(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if str(request.url) == "https://good.test/":
                raise httpx.ConnectError("connection refused", request=request)
            return _html()

        client = _make_client(handler)
        result = await client.resolve_homepage(
            ["https://good.test/", "https://www.good.test/", "http://good.test/"]
        )

        assert result.success is True
        assert result.homepage_url == "https://www.good.test/"
        assert result.attempted_candidates == ["https://good.test/", "https://www.good.test/"]

    async def test_http_fallback(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.scheme == "https":
                raise httpx.ConnectError("connection refused", request=request)
            return _html()

        client = _make_client(handler)
        result = await client.resolve_homepage(
            [
                "https://good.test/",
                "https://www.good.test/",
                "http://good.test/",
                "http://www.good.test/",
            ]
        )

        assert result.success is True
        assert result.homepage_url == "http://good.test/"
        assert result.attempted_candidates == [
            "https://good.test/",
            "https://www.good.test/",
            "http://good.test/",
        ]

    async def test_all_candidates_fail_returns_typed_failure(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        client = _make_client(handler)
        result = await client.resolve_homepage(["https://good.test/", "http://good.test/"])

        assert result.success is False
        assert result.failure_reason is not None
        assert result.attempted_candidates == ["https://good.test/", "http://good.test/"]


class TestSafeRedirect:
    async def test_redirect_is_followed_and_recorded(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if str(request.url) == "https://good.test/old":
                return _redirect("https://good.test/new")
            assert str(request.url) == "https://good.test/new"
            return _html()

        client = _make_client(handler)
        result = await client.fetch_html("https://good.test/old")

        assert result.final_url == "https://good.test/new"
        assert len(result.redirect_history) == 1
        assert result.redirect_history[0].url == "https://good.test/old"
        assert result.redirect_history[0].status_code == 302


class TestRedirectLoop:
    async def test_loop_raises_too_many_redirects(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            next_url = "https://b.test/" if url == "https://a.test/" else "https://a.test/"
            return _redirect(next_url)

        client = _make_client(handler, config=DiscoveryConfig(max_redirects=3))

        with pytest.raises(TooManyRedirectsError):
            await client.fetch_html("https://a.test/")


class TestRedirectToPrivateHost:
    async def test_redirect_to_private_ip_rejected(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert str(request.url) == "https://good.test/"
            return _redirect("http://10.0.0.5/internal")

        client = _make_client(handler)

        with pytest.raises(DisallowedHostError):
            await client.fetch_html("https://good.test/")

    async def test_redirect_to_loopback_rejected(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _redirect("http://127.0.0.1/admin")

        client = _make_client(handler)

        with pytest.raises(DisallowedHostError):
            await client.fetch_html("https://good.test/")


class TestContentType:
    async def test_non_html_response_rejected(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"{}", headers={"content-type": "application/json"})

        client = _make_client(handler)

        with pytest.raises(InvalidContentTypeError):
            await client.fetch_html("https://good.test/")

    async def test_missing_content_type_is_tolerated(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"<html></html>")

        client = _make_client(handler)
        result = await client.fetch_html("https://good.test/")

        assert result.status_code == 200


class TestOversizedResponse:
    async def test_oversized_response_rejected(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _html(body=b"x" * 1000)

        client = _make_client(handler, config=DiscoveryConfig(max_response_size_bytes=100))

        with pytest.raises(OversizedResponseError):
            await client.fetch_html("https://good.test/")


class TestTimeout:
    async def test_timeout_returns_typed_failure(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("simulated timeout", request=request)

        client = _make_client(handler)

        with pytest.raises(TimeoutFetchError):
            await client.fetch_html("https://good.test/")
