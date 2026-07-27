"""MongoDB implementation of the companies-module repository contract.

All Motor/MongoDB access for this module is confined to this file. Uses
its own `companies_pipeline` collection, distinct from the paste-in
importer's `companies` collection (`app/domains/companies/repository.py`)
— the two features model different, incompatible shapes of "company", so
sharing a collection would corrupt either feature's unique index.
"""

from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.modules.companies.domain.enums import ProcessingStatus, WorkflowStatus
from app.modules.companies.domain.exceptions import DuplicateCompanyError
from app.modules.companies.domain.models import Company
from app.modules.companies.domain.repository import CompanyPage, CompanyRepository

COLLECTION_NAME = "companies_pipeline"


def _to_document(company: Company) -> dict:
    document = company.model_dump(mode="python")
    document["processing"]["status"] = company.processing.status.value
    document["workflow"]["manual_status"] = company.workflow.manual_status.value
    return document


def _from_document(document: dict) -> Company:
    document = dict(document)
    document.pop("_id", None)
    return Company.model_validate(document)


class MongoCompanyRepository(CompanyRepository):
    """Motor-backed implementation of `CompanyRepository`."""

    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        self._collection: AsyncIOMotorCollection = database[COLLECTION_NAME]

    async def ensure_indexes(self) -> None:
        await self._collection.create_index("normalized_domain", unique=True)
        await self._collection.create_index("processing.status")
        await self._collection.create_index("workflow.manual_status")
        await self._collection.create_index("identity.platform")
        await self._collection.create_index("identity.country")

    async def create(self, company: Company) -> Company:
        try:
            await self._collection.insert_one(_to_document(company))
        except DuplicateKeyError as error:
            raise DuplicateCompanyError(company.normalized_domain) from error
        return company

    async def update(self, company_id: str, company: Company) -> Company | None:
        document = _to_document(company)
        document["updated_at"] = datetime.now(UTC)
        result = await self._collection.find_one_and_update(
            {"company_id": company_id},
            {"$set": document},
            return_document=ReturnDocument.AFTER,
        )
        return _from_document(result) if result is not None else None

    async def get_by_id(self, company_id: str) -> Company | None:
        document = await self._collection.find_one({"company_id": company_id})
        return _from_document(document) if document is not None else None

    async def get_by_normalized_domain(self, normalized_domain: str) -> Company | None:
        document = await self._collection.find_one({"normalized_domain": normalized_domain})
        return _from_document(document) if document is not None else None

    async def exists_by_normalized_domain(self, normalized_domain: str) -> bool:
        count = await self._collection.count_documents(
            {"normalized_domain": normalized_domain}, limit=1
        )
        return count > 0

    async def list_companies(
        self,
        *,
        processing_status: ProcessingStatus | None = None,
        workflow_status: WorkflowStatus | None = None,
        platform: str | None = None,
        country: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> CompanyPage:
        query: dict = {}
        if processing_status is not None:
            query["processing.status"] = processing_status.value
        if workflow_status is not None:
            query["workflow.manual_status"] = workflow_status.value
        if platform is not None:
            query["identity.platform"] = platform
        if country is not None:
            query["identity.country"] = country

        total = await self._collection.count_documents(query)
        skip = (page - 1) * page_size
        cursor = self._collection.find(query).skip(skip).limit(page_size)
        items = [_from_document(document) async for document in cursor]
        return CompanyPage(items=items, total=total)

    async def update_processing_status(
        self, company_id: str, status: ProcessingStatus
    ) -> Company | None:
        result = await self._collection.find_one_and_update(
            {"company_id": company_id},
            {
                "$set": {
                    "processing.status": status.value,
                    "updated_at": datetime.now(UTC),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return _from_document(result) if result is not None else None

    async def update_workflow_status(
        self, company_id: str, status: WorkflowStatus
    ) -> Company | None:
        updates: dict = {
            "workflow.manual_status": status.value,
            "updated_at": datetime.now(UTC),
        }
        if status == WorkflowStatus.SHORTLISTED:
            updates["workflow.shortlisted"] = True
        result = await self._collection.find_one_and_update(
            {"company_id": company_id},
            {"$set": updates},
            return_document=ReturnDocument.AFTER,
        )
        return _from_document(result) if result is not None else None

    async def update_latest_discovery_run_id(
        self, company_id: str, discovery_run_id: str
    ) -> Company | None:
        result = await self._collection.find_one_and_update(
            {"company_id": company_id},
            {
                "$set": {
                    "processing.latest_discovery_run_id": discovery_run_id,
                    "updated_at": datetime.now(UTC),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return _from_document(result) if result is not None else None
