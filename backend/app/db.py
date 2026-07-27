"""MongoDB connectivity.

Owns the single Motor (async MongoDB) client for the application and
exposes it to routes via a FastAPI dependency. No other module should
construct its own Motor client.
"""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import get_settings

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    """Return the process-wide Motor client, creating it on first use."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = AsyncIOMotorClient(settings.MONGODB_URI)
    return _client


def get_database() -> AsyncIOMotorDatabase:
    """FastAPI dependency returning the configured MongoDB database.

    Tests override this dependency to point at a dedicated test database
    (see backend/tests/conftest.py).
    """
    settings = get_settings()
    return get_client()[settings.MONGODB_DB_NAME]
