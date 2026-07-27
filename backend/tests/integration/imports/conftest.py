"""Shared fixtures for the imports-module integration tests.

No real MongoDB and no shared `app.main.app` — the imports router is
deliberately not registered there (per the task's own instruction), so
these tests build their own minimal FastAPI app with just this router,
plus a fake Company gateway dependency-injected in. This also means
these tests genuinely cannot touch the companies MongoDB collection even
by accident.
"""

from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.modules.imports.api.router import get_company_import_gateway, router
from app.modules.imports.domain.gateway import CompanyAlreadyExistsError, CompanyImportGateway


class FakeCompanyImportGateway(CompanyImportGateway):
    """In-memory gateway double.

    Unlike the real `CompanyServiceImportGateway`, this one gives a real
    `True`/`False` answer from `exists_by_domain` (never `None`), since it
    has full control over its own storage — that's what lets the preview
    tests exercise `existingCompanies` properly.
    """

    def __init__(
        self,
        *,
        existing_domains: set[str] | None = None,
        fail_domains: set[str] | None = None,
    ) -> None:
        self._domains: set[str] = set(existing_domains or set())
        self._fail_domains: set[str] = set(fail_domains or set())
        self.created: list[dict[str, str | None]] = []

    async def exists_by_domain(self, normalized_domain: str) -> bool:
        return normalized_domain in self._domains

    async def create_imported_company(
        self,
        *,
        normalized_domain: str,
        platform: str | None,
        country: str | None,
        city: str | None,
    ) -> None:
        if normalized_domain in self._fail_domains:
            raise RuntimeError(f"simulated failure for {normalized_domain!r}")
        if normalized_domain in self._domains:
            raise CompanyAlreadyExistsError(normalized_domain)
        self._domains.add(normalized_domain)
        self.created.append(
            {
                "normalized_domain": normalized_domain,
                "platform": platform,
                "country": country,
                "city": city,
            }
        )


def _build_app(gateway: CompanyImportGateway) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_company_import_gateway] = lambda: gateway
    return app


@pytest.fixture
def make_gateway() -> Callable[..., FakeCompanyImportGateway]:
    def _make(
        *,
        existing_domains: set[str] | None = None,
        fail_domains: set[str] | None = None,
    ) -> FakeCompanyImportGateway:
        return FakeCompanyImportGateway(
            existing_domains=existing_domains, fail_domains=fail_domains
        )

    return _make


ClientFactory = Callable[[CompanyImportGateway], AbstractAsyncContextManager[AsyncClient]]


@pytest.fixture
def client_factory() -> ClientFactory:
    @asynccontextmanager
    async def _factory(gateway: CompanyImportGateway) -> AsyncGenerator[AsyncClient, None]:
        transport = ASGITransport(app=_build_app(gateway))
        async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
            yield test_client

    return _factory


@pytest.fixture
def gateway() -> FakeCompanyImportGateway:
    return FakeCompanyImportGateway()


@pytest.fixture
async def client(
    gateway: FakeCompanyImportGateway,
    client_factory: ClientFactory,
) -> AsyncGenerator[AsyncClient, None]:
    async with client_factory(gateway) as test_client:
        yield test_client
