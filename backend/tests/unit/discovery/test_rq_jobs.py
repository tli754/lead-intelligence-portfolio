"""Tests for `backend/app/modules/discovery/infrastructure/rq_jobs.py`'s
`_build_service` composition (Task 020 / AC-06). No real Redis, no real
MongoDB — `get_database` is monkeypatched to a stub double that only
needs to support `__getitem__` (`MongoDiscoveryRepository.__init__` does
nothing more than store `database[collection_name]`; no connection is
ever attempted at construction time). This is a smoke test of the
composition only, not `asyncio.run`'s actual execution path against real
network I/O — that is already covered by the existing fakes-based
service suite (`test_discovery_service.py`, per AC-03/AC-04/AC-05).
"""

from app.modules.discovery.application.website_discovery_service import WebsiteDiscoveryService
from app.modules.discovery.infrastructure import rq_jobs
from app.modules.discovery.infrastructure.company_service_gateway import (
    CompanyServiceDiscoveryGateway,
)
from app.modules.discovery.infrastructure.httpx_discovery_client import HttpxDiscoveryClient
from app.modules.discovery.infrastructure.mongo_discovery_repository import MongoDiscoveryRepository


class _StubCollection:
    """A placeholder object standing in for an `AsyncIOMotorCollection` —
    never called during `_build_service`, only stored for later use."""


class _StubDatabase:
    """A placeholder standing in for an `AsyncIOMotorDatabase` — supports
    only the `__getitem__` `MongoDiscoveryRepository.__init__` needs."""

    def __getitem__(self, name: str) -> _StubCollection:
        return _StubCollection()


def test_build_service_composes_real_adapters(monkeypatch) -> None:
    monkeypatch.setattr(rq_jobs, "get_database", lambda: _StubDatabase())

    service = rq_jobs._build_service()

    assert isinstance(service, WebsiteDiscoveryService)
    assert isinstance(service._company_gateway, CompanyServiceDiscoveryGateway)
    assert isinstance(service._repository, MongoDiscoveryRepository)
    assert isinstance(service._http_client, HttpxDiscoveryClient)
