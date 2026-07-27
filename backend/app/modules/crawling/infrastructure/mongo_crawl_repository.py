"""MongoDB implementation of the crawling-module repository contract.

All Motor/MongoDB access for this module is confined to this file. Three
collections: `crawl_runs`, `crawl_targets`, `pages`. Large raw HTML is
never stored here — only `ContentReference`s and inline cleaned-HTML/text
under the configured size threshold (enforced by the application layer
before a `CrawledPage` is ever built).

`update_run`/`update_target` use an optimistic-concurrency filter on
`document_version` (match on the caller's current version, `$set` with
`document_version + 1`) — a stale caller's write is rejected (`None`
returned, no document mutated) rather than silently overwriting a newer
state. `save_target`/`save_page` are plain upserts keyed on
`(crawl_run_id, normalized_url)` — the mechanism satisfying section 16's
"retrying a failed page does not duplicate page records" and "same crawl
run and normalized URL must have one target."
"""

from enum import Enum
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.modules.crawling.domain.enums import FetchMode, PageFetchStatus
from app.modules.crawling.domain.models import CrawledPage, CrawlRun, CrawlTarget
from app.modules.crawling.domain.repository import (
    CrawledPagePage,
    CrawlRepository,
    CrawlRunPage,
    CrawlTargetPage,
)
from app.modules.discovery.domain.enums import DiscoveryPriority, PageType

RUNS_COLLECTION_NAME = "crawl_runs"
TARGETS_COLLECTION_NAME = "crawl_targets"
PAGES_COLLECTION_NAME = "pages"

_ACTIVE_RUN_STATUSES = ("queued", "running")


