"""HTTP routes for the companies module.

Thin by design: every route validates via Pydantic, calls exactly one
`CompanyService` method, and translates domain errors into HTTP status
codes. No MongoDB calls and no business rules here.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db import get_database
from app.modules.companies.api.schemas import (
    CompanyListResponse,
    CompanyResponse,
    CreateCompanyRequest,
    PaginationMeta,
    UpdateProcessingStatusRequest,
    UpdateWorkflowStatusRequest,
    company_to_list_item,
    company_to_response,
)
from app.modules.companies.application.service import CompanyService
from app.modules.companies.domain.enums import ProcessingStatus, WorkflowStatus
from app.modules.companies.domain.exceptions import (
    CompanyNotFoundError,
    DuplicateCompanyError,
    InvalidStatusTransitionError,
)
from app.modules.companies.infrastructure.mongo_repository import MongoCompanyRepository
from app.modules.discovery.application.website_discovery_service import WebsiteDiscoveryService
from app.modules.discovery.domain.gateway import CompanyDiscoveryGateway
from app.modules.discovery.domain.http_client import HttpDiscoveryClient
from app.modules.discovery.domain.repository import DiscoveryRepository
from app.modules.discovery.infrastructure.company_service_gateway import (
    CompanyServiceDiscoveryGateway,
)
from app.modules.discovery.infrastructure.httpx_discovery_client import HttpxDiscoveryClient
from app.modules.discovery.infrastructure.mongo_discovery_repository import (
    MongoDiscoveryRepository,
)

router = APIRouter(prefix="/api/companies", tags=["companies-module"])


def get_company_service(
    database: AsyncIOMotorDatabase = Depends(get_database),
) -> CompanyService:
    """FastAPI dependency assembling a service instance for this request."""
    return CompanyService(MongoCompanyRepository(database))


# The four dependencies below duplicate `discovery/api/router.py`'s own DI
# chain rather than importing from it: that file already imports
# `get_company_service` from this one, and `main.py` loads this module
# first, so a top-level import the other way would be a circular import.
# None of discovery's application/domain/infrastructure layers import this
# module, so building the graph from those layers directly avoids the
# cycle (see ADR 0003 and the "auto-discovery-trigger" feature contract's
# "Cross-module dependency decisions").


def get_discovery_repository(
    database: AsyncIOMotorDatabase = Depends(get_database),
) -> DiscoveryRepository:
    return MongoDiscoveryRepository(database)


def get_http_discovery_client() -> HttpDiscoveryClient:
    return HttpxDiscoveryClient()


def get_company_discovery_gateway(
    company_service: CompanyService = Depends(get_company_service),
) -> CompanyDiscoveryGateway:
    return CompanyServiceDiscoveryGateway(company_service)


def get_discovery_service_for_company_creation(
    company_gateway: CompanyDiscoveryGateway = Depends(get_company_discovery_gateway),
    discovery_repository: DiscoveryRepository = Depends(get_discovery_repository),
    http_client: HttpDiscoveryClient = Depends(get_http_discovery_client),
) -> WebsiteDiscoveryService:
    return WebsiteDiscoveryService(
        company_gateway=company_gateway,
        discovery_repository=discovery_repository,
        http_client=http_client,
    )


@router.get("", response_model=CompanyListResponse)
async def list_companies(
    processing_status: Annotated[
        ProcessingStatus | None, Query(alias="processingStatus")
    ] = None,
    workflow_status: Annotated[WorkflowStatus | None, Query(alias="workflowStatus")] = None,
    platform: str | None = None,
    country: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=200)] = 20,
    service: CompanyService = Depends(get_company_service),
) -> CompanyListResponse:
    result = await service.list_companies(
        processing_status=processing_status,
        workflow_status=workflow_status,
        platform=platform,
        country=country,
        page=page,
        page_size=page_size,
    )
    return CompanyListResponse(
        data=[company_to_list_item(company) for company in result.items],
        pagination=PaginationMeta(page=page, page_size=page_size, total=result.total),
    )


@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(
    company_id: str,
    service: CompanyService = Depends(get_company_service),
) -> CompanyResponse:
    try:
        company = await service.get_company(company_id)
    except CompanyNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return company_to_response(company)


@router.post("", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
async def create_company(
    request: CreateCompanyRequest,
    service: CompanyService = Depends(get_company_service),
    discovery_service: WebsiteDiscoveryService = Depends(
        get_discovery_service_for_company_creation
    ),
) -> CompanyResponse:
    try:
        company = await service.create_company(
            domain=request.domain,
            company_name=request.company_name,
            platform=request.platform,
            country=request.country,
            city=request.city,
        )
    except DuplicateCompanyError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error

    # Auto-trigger discovery synchronously (ADR 0003) — deliberately no
    # try/except here: `run_discovery` already catches network/robots/
    # sitemap failures internally and records them as a FAILED run, and a
    # `CompanyNotFoundForDiscoveryError` on the id we just created would
    # indicate a genuine data-integrity bug, not a condition to swallow.
    await discovery_service.run_discovery(company.company_id)
    company = await service.get_company(company.company_id)
    return company_to_response(company)


@router.patch("/{company_id}/processing-status", response_model=CompanyResponse)
async def update_processing_status(
    company_id: str,
    request: UpdateProcessingStatusRequest,
    service: CompanyService = Depends(get_company_service),
) -> CompanyResponse:
    try:
        company = await service.change_processing_status(company_id, request.status)
    except CompanyNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except InvalidStatusTransitionError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return company_to_response(company)


@router.patch("/{company_id}/workflow-status", response_model=CompanyResponse)
async def update_workflow_status(
    company_id: str,
    request: UpdateWorkflowStatusRequest,
    service: CompanyService = Depends(get_company_service),
) -> CompanyResponse:
    try:
        company = await service.change_workflow_status(company_id, request.status)
    except CompanyNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except InvalidStatusTransitionError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return company_to_response(company)
