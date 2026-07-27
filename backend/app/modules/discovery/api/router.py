"""HTTP routes for the discovery module.

Built but **not** centrally registered in `backend/app/main.py`, per the
task's own instruction. The `POST` route runs `WebsiteDiscoveryService`
synchronously inline — the service itself takes no FastAPI types, so a
future worker can call it identically (no `BackgroundTasks` used here).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db import get_database
from app.modules.companies.api.router import get_company_service
from app.modules.companies.application.service import CompanyService
from app.modules.discovery.api.schemas import (
    DiscoveredUrlListResponse,
    DiscoveryRunEnvelope,
    PaginationMeta,
    discovered_url_to_response,
    run_to_response,
)
from app.modules.discovery.application.website_discovery_service import WebsiteDiscoveryService
from app.modules.discovery.domain.enums import DiscoverySource, PageType
from app.modules.discovery.domain.exceptions import (
    CompanyNotFoundForDiscoveryError,
    DiscoveryRunNotFoundError,
)
from app.modules.discovery.domain.gateway import CompanyDiscoveryGateway
from app.modules.discovery.domain.http_client import HttpDiscoveryClient
from app.modules.discovery.domain.repository import DiscoveryRepository
from app.modules.discovery.infrastructure.company_service_gateway import (
    CompanyServiceDiscoveryGateway,
)
from app.modules.discovery.infrastructure.httpx_discovery_client import HttpxDiscoveryClient
from app.modules.discovery.infrastructure.mongo_discovery_repository import MongoDiscoveryRepository

router = APIRouter(tags=["discovery"])


def get_discovery_repository(
    database: AsyncIOMotorDatabase = Depends(get_database),
) -> DiscoveryRepository:
    return MongoDiscoveryRepository(database)


def get_company_discovery_gateway(
    company_service: CompanyService = Depends(get_company_service),
) -> CompanyDiscoveryGateway:
    return CompanyServiceDiscoveryGateway(company_service)


def get_http_discovery_client() -> HttpDiscoveryClient:
    return HttpxDiscoveryClient()


def get_discovery_service(
    company_gateway: CompanyDiscoveryGateway = Depends(get_company_discovery_gateway),
    discovery_repository: DiscoveryRepository = Depends(get_discovery_repository),
    http_client: HttpDiscoveryClient = Depends(get_http_discovery_client),
) -> WebsiteDiscoveryService:
    return WebsiteDiscoveryService(
        company_gateway=company_gateway,
        discovery_repository=discovery_repository,
        http_client=http_client,
    )


@router.post(
    "/api/companies/{company_id}/discovery-runs",
    response_model=DiscoveryRunEnvelope,
    status_code=status.HTTP_201_CREATED,
)
async def create_discovery_run(
    company_id: str,
    service: WebsiteDiscoveryService = Depends(get_discovery_service),
) -> DiscoveryRunEnvelope:
    try:
        run = await service.run_discovery(company_id)
    except CompanyNotFoundForDiscoveryError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return DiscoveryRunEnvelope(data=run_to_response(run))


@router.get(
    "/api/companies/{company_id}/discovery-runs/latest",
    response_model=DiscoveryRunEnvelope,
)
async def get_latest_discovery_run(
    company_id: str,
    repository: DiscoveryRepository = Depends(get_discovery_repository),
) -> DiscoveryRunEnvelope:
    run = await repository.get_latest_run_for_company(company_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no discovery run found for company_id={company_id!r}",
        )
    return DiscoveryRunEnvelope(data=run_to_response(run))


@router.get("/api/discovery-runs/{discovery_run_id}", response_model=DiscoveryRunEnvelope)
async def get_discovery_run(
    discovery_run_id: str,
    repository: DiscoveryRepository = Depends(get_discovery_repository),
) -> DiscoveryRunEnvelope:
    run = await repository.get_run(discovery_run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(DiscoveryRunNotFoundError(discovery_run_id)),
        )
    return DiscoveryRunEnvelope(data=run_to_response(run))


@router.get(
    "/api/discovery-runs/{discovery_run_id}/urls", response_model=DiscoveredUrlListResponse
)
async def list_discovered_urls(
    discovery_run_id: str,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=200)] = 20,
    priority: str | None = None,
    page_type: Annotated[PageType | None, Query(alias="pageType")] = None,
    source: DiscoverySource | None = None,
    include_excluded: Annotated[bool, Query(alias="includeExcluded")] = False,
    repository: DiscoveryRepository = Depends(get_discovery_repository),
) -> DiscoveredUrlListResponse:
    result = await repository.list_discovered_urls(
        discovery_run_id,
        priority=priority,
        page_type=page_type,
        source=source,
        include_excluded=include_excluded,
        page=page,
        page_size=page_size,
    )
    return DiscoveredUrlListResponse(
        data=[discovered_url_to_response(url) for url in result.items],
        pagination=PaginationMeta(page=page, page_size=page_size, total=result.total),
    )
