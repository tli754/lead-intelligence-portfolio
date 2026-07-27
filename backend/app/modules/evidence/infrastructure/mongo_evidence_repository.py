"""MongoDB implementation of the evidence-module repository contract.

All Motor/MongoDB access for this module is confined to this file. One
collection: `evidence`. No raw page HTML is ever stored here — only the
capped `EvidenceExcerpt` and small location/metadata fields (brief's
explicit prohibition, section 22).
"""

from enum import Enum
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo import ReturnDocument

from app.modules.evidence.domain.enums import EvidenceStatus, EvidenceStrength, EvidenceType
from app.modules.evidence.domain.models import EvidenceRecord
from app.modules.evidence.domain.repository import EvidencePage, EvidenceRepository

EVIDENCE_COLLECTION_NAME = "evidence"


def _stringify_enums(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _stringify_enums(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_stringify_enums(item) for item in value]
    return value


def _to_document(evidence: EvidenceRecord) -> dict:
    return _stringify_enums(evidence.model_dump(mode="python"))


def _from_document(document: dict) -> EvidenceRecord:
    document = dict(document)
    document.pop("_id", None)
    return EvidenceRecord.model_validate(document)


class MongoEvidenceRepository(EvidenceRepository):
    """Motor-backed implementation of `EvidenceRepository`."""

    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        self._evidence: AsyncIOMotorCollection = database[EVIDENCE_COLLECTION_NAME]

    async def ensure_indexes(self) -> None:
        await self._evidence.create_index("evidence_id", unique=True)
        await self._evidence.create_index("company_id")
        await self._evidence.create_index("extraction_run_id")
        await self._evidence.create_index("page_id")
        await self._evidence.create_index("fact_field_path")
        await self._evidence.create_index("status")
        await self._evidence.create_index("source_url")

    async def save_evidence(self, evidence: EvidenceRecord) -> EvidenceRecord:
        await self._evidence.find_one_and_update(
            {"evidence_id": evidence.evidence_id},
            {"$set": _to_document(evidence)},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return evidence

    async def get_evidence(self, evidence_id: str) -> EvidenceRecord | None:
        document = await self._evidence.find_one({"evidence_id": evidence_id})
        return _from_document(document) if document is not None else None

    async def list_evidence_for_fact(self, evidence_ids: list[str]) -> list[EvidenceRecord]:
        if not evidence_ids:
            return []
        cursor = self._evidence.find({"evidence_id": {"$in": evidence_ids}})
        return [_from_document(document) async for document in cursor]

    async def list_evidence_for_page(self, page_id: str) -> list[EvidenceRecord]:
        cursor = self._evidence.find({"page_id": page_id})
        return [_from_document(document) async for document in cursor]

    async def update_evidence_status(
        self, evidence_id: str, status: EvidenceStatus
    ) -> EvidenceRecord | None:
        result = await self._evidence.find_one_and_update(
            {"evidence_id": evidence_id},
            {"$set": {"status": status.value}},
            return_document=ReturnDocument.AFTER,
        )
        return _from_document(result) if result is not None else None

    async def list_evidence(
        self,
        *,
        evidence_type: EvidenceType | None = None,
        strength: EvidenceStrength | None = None,
        status: EvidenceStatus | None = None,
        page_id: str | None = None,
        fact_field_path: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> EvidencePage:
        query: dict = {}
        if evidence_type is not None:
            query["evidence_type"] = evidence_type.value
        if strength is not None:
            query["strength"] = strength.value
        if status is not None:
            query["status"] = status.value
        if page_id is not None:
            query["page_id"] = page_id
        if fact_field_path is not None:
            query["fact_field_path"] = fact_field_path

        total = await self._evidence.count_documents(query)
        skip = (page - 1) * page_size
        cursor = self._evidence.find(query).skip(skip).limit(page_size)
        items = [_from_document(document) async for document in cursor]
        return EvidencePage(items=items, total=total)
