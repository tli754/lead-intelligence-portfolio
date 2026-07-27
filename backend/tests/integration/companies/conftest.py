"""Shared helpers for the companies-module integration tests.

Uses the `client`/`test_database` fixtures already defined in
`backend/tests/conftest.py` (real MongoDB, dedicated test database).
"""

from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient

CreateCompany = Callable[..., Awaitable[dict]]


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
