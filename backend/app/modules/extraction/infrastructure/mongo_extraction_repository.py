"""MongoDB implementation of the extraction-module repository contract.

All Motor/MongoDB access for this module is confined to this file. Five
collections: `extraction_runs`, `extractor_executions`, `fact_candidates`,
`facts`, `fact_conflicts`. No raw page HTML is ever stored in any of them
— only `FactValue`/candidate metadata/`evidence_ids` references.

**`facts` storage model, documented in full (contract T24's addition):**
each `(company_id, field_path)` pair has at most one *current* document
(`status in ("accepted", "conflicting")`), enforced by a partial unique
index. `save_facts` upserts against that filter: if the current slot
still matches (an idempotent retry producing the identical outcome), the
same document is overwritten in place — no duplicate, satisfying AC-34.
If the slot's status was already flipped away from accepted/conflicting
by `mark_previous_facts_stale` (a real supersession happened), the filter
no longer matches, so a **new** document is inserted instead — the old,
now-`stale`/`superseded` document is preserved as history, never deleted
or overwritten, satisfying AC-35 and brief section 18's "stale facts are
not deleted."
"""

from enum import Enum
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.modules.extraction.domain.enums import FactStatus, VerificationState
from app.modules.extraction.domain.field_catalogue import FieldPath
from app.modules.extraction.domain.models import (
    ExtractionRun,
    ExtractorExecution,
    FactCandidate,
    FactConflict,
    FactRecord,
)
from app.modules.extraction.domain.repository import (
    CandidatePage,
    ExtractionRepository,
    ExtractionRunPage,
    FactPage,
)

RUNS_COLLECTION_NAME = "extraction_runs"
EXECUTIONS_COLLECTION_NAME = "extractor_executions"
CANDIDATES_COLLECTION_NAME = "fact_candidates"
FACTS_COLLECTION_NAME = "facts"
CONFLICTS_COLLECTION_NAME = "fact_conflicts"

_CURRENT_FACT_STATUSES = ("accepted", "conflicting")
_ACTIVE_RUN_STATUSES = (
    "queued",
    "running",
    "completed",
    "completed_with_warnings",
    "partial",
)


