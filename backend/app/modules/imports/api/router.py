"""HTTP routes for the imports module.

Built but deliberately **not** registered in `app.main` (out of this
task's allowed paths, and the task explicitly asks for the router to
exist without being centrally wired up yet).
"""

from fastapi import APIRouter, Depends

from app.modules.companies.api.router import get_company_service
from app.modules.companies.application.service import CompanyService
from app.modules.imports.api.schemas import (
    ImportPreviewResponse,
    ImportResultResponse,
    StoreLeadsImportRequest,
    preview_to_response,
    result_to_response,
)
from app.modules.imports.application.import_service import ImportService
from app.modules.imports.application.preview_service import ImportPreviewService
from app.modules.imports.domain.gateway import CompanyImportGateway
from app.modules.imports.infrastructure.company_service_gateway import CompanyServiceImportGateway

router = APIRouter(prefix="/api/imports/storeleads", tags=["imports"])


def get_company_import_gateway(
    company_service: CompanyService = Depends(get_company_service),
) -> CompanyImportGateway:
    """Wraps the Company module's own `CompanyService` — never MongoDB directly."""
    return CompanyServiceImportGateway(company_service)


def get_import_preview_service(
    gateway: CompanyImportGateway = Depends(get_company_import_gateway),
) -> ImportPreviewService:
    return ImportPreviewService(gateway)


def get_import_service(
    gateway: CompanyImportGateway = Depends(get_company_import_gateway),
) -> ImportService:
    return ImportService(gateway)


@router.post("/preview", response_model=ImportPreviewResponse)
async def preview_storeleads_import(
    request: StoreLeadsImportRequest,
    service: ImportPreviewService = Depends(get_import_preview_service),
) -> ImportPreviewResponse:
    preview = await service.preview_storeleads_html(request.html)
    return preview_to_response(preview)


@router.post("", response_model=ImportResultResponse)
async def run_storeleads_import(
    request: StoreLeadsImportRequest,
    service: ImportService = Depends(get_import_service),
) -> ImportResultResponse:
    result = await service.import_storeleads_html(request.html)
    return result_to_response(result)
