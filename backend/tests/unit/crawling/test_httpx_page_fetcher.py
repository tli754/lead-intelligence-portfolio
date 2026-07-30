"""Tests for `HttpxPageFetcher` — the SSRF/safety-critical HTTP adapter.

Uses `httpx.MockTransport` so nothing here touches the real network. DNS
resolution for non-literal hostnames is monkeypatched to a fixed public
address so tests are deterministic — only literal IPs in test URLs (used
for the private-host-rejection cases) exercise the real `ipaddress`
validation logic. Exactly matches `test_httpx_discovery_client.py`'s
established pattern.
"""

import ipaddress
from collections.abc import Callable

import httpx
import pytest

from app.modules.crawling.domain.config import CrawlConfig
from app.modules.crawling.domain.exceptions import (
    DisallowedHostError,
    InvalidContentTypeError,
    OversizedResponseError,
    TimeoutFetchError,
    TooManyRedirectsError,
)
from app.modules.crawling.domain.page_fetcher import PageFetchRequest
from app.modules.crawling.infrastructure.httpx_page_fetcher import (
    HttpxPageFetcher,
    IpAddress,
)

_PUBLIC_IP = ipaddress.ip_address("93.184.216.34")

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture(autouse=True)
def _fake_public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _resolve_all(self: HttpxPageFetcher, hostname: str) -> list[IpAddress]:
        return [_PUBLIC_IP]

    monkeypatch.setattr(HttpxPageFetcher, "_resolve_all", _resolve_all)


async def _no_sleep(_delay: float) -> None:
    return None


def _make_fetcher(
    handler: Handler,
    *,
    config: CrawlConfig | None = None,
    sleep=None,
) -> HttpxPageFetcher:
    transport = httpx.MockTransport(handler)
    return HttpxPageFetcher(
        config or CrawlConfig(),
        transport=transport,
        sleep=sleep or _no_sleep,
        jitter_source=lambda: 1.0,
    )


def _html(
    status_code: int = 200,
    body: bytes = b"<html><body>ok</body></html>",
    extra_headers: dict[str, str] | None = None,
) -> httpx.Response:
    merged = {"content-type": "text/html; charset=utf-8", **(extra_headers or {})}
    return httpx.Response(status_code, content=body, headers=merged)


def _redirect(location: str, status_code: int = 302) -> httpx.Response:
    return httpx.Response(status_code, headers={"location": location})


