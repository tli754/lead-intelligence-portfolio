"""MongoDB access for the `companies` collection.

All MongoDB access for this domain is confined to this file. No dedupe
or other business rules live here — that belongs in `service.py`.
"""

from datetime import datetime, time

from motor.motor_asyncio import AsyncIOMotorCollection, AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.domains.companies.models import Company

COLLECTION_NAME = "companies"


def _to_mongo_document(company: Company) -> dict:
    """Convert a `Company` model into a BSON-encodable document.

    BSON has no native `date`-only type, so `source_created_at` (a
    `datetime.date`) is stored as a UTC midnight `datetime` — the
    standard MongoDB representation for date-only values.
    """
    document = company.model_dump(mode="python")
    source_created_at = document["source_created_at"]
    if source_created_at is not None:
        document["source_created_at"] = datetime.combine(source_created_at, time.min)
    return document


class CompanyRepository:
    """Owns all reads/writes against the `companies` collection."""

    def __init__(self, database: AsyncIOMotorDatabase) -> None:
        self._collection: AsyncIOMotorCollection = database[COLLECTION_NAME]

    async def ensure_indexes(self) -> None:
        """Create the unique index on `domain`.

        This is defense-in-depth against race conditions beyond the
        app-level dedupe check performed in `CompanyImportService`.
        """
        await self._collection.create_index("domain", unique=True)

    async def get_existing_domains(self, domains: list[str]) -> set[str]:
        """Return the subset of `domains` that already exist in MongoDB.

        A single batched `$in` query, not one query per domain.
        """
        if not domains:
            return set()
        cursor = self._collection.find({"domain": {"$in": domains}}, {"domain": 1})
        return {document["domain"] async for document in cursor}

    async def insert_many(self, companies: list[Company]) -> list[Company]:
        """Insert each company document, skipping any that lose a duplicate-key race.

        Documents are inserted one at a time (rather than via a single
        bulk call) so that a duplicate-key conflict on one document is
        attributed to that document specifically and does not abort the
        rest of the batch or surface as an unhandled 500 (see AC-11).
        """
        inserted: list[Company] = []
        for company in companies:
            document = _to_mongo_document(company)
            try:
                await self._collection.insert_one(document)
            except DuplicateKeyError:
                continue
            inserted.append(company)
        return inserted
