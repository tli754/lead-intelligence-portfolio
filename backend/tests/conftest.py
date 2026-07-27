"""Shared pytest fixtures for backend tests.

Tests run against a real MongoDB instance, but always a dedicated test
database (`<MONGODB_DB_NAME>_test`) so they never touch development data.
"""

from collections.abc import AsyncGenerator, Generator

import pytest
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import get_settings
from app.db import get_database
from app.main import app


@pytest.fixture(scope="session")
def test_db_name() -> str:
    """Name of the dedicated MongoDB database used only by tests."""
    return f"{get_settings().MONGODB_DB_NAME}_test"


@pytest.fixture
def motor_client() -> Generator[AsyncIOMotorClient, None, None]:
    """A Motor client scoped to a single test.

    Motor binds its client to the running asyncio event loop, and
    pytest-asyncio creates a fresh event loop per test function, so the
    client must also be recreated per test (a session-scoped client would
    be bound to an already-closed loop after the first test).
    """
    client = AsyncIOMotorClient(get_settings().MONGODB_URI)
    yield client
    client.close()


@pytest.fixture
def test_database(
    motor_client: AsyncIOMotorClient, test_db_name: str
) -> AsyncIOMotorDatabase:
    """The dedicated test database, distinct from the dev/prod database."""
    return motor_client[test_db_name]


@pytest.fixture(autouse=True)
async def clean_companies_collection(
    test_database: AsyncIOMotorDatabase,
) -> AsyncGenerator[None, None]:
    """Drop the `companies` collection before and after every test."""
    await test_database["companies"].drop()
    yield
    await test_database["companies"].drop()


@pytest.fixture(autouse=True)
async def clean_companies_pipeline_collection(
    test_database: AsyncIOMotorDatabase,
) -> AsyncGenerator[None, None]:
    """Drop the companies-module's `companies_pipeline` collection before and after every test."""
    await test_database["companies_pipeline"].drop()
    yield
    await test_database["companies_pipeline"].drop()


@pytest.fixture
async def client(test_database: AsyncIOMotorDatabase) -> AsyncGenerator[AsyncClient, None]:
    """An async HTTP client wired to the dedicated test database.

    Uses httpx's ASGI transport rather than `fastapi.testclient.TestClient`
    so that requests execute on the *same* asyncio event loop as the other
    async fixtures in this module (`TestClient` runs the app in a separate
    thread with its own event loop, which conflicts with Motor's per-loop
    client binding and causes cross-loop `RuntimeError`s).
    """

    def _get_test_database() -> AsyncIOMotorDatabase:
        return test_database

    app.dependency_overrides[get_database] = _get_test_database
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client
    app.dependency_overrides.clear()