def _stringify_enums(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _stringify_enums(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_stringify_enums(item) for item in value]
    return value


def _strip_id(document: dict) -> dict:
    document = dict(document)
    document.pop("_id", None)
    return document


class MongoExtractionRepository(ExtractionRepository):
    """Motor-backed implementation of `ExtractionRepository`."""

    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        self._runs: AsyncIOMotorCollection = database[RUNS_COLLECTION_NAME]
        self._executions: AsyncIOMotorCollection = database[EXECUTIONS_COLLECTION_NAME]
        self._candidates: AsyncIOMotorCollection = database[CANDIDATES_COLLECTION_NAME]
        self._facts: AsyncIOMotorCollection = database[FACTS_COLLECTION_NAME]
        self._conflicts: AsyncIOMotorCollection = database[CONFLICTS_COLLECTION_NAME]

    async def ensure_indexes(self) -> None:
        await self._runs.create_index("extraction_run_id", unique=True)
        await self._runs.create_index("company_id")
        await self._runs.create_index("crawl_run_id")
        await self._runs.create_index("status")
        await self._runs.create_index("started_at")

        await self._executions.create_index("extractor_execution_id", unique=True)
        await self._executions.create_index("extraction_run_id")
        await self._executions.create_index("page_id")
        await self._executions.create_index("extractor_id")
        await self._executions.create_index("status")

        await self._candidates.create_index("candidate_id", unique=True)
        await self._candidates.create_index("company_id")
        await self._candidates.create_index("extraction_run_id")
        await self._candidates.create_index("field_path")
        await self._candidates.create_index("page_id")
        # Section 22 also lists a `status` index on `fact_candidates`, but
        # `FactCandidate` (brief section 1's own literal field list) has
        # no `status` field — only `verification_state`. Indexed here
        # instead, the closest real field to what that entry meant.
        await self._candidates.create_index("verification_state")

        await self._facts.create_index("fact_id", unique=True)
        await self._facts.create_index("company_id")
        await self._facts.create_index("field_path")
        await self._facts.create_index("status")
        await self._facts.create_index("last_verified_at")
        await self._facts.create_index([("company_id", 1), ("field_path", 1), ("status", 1)])
        # Documented addition (contract T24): makes `save_facts` an
        # upsert-per-current-slot — see this module's own docstring.
        await self._facts.create_index(
            [("company_id", 1), ("field_path", 1)],
            unique=True,
            partialFilterExpression={"status": {"$in": list(_CURRENT_FACT_STATUSES)}},
        )

        await self._conflicts.create_index("conflict_id", unique=True)
        await self._conflicts.create_index("company_id")
        await self._conflicts.create_index("extraction_run_id")
        await self._conflicts.create_index("field_path")

    # --- Runs -----------------------------------------------------------

    async def create_run(self, run: ExtractionRun) -> ExtractionRun:
        await self._runs.insert_one(_stringify_enums(run.model_dump(mode="python")))
        return run

    async def update_run(self, run: ExtractionRun) -> ExtractionRun | None:
        current_version = run.document_version
        document = _stringify_enums(run.model_dump(mode="python"))
        document["document_version"] = current_version + 1
        result = await self._runs.find_one_and_update(
            {"extraction_run_id": run.extraction_run_id, "document_version": current_version},
            {"$set": document},
            return_document=ReturnDocument.AFTER,
        )
        return ExtractionRun.model_validate(_strip_id(result)) if result is not None else None

    async def get_run(self, extraction_run_id: str) -> ExtractionRun | None:
        document = await self._runs.find_one({"extraction_run_id": extraction_run_id})
        return ExtractionRun.model_validate(_strip_id(document)) if document is not None else None

    async def list_runs_by_company(
        self, company_id: str, *, page: int = 1, page_size: int = 20
    ) -> ExtractionRunPage:
        query = {"company_id": company_id}
        total = await self._runs.count_documents(query)
        skip = (page - 1) * page_size
        cursor = self._runs.find(query).sort("created_at", -1).skip(skip).limit(page_size)
        items = [ExtractionRun.model_validate(_strip_id(document)) async for document in cursor]
        return ExtractionRunPage(items=items, total=total)

    async def find_active_or_completed_run(
        self, company_id: str, idempotency_key: str
    ) -> ExtractionRun | None:
        document = await self._runs.find_one(
            {
                "company_id": company_id,
                "idempotency_key": idempotency_key,
                "status": {"$in": list(_ACTIVE_RUN_STATUSES)},
            },
            sort=[("created_at", -1)],
        )
        return ExtractionRun.model_validate(_strip_id(document)) if document is not None else None

    async def mark_run_cancelled(self, extraction_run_id: str) -> ExtractionRun | None:
        result = await self._runs.find_one_and_update(
            {"extraction_run_id": extraction_run_id},
            {"$set": {"status": "cancelled"}, "$inc": {"document_version": 1}},
            return_document=ReturnDocument.AFTER,
        )
        return ExtractionRun.model_validate(_strip_id(result)) if result is not None else None

    # --- Extractor executions -------------------------------------------

    async def save_extractor_execution(self, execution: ExtractorExecution) -> ExtractorExecution:
        await self._executions.find_one_and_update(
            {"extractor_execution_id": execution.extractor_execution_id},
            {"$set": _stringify_enums(execution.model_dump(mode="python"))},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return execution

    # --- Candidates -------------------------------------------------------

    async def save_candidates(self, candidates: list[FactCandidate]) -> list[FactCandidate]:
        for candidate in candidates:
            await self._candidates.find_one_and_update(
                {"candidate_id": candidate.candidate_id},
                {"$set": _stringify_enums(candidate.model_dump(mode="python"))},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        return candidates

    async def list_candidates_by_run(
        self,
        extraction_run_id: str,
        *,
        field_path: FieldPath | None = None,
        page_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> CandidatePage:
        query: dict = {"extraction_run_id": extraction_run_id}
        if field_path is not None:
            query["field_path"] = field_path.value
        if page_id is not None:
            query["page_id"] = page_id

        total = await self._candidates.count_documents(query)
        skip = (page - 1) * page_size
        cursor = self._candidates.find(query).sort("created_at", -1).skip(skip).limit(page_size)
        items = [FactCandidate.model_validate(_strip_id(document)) async for document in cursor]
        return CandidatePage(items=items, total=total)

    # --- Facts -----------------------------------------------------------

    async def save_facts(self, facts: list[FactRecord]) -> list[FactRecord]:
        for fact in facts:
            await self._facts.find_one_and_update(
                {
                    "company_id": fact.company_id,
                    "field_path": fact.field_path.value,
                    "status": {"$in": list(_CURRENT_FACT_STATUSES)},
                },
                {"$set": _stringify_enums(fact.model_dump(mode="python"))},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        return facts

    async def get_fact(self, fact_id: str) -> FactRecord | None:
        document = await self._facts.find_one({"fact_id": fact_id})
        return FactRecord.model_validate(_strip_id(document)) if document is not None else None

    async def get_latest_fact(self, company_id: str, field_path: FieldPath) -> FactRecord | None:
        document = await self._facts.find_one(
            {
                "company_id": company_id,
                "field_path": field_path.value,
                "status": {"$in": list(_CURRENT_FACT_STATUSES)},
            }
        )
        return FactRecord.model_validate(_strip_id(document)) if document is not None else None

    async def list_facts_by_run(self, extraction_run_id: str) -> list[FactRecord]:
        cursor = self._facts.find({"extraction_run_id": extraction_run_id}).sort("updated_at", -1)
        return [FactRecord.model_validate(_strip_id(document)) async for document in cursor]

    async def list_facts_by_company(
        self,
        company_id: str,
        *,
        field_path: FieldPath | None = None,
        status: FactStatus | None = None,
        verification_state: VerificationState | None = None,
        minimum_confidence: int | None = None,
        include_stale: bool = False,
        include_conflicting: bool = True,
        page: int = 1,
        page_size: int = 20,
    ) -> FactPage:
        query: dict = {"company_id": company_id}
        if field_path is not None:
            query["field_path"] = field_path.value
        if status is not None:
            query["status"] = status.value
        else:
            excluded_statuses = []
            if not include_stale:
                excluded_statuses.append("stale")
            if not include_conflicting:
                excluded_statuses.append("conflicting")
            if excluded_statuses:
                query["status"] = {"$nin": excluded_statuses}
        if verification_state is not None:
            query["verification_state"] = verification_state.value
        if minimum_confidence is not None:
            query["confidence"] = {"$gte": minimum_confidence}

        total = await self._facts.count_documents(query)
        skip = (page - 1) * page_size
        cursor = self._facts.find(query).sort("updated_at", -1).skip(skip).limit(page_size)
        items = [FactRecord.model_validate(_strip_id(document)) async for document in cursor]
        return FactPage(items=items, total=total)

    async def mark_previous_facts_stale(
        self, company_id: str, field_path: FieldPath, *, exclude_fact_ids: list[str] | None = None
    ) -> int:
        exclude_fact_ids = exclude_fact_ids or []
        result = await self._facts.update_many(
            {
                "company_id": company_id,
                "field_path": field_path.value,
                "status": {"$in": list(_CURRENT_FACT_STATUSES)},
                "fact_id": {"$nin": exclude_fact_ids},
            },
            {"$set": {"status": "stale", "verification_state": "stale"}},
        )
        return result.modified_count

    # --- Conflicts ---------------------------------------------------------

    async def save_conflicts(self, conflicts: list[FactConflict]) -> list[FactConflict]:
        for conflict in conflicts:
            await self._conflicts.find_one_and_update(
                {"conflict_id": conflict.conflict_id},
                {"$set": _stringify_enums(conflict.model_dump(mode="python"))},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        return conflicts
