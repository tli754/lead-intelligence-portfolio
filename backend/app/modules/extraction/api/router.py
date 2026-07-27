"""HTTP routes for the extraction module.

Built but **not** centrally registered in `backend/app/main.py` — a
required, out-of-allowed-paths integration step, mirroring
`modules/imports`/`modules/discovery`/`modules/crawling`'s already-
unregistered routers. `POST .../extraction-runs` runs
`StructuredExtractionService.start_extraction_run` synchronously inline —
no `BackgroundTasks`, matching every prior module's identical constraint.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db import get_database
from app.modules.companies.api.router import get_company_service
from app.modules.companies.application.service import CompanyService
from app.modules.crawling.api.router import get_content_storage, get_crawl_repository
from app.modules.crawling.domain.content_storage import ContentStorage
from app.modules.crawling.domain.repository import CrawlRepository
from app.modules.evidence.api.router import get_evidence_service
from app.modules.evidence.api.schemas import evidence_to_response
from app.modules.evidence.application.evidence_service import EvidenceService
from app.modules.evidence.domain.enums import EvidenceStatus, EvidenceStrength, EvidenceType
from app.modules.extraction.api.schemas import (
    CreateExtractionRunRequest,
    ExtractionRunEnvelope,
    FactCandidateListResponse,
    FactEnvelope,
    FactListResponse,
    PaginationMeta,
    candidate_to_response,
    fact_to_response,
    run_to_response,
)
from app.modules.extraction.application.structured_extraction_service import (
    StructuredExtractionService,
)
from app.modules.extraction.domain.enums import FactStatus, VerificationState
from app.modules.extraction.domain.exceptions import (
    CompanyNotFoundForExtractionError,
    CrawlRunNotFoundForExtractionError,
    DuplicateActiveExtractionRunError,
    ExtractionRunNotFoundError,
    FactNotFoundError,
)
from app.modules.extraction.domain.extractor import Extractor
from app.modules.extraction.domain.extractors.business.brands_extractor import BrandsExtractor
from app.modules.extraction.domain.extractors.business.business_model_extractor import (
    BusinessModelExtractor,
)
from app.modules.extraction.domain.extractors.catalogue.catalogue_extractor import (
    CatalogueExtractor,
)
from app.modules.extraction.domain.extractors.growth.growth_extractor import GrowthSignalExtractor
from app.modules.extraction.domain.extractors.identity.company_name_extractor import (
    CompanyNameExtractor,
)
from app.modules.extraction.domain.extractors.identity.country_city_extractor import (
    CountryCityExtractor,
)
from app.modules.extraction.domain.extractors.identity.language_extractor import LanguageExtractor
from app.modules.extraction.domain.extractors.identity.trading_name_extractor import (
    TradingNameExtractor,
)
from app.modules.extraction.domain.extractors.operations.operations_extractor import (
    OperationsExtractor,
)
from app.modules.extraction.domain.extractors.organisation.organisation_extractor import (
    OrganisationExtractor,
)
from app.modules.extraction.domain.extractors.technology.technology_extractor import (
    TechnologyExtractor,
)
from app.modules.extraction.domain.field_catalogue import FieldPath
from app.modules.extraction.domain.gateway import (
    CompanyExtractionGateway,
    CrawlExtractionGateway,
    EvidenceGateway,
)
from app.modules.extraction.domain.repository import ExtractionRepository
from app.modules.extraction.infrastructure.company_service_gateway import (
    CompanyServiceExtractionGateway,
)
from app.modules.extraction.infrastructure.crawl_repository_gateway import (
    CrawlRepositoryExtractionGateway,
)
from app.modules.extraction.infrastructure.evidence_service_gateway import (
    EvidenceServiceExtractionGateway,
)
from app.modules.extraction.infrastructure.mongo_extraction_repository import (
    MongoExtractionRepository,
)

router = APIRouter(tags=["extraction"])


def get_extraction_repository(
    database: AsyncIOMotorDatabase = Depends(get_database),
) -> ExtractionRepository:
    return MongoExtractionRepository(database)


def get_company_extraction_gateway(
    company_service: CompanyService = Depends(get_company_service),
) -> CompanyExtractionGateway:
    return CompanyServiceExtractionGateway(company_service)


def get_crawl_extraction_gateway(
    crawl_repository: CrawlRepository = Depends(get_crawl_repository),
    content_storage: ContentStorage = Depends(get_content_storage),
) -> CrawlExtractionGateway:
    return CrawlRepositoryExtractionGateway(crawl_repository, content_storage)


def get_evidence_extraction_gateway(
    evidence_service: EvidenceService = Depends(get_evidence_service),
) -> EvidenceGateway:
    return EvidenceServiceExtractionGateway(evidence_service)


def get_registered_extractors() -> list[Extractor]:
    return [
        CompanyNameExtractor(),
        TradingNameExtractor(),
        CountryCityExtractor(),
        LanguageExtractor(),
        BusinessModelExtractor(),
        BrandsExtractor(),
        OrganisationExtractor(),
        OperationsExtractor(),
        TechnologyExtractor(),
        CatalogueExtractor(),
        GrowthSignalExtractor(),
    ]


def get_extraction_service(
    company_gateway: CompanyExtractionGateway = Depends(get_company_extraction_gateway),
    crawl_gateway: CrawlExtractionGateway = Depends(get_crawl_extraction_gateway),
    evidence_gateway: EvidenceGateway = Depends(get_evidence_extraction_gateway),
    repository: ExtractionRepository = Depends(get_extraction_repository),
) -> StructuredExtractionService:
    return StructuredExtractionService(
        company_gateway=company_gateway,
        crawl_gateway=crawl_gateway,
        evidence_gateway=evidence_gateway,
        repository=repository,
        extractors=get_registered_extractors(),
    )


@router.post(
    "/api/companies/{company_id}/extraction-runs",
    response_model=ExtractionRunEnvelope,
    status_code=status.HTTP_201_CREATED,
)
async def create_extraction_run(
    company_id: str,
    request: CreateExtractionRunRequest,
    service: StructuredExtractionService = Depends(get_extraction_service),
) -> ExtractionRunEnvelope:
    options = request.options.to_domain() if request.options else None
    try:
        run = await service.start_extraction_run(company_id, request.crawl_run_id, options)
    except CompanyNotFoundForExtractionError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except CrawlRunNotFoundForExtractionError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except DuplicateActiveExtractionRunError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": str(error),
                "extractionRunId": error.existing_extraction_run_id,
                "status": error.status,
            },
        ) from error
    return ExtractionRunEnvelope(data=run_to_response(run))


@router.get(
    "/api/companies/{company_id}/extraction-runs/latest", response_model=ExtractionRunEnvelope
)
async def get_latest_extraction_run(
    company_id: str,
    repository: ExtractionRepository = Depends(get_extraction_repository),
) -> ExtractionRunEnvelope:
    result = await repository.list_runs_by_company(company_id, page=1, page_size=1)
    if not result.items:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no extraction run found for company_id={company_id!r}",
        )
    return ExtractionRunEnvelope(data=run_to_response(result.items[0]))


@router.get("/api/extraction-runs/{extraction_run_id}", response_model=ExtractionRunEnvelope)
async def get_extraction_run(
    extraction_run_id: str,
    repository: ExtractionRepository = Depends(get_extraction_repository),
) -> ExtractionRunEnvelope:
    run = await repository.get_run(extraction_run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(ExtractionRunNotFoundError(extraction_run_id)),
        )
    return ExtractionRunEnvelope(data=run_to_response(run))


@router.get("/api/extraction-runs/{extraction_run_id}/facts", response_model=FactListResponse)
async def list_run_facts(
    extraction_run_id: str,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=200)] = 20,
    repository: ExtractionRepository = Depends(get_extraction_repository),
) -> FactListResponse:
    facts = await repository.list_facts_by_run(extraction_run_id)
    start = (page - 1) * page_size
    page_items = facts[start : start + page_size]
    return FactListResponse(
        data=[fact_to_response(fact) for fact in page_items],
        pagination=PaginationMeta(page=page, page_size=page_size, total=len(facts)),
    )


@router.get(
    "/api/extraction-runs/{extraction_run_id}/candidates", response_model=FactCandidateListResponse
)
async def list_run_candidates(
    extraction_run_id: str,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=200)] = 20,
    field_path: Annotated[FieldPath | None, Query(alias="fieldPath")] = None,
    repository: ExtractionRepository = Depends(get_extraction_repository),
) -> FactCandidateListResponse:
    result = await repository.list_candidates_by_run(
        extraction_run_id, field_path=field_path, page=page, page_size=page_size
    )
    return FactCandidateListResponse(
        data=[candidate_to_response(candidate) for candidate in result.items],
        pagination=PaginationMeta(page=page, page_size=page_size, total=result.total),
    )


@router.get("/api/companies/{company_id}/facts", response_model=FactListResponse)
async def list_company_facts(
    company_id: str,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=200)] = 20,
    field_path: Annotated[FieldPath | None, Query(alias="fieldPath")] = None,
    fact_status: Annotated[FactStatus | None, Query(alias="status")] = None,
    verification_state: Annotated[
        VerificationState | None, Query(alias="verificationState")
    ] = None,
    minimum_confidence: Annotated[
        int | None, Query(alias="minimumConfidence", ge=0, le=100)
    ] = None,
    include_stale: Annotated[bool, Query(alias="includeStale")] = False,
    include_conflicting: Annotated[bool, Query(alias="includeConflicting")] = True,
    repository: ExtractionRepository = Depends(get_extraction_repository),
) -> FactListResponse:
    result = await repository.list_facts_by_company(
        company_id,
        field_path=field_path,
        status=fact_status,
        verification_state=verification_state,
        minimum_confidence=minimum_confidence,
        include_stale=include_stale,
        include_conflicting=include_conflicting,
        page=page,
        page_size=page_size,
    )
    return FactListResponse(
        data=[fact_to_response(fact) for fact in result.items],
        pagination=PaginationMeta(page=page, page_size=page_size, total=result.total),
    )


@router.get("/api/facts/{fact_id}", response_model=FactEnvelope)
async def get_fact(
    fact_id: str,
    repository: ExtractionRepository = Depends(get_extraction_repository),
) -> FactEnvelope:
    fact = await repository.get_fact(fact_id)
    if fact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(FactNotFoundError(fact_id))
        )
    return FactEnvelope(data=fact_to_response(fact))


@router.get("/api/facts/{fact_id}/evidence")
async def get_fact_evidence(
    fact_id: str,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=200)] = 20,
    evidence_type: Annotated[str | None, Query(alias="evidenceType")] = None,
    strength: Annotated[str | None, Query(alias="strength")] = None,
    evidence_status: Annotated[str | None, Query(alias="status")] = None,
    page_id: Annotated[str | None, Query(alias="pageId")] = None,
    field_path: Annotated[str | None, Query(alias="fieldPath")] = None,
    repository: ExtractionRepository = Depends(get_extraction_repository),
    evidence_service: EvidenceService = Depends(get_evidence_service),
):
    fact = await repository.get_fact(fact_id)
    if fact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(FactNotFoundError(fact_id))
        )
    records = await evidence_service.list_evidence_for_fact(fact.evidence_ids)

    if evidence_type is not None:
        records = [
            record for record in records if record.evidence_type == EvidenceType(evidence_type)
        ]
    if strength is not None:
        records = [record for record in records if record.strength == EvidenceStrength(strength)]
    if evidence_status is not None:
        records = [record for record in records if record.status == EvidenceStatus(evidence_status)]
    if page_id is not None:
        records = [record for record in records if record.page_id == page_id]
    if field_path is not None:
        records = [record for record in records if record.fact_field_path == field_path]

    start = (page - 1) * page_size
    page_items = records[start : start + page_size]
    return {
        "data": [evidence_to_response(record).model_dump(by_alias=True) for record in page_items],
        "pagination": {"page": page, "pageSize": page_size, "total": len(records)},
    }
