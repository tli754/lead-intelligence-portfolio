"""HTTP routes for the `companies` domain.

Thin by design: no parsing, no dedupe logic, no MongoDB calls here. Every
decision is delegated to `CompanyImportService`.
"""

from fastapi import APIRouter, Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db import get_database
from app.domains.companies.models import ImportRequest, ImportResponse
from app.domains.companies.repository import CompanyRepository
from app.domains.companies.service import CompanyImportService

router = APIRouter(prefix="/api/companies", tags=["companies"])


def get_company_import_service(
    database: AsyncIOMotorDatabase = Depends(get_database),
) -> CompanyImportService:
    """FastAPI dependency assembling a service instance for this request."""
    return CompanyImportService(CompanyRepository(database))


@router.post("/import", response_model=ImportResponse)
async def import_companies(
    request: ImportRequest,
    service: CompanyImportService = Depends(get_company_import_service),
) -> ImportResponse:
    return await service.import_companies(request.raw_text)