class TestValidPublicPage:
    async def test_https_page_fetched_successfully(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert str(request.url) == "https://good.test/"
            assert request.method == "GET"
            return _html()

        fetcher = _make_fetcher(handler)
        result = await fetcher.fetch_page(PageFetchRequest(url="https://good.test/"))

        assert result.outcome == "fetched"
        assert result.status_code == 200
        assert result.body == b"<html><body>ok</body></html>"


class TestUnsafeTargetsRejected:
    async def test_unsupported_scheme_rejected(self) -> None:
        fetcher = _make_fetcher(lambda request: _html())
        with pytest.raises(DisallowedHostError):
            await fetcher.fetch_page(PageFetchRequest(url="ftp://good.test/file"))

    async def test_credentials_in_url_rejected(self) -> None:
        fetcher = _make_fetcher(lambda request: _html())
        with pytest.raises(DisallowedHostError):
            await fetcher.fetch_page(PageFetchRequest(url="https://user:pass@good.test/"))

    async def test_localhost_rejected(self) -> None:
        fetcher = _make_fetcher(lambda request: _html())
        with pytest.raises(DisallowedHostError):
            await fetcher.fetch_page(PageFetchRequest(url="https://localhost/"))

    async def test_loopback_ip_rejected(self) -> None:
        fetcher = _make_fetcher(lambda request: _html())
        with pytest.raises(DisallowedHostError):
            await fetcher.fetch_page(PageFetchRequest(url="http://127.0.0.1/"))

    async def test_link_local_metadata_ip_rejected(self) -> None:
        fetcher = _make_fetcher(lambda request: _html())
        with pytest.raises(DisallowedHostError):
            await fetcher.fetch_page(PageFetchRequest(url="http://169.254.169.254/"))

    async def test_private_ipv4_rejected(self) -> None:
        fetcher = _make_fetcher(lambda request: _html())
        with pytest.raises(DisallowedHostError):
            await fetcher.fetch_page(PageFetchRequest(url="http://10.0.0.5/"))

    async def test_private_ipv6_ula_rejected(self) -> None:
        fetcher = _make_fetcher(lambda request: _html())
        with pytest.raises(DisallowedHostError):
            await fetcher.fetch_page(PageFetchRequest(url="http://[fd00::1]/"))

    async def test_no_network_call_made_for_unsafe_targets(self) -> None:
        called = False

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal called
            called = True
            return _html()

        fetcher = _make_fetcher(handler)
        with pytest.raises(DisallowedHostError):
            await fetcher.fetch_page(PageFetchRequest(url="http://127.0.0.1/"))
        assert called is False


class TestRedirectToPrivateHost:
    async def test_redirect_to_private_host_rejected_before_body_read(self) -> None:
        second_hop_body_read = False

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal second_hop_body_read
            if str(request.url) == "https://good.test/":
                return _redirect("http://169.254.169.254/")
            second_hop_body_read = True
            return _html()

        fetcher = _make_fetcher(handler)
        with pytest.raises(DisallowedHostError):
            await fetcher.fetch_page(PageFetchRequest(url="https://good.test/"))
        assert second_hop_body_read is False


class TestRedirectAndSizeLimits:
    async def test_redirect_limit_exceeded(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            next_url = "https://b.test/" if url == "https://a.test/" else "https://a.test/"
            return _redirect(next_url)

        fetcher = _make_fetcher(handler, config=CrawlConfig(max_redirects=3))
        with pytest.raises(TooManyRedirectsError):
            await fetcher.fetch_page(PageFetchRequest(url="https://a.test/"))

    async def test_oversized_response_aborted_mid_stream(self) -> None:
        chunks_sent = 0

        async def _stream():
            nonlocal chunks_sent
            for _ in range(20):
                chunks_sent += 1
                yield b"x" * 100

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"content-type": "text/html"},
                stream=_ChunkedStream(_stream()),
            )

        fetcher = _make_fetcher(handler, config=CrawlConfig(max_response_size_bytes=250))
        with pytest.raises(OversizedResponseError):
            await fetcher.fetch_page(PageFetchRequest(url="https://good.test/"))

        # 250-byte limit / 100-byte chunks: aborts on the 3rd chunk, well
        # before all 20 configured chunks (2000 bytes) were ever sent.
        assert chunks_sent < 20


class _ChunkedStream(httpx.AsyncByteStream):
    def __init__(self, generator) -> None:
        self._generator = generator

    async def __aiter__(self):
        async for chunk in self._generator:
            yield chunk


class TestNonHtmlResponse:
    async def test_non_html_response_rejected(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"{}", headers={"content-type": "application/json"})

        fetcher = _make_fetcher(handler)
        with pytest.raises(InvalidContentTypeError):
            await fetcher.fetch_page(PageFetchRequest(url="https://good.test/"))

    async def test_text_plain_allowed_when_expected(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"hello", headers={"content-type": "text/plain"})

        fetcher = _make_fetcher(handler)
        result = await fetcher.fetch_page(
            PageFetchRequest(url="https://good.test/robots.txt", expected_content_type="text/plain")
        )
        assert result.status_code == 200

    async def test_missing_content_type_is_tolerated(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"<html></html>")

        fetcher = _make_fetcher(handler)
        result = await fetcher.fetch_page(PageFetchRequest(url="https://good.test/"))
        assert result.status_code == 200

    async def test_error_status_response_is_exempt_from_content_type_check(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, content=b"{}", headers={"content-type": "application/json"})

        fetcher = _make_fetcher(handler)
        result = await fetcher.fetch_page(PageFetchRequest(url="https://good.test/missing"))
        assert result.status_code == 404