def _stringify_enums(value: Any) -> Any:
    """Recursively converts every `Enum` member in a nested dict/list
    structure to its plain string `.value` — nested `ContentStorageInfo`/
    `CrawlTarget`/`CrawledPage` structures carry enums several levels
    deep, so a generic walker is used here rather than repeating a
    per-field conversion at every nesting level."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _stringify_enums(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_stringify_enums(item) for item in value]
    return value


def _run_to_document(run: CrawlRun) -> dict:
    return _stringify_enums(run.model_dump(mode="python"))


def _run_from_document(document: dict) -> CrawlRun:
    document = dict(document)
    document.pop("_id", None)
    return CrawlRun.model_validate(document)


def _target_to_document(target: CrawlTarget) -> dict:
    return _stringify_enums(target.model_dump(mode="python"))


def _target_from_document(document: dict) -> CrawlTarget:
    document = dict(document)
    document.pop("_id", None)
    return CrawlTarget.model_validate(document)


def _page_to_document(page: CrawledPage) -> dict:
    return _stringify_enums(page.model_dump(mode="python"))


def _page_from_document(document: dict) -> CrawledPage:
    document = dict(document)
    document.pop("_id", None)
    return CrawledPage.model_validate(document)


class MongoCrawlRepository(CrawlRepository):
    """Motor-backed implementation of `CrawlRepository`."""

    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        self._runs: AsyncIOMotorCollection = database[RUNS_COLLECTION_NAME]
        self._targets: AsyncIOMotorCollection = database[TARGETS_COLLECTION_NAME]
        self._pages: AsyncIOMotorCollection = database[PAGES_COLLECTION_NAME]

    async def ensure_indexes(self) -> None:
        await self._runs.create_index("crawl_run_id", unique=True)
        await self._runs.create_index("company_id")
        await self._runs.create_index("discovery_run_id")
        await self._runs.create_index("status")
        await self._runs.create_index("started_at")

        await self._targets.create_index("crawl_target_id", unique=True)
        await self._targets.create_index([("crawl_run_id", 1), ("normalized_url", 1)], unique=True)
        await self._targets.create_index("company_id")
        await self._targets.create_index("status")
        await self._targets.create_index("priority")

        await self._pages.create_index("page_id", unique=True)
        await self._pages.create_index("company_id")
        await self._pages.create_index("crawl_run_id")
        await self._pages.create_index("normalized_url")
        await self._pages.create_index("fetched_at")
        await self._pages.create_index("page_type")
        await self._pages.create_index("fetch_status")
        await self._pages.create_index(
            [("company_id", 1), ("normalized_url", 1), ("fetched_at", -1)]
        )
        # Documented addition (contract T21): needed to make `save_page`
        # an upsert keyed on this pair.
        await self._pages.create_index([("crawl_run_id", 1), ("normalized_url", 1)], unique=True)

    # --- Runs -----------------------------------------------------------

    async def create_run(self, run: CrawlRun) -> CrawlRun:
        await self._runs.insert_one(_run_to_document(run))
        return run

    async def update_run(self, run: CrawlRun) -> CrawlRun | None:
        current_version = run.document_version
        document = _run_to_document(run)
        document["document_version"] = current_version + 1
        result = await self._runs.find_one_and_update(
            {"crawl_run_id": run.crawl_run_id, "document_version": current_version},
            {"$set": document},
            return_document=ReturnDocument.AFTER,
        )
        return _run_from_document(result) if result is not None else None

    async def get_run(self, crawl_run_id: str) -> CrawlRun | None:
        document = await self._runs.find_one({"crawl_run_id": crawl_run_id})
        return _run_from_document(document) if document is not None else None

    async def list_runs_by_company(
        self, company_id: str, *, page: int = 1, page_size: int = 20
    ) -> CrawlRunPage:
        query = {"company_id": company_id}
        total = await self._runs.count_documents(query)
        skip = (page - 1) * page_size
        cursor = self._runs.find(query).sort("created_at", -1).skip(skip).limit(page_size)
        items = [_run_from_document(document) async for document in cursor]
        return CrawlRunPage(items=items, total=total)

    async def find_active_run(self, company_id: str, idempotency_key: str) -> CrawlRun | None:
        document = await self._runs.find_one(
            {
                "company_id": company_id,
                "idempotency_key": idempotency_key,
                "status": {"$in": list(_ACTIVE_RUN_STATUSES)},
            }
        )
        return _run_from_document(document) if document is not None else None

    async def mark_run_cancelled(self, crawl_run_id: str) -> CrawlRun | None:
        result = await self._runs.find_one_and_update(
            {"crawl_run_id": crawl_run_id},
            {"$set": {"status": "cancelled"}, "$inc": {"document_version": 1}},
            return_document=ReturnDocument.AFTER,
        )
        return _run_from_document(result) if result is not None else None

    # --- Targets ----------------------------------------------------------

    async def save_target(self, target: CrawlTarget) -> CrawlTarget:
        await self._targets.find_one_and_update(
            {"crawl_run_id": target.crawl_run_id, "normalized_url": target.normalized_url},
            {"$set": _target_to_document(target)},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return target

    async def update_target(self, target: CrawlTarget) -> CrawlTarget | None:
        current_version = target.document_version
        document = _target_to_document(target)
        document["document_version"] = current_version + 1
        result = await self._targets.find_one_and_update(
            {"crawl_target_id": target.crawl_target_id, "document_version": current_version},
            {"$set": document},
            return_document=ReturnDocument.AFTER,
        )
        return _target_from_document(result) if result is not None else None

    async def find_target_by_url(
        self, crawl_run_id: str, normalized_url: str
    ) -> CrawlTarget | None:
        document = await self._targets.find_one(
            {"crawl_run_id": crawl_run_id, "normalized_url": normalized_url}
        )
        return _target_from_document(document) if document is not None else None

    async def list_targets_by_run(
        self,
        crawl_run_id: str,
        *,
        status: PageFetchStatus | None = None,
        page_type: PageType | None = None,
        priority: DiscoveryPriority | None = None,
        fetch_mode: FetchMode | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> CrawlTargetPage:
        query: dict = {"crawl_run_id": crawl_run_id}
        if status is not None:
            query["status"] = status.value
        if page_type is not None:
            query["page_type"] = page_type.value
        if priority is not None:
            query["priority"] = priority.value
        if fetch_mode is not None:
            query["fetch_mode"] = fetch_mode.value

        total = await self._targets.count_documents(query)
        skip = (page - 1) * page_size
        cursor = self._targets.find(query).skip(skip).limit(page_size)
        items = [_target_from_document(document) async for document in cursor]
        return CrawlTargetPage(items=items, total=total)

    # --- Pages --------------------------------------------------------------

    async def save_page(self, page: CrawledPage) -> CrawledPage:
        await self._pages.find_one_and_update(
            {"crawl_run_id": page.crawl_run_id, "normalized_url": page.normalized_url},
            {"$set": _page_to_document(page)},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return page

    async def get_page(self, page_id: str) -> CrawledPage | None:
        document = await self._pages.find_one({"page_id": page_id})
        return _page_from_document(document) if document is not None else None

    async def list_pages_by_run(
        self,
        crawl_run_id: str,
        *,
        status: PageFetchStatus | None = None,
        page_type: PageType | None = None,
        priority: DiscoveryPriority | None = None,
        fetch_mode: FetchMode | None = None,
        browser_required: bool | None = None,
        include_failed: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> CrawledPagePage:
        query: dict = {"crawl_run_id": crawl_run_id}
        if status is not None:
            query["fetch_status"] = status.value
        elif not include_failed:
            query["fetch_status"] = {"$ne": PageFetchStatus.FAILED.value}
        if page_type is not None:
            query["page_type"] = page_type.value
        if priority is not None:
            query["priority"] = priority.value
        if fetch_mode is not None:
            query["fetch_mode"] = fetch_mode.value
        if browser_required is True:
            query["browser_fallback_reason"] = {"$ne": None}
        elif browser_required is False:
            query["browser_fallback_reason"] = None

        total = await self._pages.count_documents(query)
        skip = (page - 1) * page_size
        cursor = self._pages.find(query).skip(skip).limit(page_size)
        items = [_page_from_document(document) async for document in cursor]
        return CrawledPagePage(items=items, total=total)

    async def get_latest_page_by_normalized_url(
        self, company_id: str, normalized_url: str
    ) -> CrawledPage | None:
        cursor = (
            self._pages.find({"company_id": company_id, "normalized_url": normalized_url})
            .sort("fetched_at", -1)
            .limit(1)
        )
        async for document in cursor:
            return _page_from_document(document)
        return None
