"""MongoDB implementation of the discovery-module repository contract.

All Motor/MongoDB access for this module is confined to this file, same
style as `modules/companies/infrastructure/mongo_repository.py`. Two
collections: `discovery_runs` and `discoveries`. Never stores raw
homepage HTML — only `DiscoveredUrl` metadata; the homepage HTML itself
lives only transiently in a `HomepageResolutionResult` during one run
and is never persisted.

Not wired into any shared DI container or app startup lifespan — that
would require editing `backend/app/main.py`, off-limits to this module.
Flagged as a required integration step (mirrors how `MongoCompanyRepository`
needed `main.py` wiring for its own `ensure_indexes()` call).
"""

from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.modules.discovery.domain.enums import DiscoverySource, DiscoveryStatus, PageType
from app.modules.discovery.domain.models import DiscoveredUrl, DiscoveryRun
from app.modules.discovery.domain.repository import (
    DiscoveredUrlPage,
    DiscoveryRepository,
    DiscoveryRunPage,
)

RUNS_COLLECTION_NAME = "discovery_runs"
URLS_COLLECTION_NAME = "discoveries"


def _run_to_document(run: DiscoveryRun) -> dict:
    return run.model_dump(mode="python")


def _run_from_document(document: dict) -> DiscoveryRun:
    document = dict(document)
    document.pop("_id", None)
    return DiscoveryRun.model_validate(document)


def _url_to_document(url: DiscoveredUrl) -> dict:
    document = url.model_dump(mode="python")
    document["page_type"] = url.page_type.value
    document["priority"] = url.priority.value
    document["discovery_sources"] = [source.value for source in url.discovery_sources]
    return document


def _url_from_document(document: dict) -> DiscoveredUrl:
    document = dict(document)
    document.pop("_id", None)
    return DiscoveredUrl.model_validate(document)


class MongoDiscoveryRepository(DiscoveryRepository):
    """Motor-backed implementation of `DiscoveryRepository`."""

    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        self._runs: AsyncIOMotorCollection = database[RUNS_COLLECTION_NAME]
        self._urls: AsyncIOMotorCollection = database[URLS_COLLECTION_NAME]

    async def ensure_indexes(self) -> None:
        await self._runs.create_index("discovery_run_id", unique=True)
        await self._runs.create_index("company_id")
        await self._runs.create_index("status")
        await self._runs.create_index("started_at")
        await self._runs.create_index("created_at")

        await self._urls.create_index("discovered_url_id", unique=True)
        await self._urls.create_index(
            [("discovery_run_id", 1), ("normalized_url", 1)], unique=True
        )
        await self._urls.create_index("company_id")
        await self._urls.create_index("page_type")
        await self._urls.create_index("priority")
        await self._urls.create_index("normalized_url")

    async def create_run(self, run: DiscoveryRun) -> DiscoveryRun:
        await self._runs.insert_one(_run_to_document(run))
        return run

    async def update_run(self, run: DiscoveryRun) -> DiscoveryRun | None:
        result = await self._runs.find_one_and_update(
            {"discovery_run_id": run.discovery_run_id},
            {"$set": _run_to_document(run)},
            return_document=ReturnDocument.AFTER,
        )
        return _run_from_document(result) if result is not None else None

    async def get_run(self, discovery_run_id: str) -> DiscoveryRun | None:
        document = await self._runs.find_one({"discovery_run_id": discovery_run_id})
        return _run_from_document(document) if document is not None else None

    async def get_latest_run_for_company(self, company_id: str) -> DiscoveryRun | None:
        cursor = (
            self._runs.find({"company_id": company_id})
            .sort("created_at", -1)
            .limit(1)
        )
        async for document in cursor:
            return _run_from_document(document)
        return None

    async def list_runs(
        self,
        *,
        status: DiscoveryStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> DiscoveryRunPage:
        query: dict = {}
        if status is not None:
            query["status"] = status.value

        total = await self._runs.count_documents(query)
        skip = (page - 1) * page_size
        cursor = self._runs.find(query).sort("created_at", -1).skip(skip).limit(page_size)
        items = [_run_from_document(document) async for document in cursor]
        return DiscoveryRunPage(items=items, total=total)

    async def save_discovered_urls(self, urls: list[DiscoveredUrl]) -> list[DiscoveredUrl]:
        if not urls:
            return []
        await self._urls.insert_many([_url_to_document(url) for url in urls])
        return urls

    async def find_existing_url(
        self, discovery_run_id: str, normalized_url: str
    ) -> DiscoveredUrl | None:
        document = await self._urls.find_one(
            {"discovery_run_id": discovery_run_id, "normalized_url": normalized_url}
        )
        return _url_from_document(document) if document is not None else None

    async def list_discovered_urls(
        self,
        discovery_run_id: str,
        *,
        priority: str | None = None,
        page_type: PageType | None = None,
        source: DiscoverySource | None = None,
        include_excluded: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> DiscoveredUrlPage:
        query: dict = {"discovery_run_id": discovery_run_id}
        if priority is not None:
            query["priority"] = priority
        elif not include_excluded:
            query["priority"] = {"$ne": "excluded"}
        if page_type is not None:
            query["page_type"] = page_type.value
        if source is not None:
            query["discovery_sources"] = source.value

        total = await self._urls.count_documents(query)
        skip = (page - 1) * page_size
        cursor = self._urls.find(query).skip(skip).limit(page_size)
        items = [_url_from_document(document) async for document in cursor]
        return DiscoveredUrlPage(items=items, total=total)