class TestTimeout:
    async def test_timeout_raises_typed_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("simulated timeout", request=request)

        fetcher = _make_fetcher(handler, config=CrawlConfig(max_attempts=1))
        with pytest.raises(TimeoutFetchError):
            await fetcher.fetch_page(PageFetchRequest(url="https://good.test/"))


class TestTransientRetry:
    async def test_transient_503_then_success(self) -> None:
        attempts = 0
        recorded_delays: list[float] = []

        async def recording_sleep(delay: float) -> None:
            recorded_delays.append(delay)

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                return httpx.Response(503, headers={"content-type": "text/html"})
            return _html()

        fetcher = _make_fetcher(handler, config=CrawlConfig(max_attempts=3), sleep=recording_sleep)
        result = await fetcher.fetch_page(PageFetchRequest(url="https://good.test/"))

        assert result.status_code == 200
        assert attempts == 3
        assert len(recorded_delays) == 2

    async def test_non_transient_404_not_retried(self) -> None:
        attempts = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            return httpx.Response(404, headers={"content-type": "text/html"})

        fetcher = _make_fetcher(handler, config=CrawlConfig(max_attempts=3))
        result = await fetcher.fetch_page(PageFetchRequest(url="https://good.test/"))

        assert result.status_code == 404
        assert attempts == 1


class TestRetryAfterHonored:
    async def test_retry_after_capped(self) -> None:
        attempts = 0
        recorded_delays: list[float] = []

        async def recording_sleep(delay: float) -> None:
            recorded_delays.append(delay)

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return httpx.Response(
                    429, headers={"content-type": "text/html", "retry-after": "120"}
                )
            return _html()

        fetcher = _make_fetcher(
            handler,
            config=CrawlConfig(max_attempts=2, max_retry_after_s=60.0),
            sleep=recording_sleep,
        )
        result = await fetcher.fetch_page(PageFetchRequest(url="https://good.test/"))

        assert result.status_code == 200
        assert recorded_delays == [60.0]


class TestConditionalRequests:
    async def test_etag_sent_and_304_maps_to_not_modified(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers.get("if-none-match") == '"abc123"'
            return httpx.Response(304, headers={"etag": '"abc123"'})

        fetcher = _make_fetcher(handler)
        result = await fetcher.fetch_page(
            PageFetchRequest(url="https://good.test/", previous_etag='"abc123"')
        )

        assert result.outcome == "not_modified"
        assert result.body is None

    async def test_last_modified_sent_and_304_maps_to_not_modified(self) -> None:
        last_modified = "Wed, 21 Oct 2015 07:28:00 GMT"

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers.get("if-modified-since") == last_modified
            return httpx.Response(304)

        fetcher = _make_fetcher(handler)
        result = await fetcher.fetch_page(
            PageFetchRequest(url="https://good.test/", previous_last_modified=last_modified)
        )

        assert result.outcome == "not_modified"
        assert result.body is None


class TestNoCookiesOrAuthHeaders:
    async def test_never_sends_authorization_or_cookie(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert "authorization" not in request.headers
            assert "cookie" not in request.headers
            return _html()

        fetcher = _make_fetcher(handler)
        await fetcher.fetch_page(PageFetchRequest(url="https://good.test/"))

    async def test_never_advertises_brotli(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers.get("accept-encoding") == "gzip"
            return _html()

        fetcher = _make_fetcher(handler)
        await fetcher.fetch_page(PageFetchRequest(url="https://good.test/"))


class TestResponseHeaderAllowlist:
    async def test_only_allowlisted_headers_are_retained(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _html(extra_headers={"x-secret-token": "shh", "server": "nginx"})

        fetcher = _make_fetcher(handler)
        result = await fetcher.fetch_page(PageFetchRequest(url="https://good.test/"))

        assert "x-secret-token" not in result.http_metadata.response_headers_allowlist
        assert result.http_metadata.response_headers_allowlist.get("server") == "nginx"
