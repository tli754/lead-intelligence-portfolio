"""Shared helpers for the companies-module integration tests.

Uses the `client`/`test_database` fixtures already defined in
`backend/tests/conftest.py` (real MongoDB, dedicated test database).

`POST /api/companies` now auto-triggers discovery synchronously (Task
015 / ADR 0003), so every test that creates a company would otherwise
make a real `HttpxDiscoveryClient` network call. The autouse
`_stub_discovery_http_client` fixture below overrides
`get_http_discovery_client` with a canned, no-network stub for every
test in this directory.
"""

from collections.abc import Awaitable, Callable, Generator

import pytest
from httpx import AsyncClient

from app.main import app
from app.modules.companies.api.router import get_http_discovery_client
from app.modules.discovery.domain.http_client import (
    FetchResult,
    HomepageResolutionResult,
    HttpDiscoveryClient,
)

CreateCompany = Callable[..., Awaitable[dict]]


class StubHttpDiscoveryClient(HttpDiscoveryClient):
    """Fully canned responses — no real network access.

    Companies-module tests care about company creation, not discovery
    internals (those are covered under `tests/integration/discovery/`);
    this only needs to support the two outcomes `run_discovery` can
    reach via `resolve_homepage`.
    """

    def __init__(self, *, homepage_success: bool = True) -> None:
        self._homepage_success = homepage_success

    async def resolve_homepage(self, candidates: list[str]) -> HomepageResolutionResult:
        if not self._homepage_success:
            return HomepageResolutionResult(
                success=False,
                failure_reason="simulated homepage failure",
                attempted_candidates=candidates,
            )
        return HomepageResolutionResult(
            success=True,
            homepage_url=candidates[0] if candidates else "https://example.com",
            html="<html><body></body></html>",
            attempted_candidates=candidates[:1],
        )

    async def fetch_text(self, url: str) -> FetchResult:
        return FetchResult(status_code=200, content_type="text/plain", body=b"", final_url=url)

    async def fetch_binary(self, url: str) -> FetchResult:
        return FetchResult(
            status_code=200, content_type="application/xml", body=b"", final_url=url
        )

    async def fetch_html(self, url: str) -> FetchResult:
        raise NotImplementedError("not exercised via resolve_homepage-only discovery")


@pytest.fixture(autouse=True)
def _stub_discovery_http_client() -> Generator[None, None, None]:
    app.dependency_overrides[get_http_discovery_client] = lambda: StubHttpDiscoveryClient()
    yield
    app.dependency_overrides.pop(get_http_discovery_client, None)


@pytest.fixture
def create_company() -> CreateCompany:
    """Returns an async helper that POSTs a company and returns its JSON body."""

    async def _create(
        client: AsyncClient,
        domain: str = "example.com",
        *,
        company_name: str | None = None,
        platform: str | None = None,
        country: str | None = None,
        city: str | None = None,
    ) -> dict:
        response = await client.post(
            "/api/companies",
            json={
                "domain": domain,
                "companyName": company_name,
                "platform": platform,
                "country": country,
                "city": city,
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    return _create
