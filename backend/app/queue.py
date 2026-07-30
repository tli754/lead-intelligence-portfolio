"""Redis/RQ connectivity.

A small, cross-cutting module, sibling to `config.py`/`db.py`/`main.py` —
not under any `modules/` directory, because ADR 0004
(`docs/decisions/0004-adopt-rq-as-queue-system.md`) frames RQ as a
repository-wide decision. This factory must be reusable by any future
module that adopts RQ without importing across module boundaries,
mirroring how `db.py` is a single, cross-cutting Motor-client factory
every module's own `infrastructure/mongo_*_repository.py` depends on.
"""

from functools import lru_cache

from redis import Redis
from rq import Queue

from app.config import get_settings


@lru_cache
def get_redis_connection() -> Redis:
    """Return the process-wide Redis connection, creating it on first use."""
    settings = get_settings()
    return Redis.from_url(settings.REDIS_URL)


def get_queue(name: str) -> Queue:
    """Return an RQ Queue bound to the shared Redis connection."""
    return Queue(name, connection=get_redis_connection())
