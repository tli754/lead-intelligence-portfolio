"""HTTP routes for the crawling module.

Registered in `backend/app/main.py` alongside the other pipeline
routers. Since Task 017 (`docs/contracts/active/017-rq-crawling-vertical-
slice.md`), `POST .../crawl-runs` and `POST .../retry-failed` enqueue
work onto the `"crawling"` RQ queue (`app.queue.get_queue`) instead of
running it inline: the route only calls `WebsiteCrawlService.enqueue_crawl_run`/
`enqueue_retry` (fast, no crawl network I/O) and returns a `queued` run
immediately. The actual crawl/retry execution
(`WebsiteCrawlService.execute_crawl_run`/`retry_failed`) runs on a
separate `app.worker` process via the job wrappers in
`infrastructure/rq_jobs.py`. `WebsiteCrawlService.start_crawl_run` is
still available (a thin composed wrapper of the two enqueue/execute
halves) for local development without a running Redis/worker, but the
router no longer calls it.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from rq import Queue
from rq.exceptions import NoSuchJobError
from rq.job import Job

from app.db import get_database
from app.modules.companies.api.router import get_company_service
from app.modules.companies.application.service import CompanyService
from app.modules.crawling.api.schemas import (
    CrawlRunEnvelope,
    CrawlRunListResponse,
    CrawlTargetListResponse,
    CreateCrawlRunRequest,
    PageEnvelope,
    PageListResponse,
    PaginationMeta,
    page_to_response,
    run_to_response,
    target_to_response,
)
from app.modules.crawling.application.website_crawl_service import WebsiteCrawlService
from app.modules.crawling.domain.config import CrawlConfig
from app.modules.crawling.domain.content_storage import ContentStorage
from app.modules.crawling.domain.enums import CrawlStatus, FetchMode, PageFetchStatus
from app.modules.crawling.domain.exceptions import (
    CompanyNotFoundForCrawlError,
    CrawlRunNotFoundError,
    DiscoveryRunNotFoundForCrawlError,
    DuplicateActiveCrawlRunError,
    PageNotFoundError,
)
from app.modules.crawling.domain.gateway import (
    CompanyCrawlGateway,
    DiscoveryCrawlGateway,
    RobotsPolicyGateway,
)
from app.modules.crawling.domain.page_fetcher import PageFetcher
from app.modules.crawling.domain.repository import CrawlRepository
from app.modules.crawling.infrastructure.company_service_gateway import CompanyServiceCrawlGateway
from app.modules.crawling.infrastructure.discovery_repository_gateway import (
    DiscoveryRepositoryCrawlGateway,
)
from app.modules.crawling.infrastructure.http_robots_policy_gateway import HttpRobotsPolicyGateway
from app.modules.crawling.infrastructure.httpx_page_fetcher import HttpxPageFetcher
from app.modules.crawling.infrastructure.local_filesystem_content_storage import (
    LocalFilesystemContentStorage,
)
from app.modules.crawling.infrastructure.mongo_crawl_repository import MongoCrawlRepository
from app.modules.discovery.api.router import get_discovery_repository
from app.modules.discovery.domain.enums import DiscoveryPriority, PageType
from app.modules.discovery.domain.repository import DiscoveryRepository
from app.queue import get_queue, get_redis_connection

logger = logging.getLogger(__name__)

router = APIRouter(tags=["crawling"])


def get_crawl_repository(
    database: AsyncIOMotorDatabase = Depends(get_database),
) -> CrawlRepository:
    return MongoCrawlRepository(database)


def get_company_crawl_gateway(
    company_service: CompanyService = Depends(get_company_service),
) -> CompanyCrawlGateway:
    return CompanyServiceCrawlGateway(company_service)


def get_discovery_crawl_gateway(
    discovery_repository: DiscoveryRepository = Depends(get_discovery_repository),
) -> DiscoveryCrawlGateway:
    return DiscoveryRepositoryCrawlGateway(discovery_repository)


def get_page_fetcher() -> PageFetcher:
    return HttpxPageFetcher()


def get_robots_policy_gateway(
    page_fetcher: PageFetcher = Depends(get_page_fetcher),
) -> RobotsPolicyGateway:
    return HttpRobotsPolicyGateway(page_fetcher)


def get_content_storage() -> ContentStorage:
    return LocalFilesystemContentStorage()


def get_crawl_queue() -> Queue:
    return get_queue("crawling")


def get_crawl_service(
    company_gateway: CompanyCrawlGateway = Depends(get_company_crawl_gateway),
    discovery_gateway: DiscoveryCrawlGateway = Depends(get_discovery_crawl_gateway),
    robots_gateway: RobotsPolicyGateway = Depends(get_robots_policy_gateway),
    repository: CrawlRepository = Depends(get_crawl_repository),
    page_fetcher: PageFetcher = Depends(get_page_fetcher),
    content_storage: ContentStorage = Depends(get_content_storage),
) -> WebsiteCrawlService:
    return WebsiteCrawlService(
        company_gateway=company_gateway,
        discovery_gateway=discovery_gateway,
        robots_gateway=robots_gateway,
        repository=repository,
        page_fetcher=page_fetcher,
        content_storage=content_storage,
        config=CrawlConfig(),
    )


@router.post(
    "/api/companies/{company_id}/crawl-runs",
    response_model=CrawlRunEnvelope,
    status_code=status.HTTP_201_CREATED,
)
async def create_crawl_run(
    company_id: str,
    request: CreateCrawlRunRequest,
    service: WebsiteCrawlService = Depends(get_crawl_service),
    queue: Queue = Depends(get_crawl_queue),
) -> CrawlRunEnvelope:
    # Imported here, not at module top: `rq_jobs.py` imports this
    # module's own `get_*` DI accessors to rebuild the same composition
    # for a worker process, which would otherwise be a circular import.
    from app.modules.crawling.infrastructure.rq_jobs import CRAWL_JOB_TIMEOUT, run_crawl_execution

    try:
        run = await service.enqueue_crawl_run(
            company_id, request.discovery_run_id, request.options_or_default()
        )
    except CompanyNotFoundForCrawlError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except DiscoveryRunNotFoundForCrawlError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except DuplicateActiveCrawlRunError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": str(error),
                "crawlRunId": error.existing_crawl_run_id,
                "status": error.status,
            },
        ) from error
    queue.enqueue_call(
        func=run_crawl_execution,
        args=(run.crawl_run_id,),
        job_id=run.crawl_run_id,
        # RQ's own `Queue.enqueue_call` type stub declares `timeout` as
        # `int | None`, but its runtime implementation
        # (`rq.utils.parse_timeout`) also accepts RQ's documented string
        # duration syntax (e.g. "1h") — a known stub/runtime mismatch in
        # the installed `rq` package, not a real type error here.
        timeout=CRAWL_JOB_TIMEOUT,  # pyright: ignore[reportArgumentType]
    )
    return CrawlRunEnvelope(data=run_to_response(run))


@router.get(
    "/api/companies/{company_id}/crawl-runs/latest",
    response_model=CrawlRunEnvelope,
)
async def get_latest_crawl_run(
    company_id: str,
    repository: CrawlRepository = Depends(get_crawl_repository),
) -> CrawlRunEnvelope:
    result = await repository.list_runs_by_company(company_id, page=1, page_size=1)
    if not result.items:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no crawl run found for company_id={company_id!r}",
        )
    return CrawlRunEnvelope(data=run_to_response(result.items[0]))


@router.get("/api/crawl-runs/{crawl_run_id}", response_model=CrawlRunEnvelope)
async def get_crawl_run(
    crawl_run_id: str,
    repository: CrawlRepository = Depends(get_crawl_repository),
) -> CrawlRunEnvelope:
    run = await repository.get_run(crawl_run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(CrawlRunNotFoundError(crawl_run_id))
        )
    return CrawlRunEnvelope(data=run_to_response(run))


@router.get("/api/crawl-runs", response_model=CrawlRunListResponse)
async def list_crawl_runs(
    status: Annotated[CrawlStatus | None, Query(alias="status")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=200)] = 20,
    repository: CrawlRepository = Depends(get_crawl_repository),
) -> CrawlRunListResponse:
    result = await repository.list_runs(status=status, page=page, page_size=page_size)
    return CrawlRunListResponse(
        data=[run_to_response(run) for run in result.items],
        pagination=PaginationMeta(page=page, page_size=page_size, total=result.total),
    )


@router.get("/api/crawl-runs/{crawl_run_id}/targets", response_model=CrawlTargetListResponse)
async def list_crawl_targets(
    crawl_run_id: str,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=200)] = 20,
    target_status: Annotated[PageFetchStatus | None, Query(alias="status")] = None,
    page_type: Annotated[PageType | None, Query(alias="pageType")] = None,
    priority: Annotated[DiscoveryPriority | None, Query(alias="priority")] = None,
    fetch_mode: Annotated[FetchMode | None, Query(alias="fetchMode")] = None,
    repository: CrawlRepository = Depends(get_crawl_repository),
) -> CrawlTargetListResponse:
    result = await repository.list_targets_by_run(
        crawl_run_id,
        status=target_status,
        page_type=page_type,
        priority=priority,
        fetch_mode=fetch_mode,
        page=page,
        page_size=page_size,
    )
    return CrawlTargetListResponse(
        data=[target_to_response(target) for target in result.items],
        pagination=PaginationMeta(page=page, page_size=page_size, total=result.total),
    )


@router.get("/api/crawl-runs/{crawl_run_id}/pages", response_model=PageListResponse)
async def list_pages(
    crawl_run_id: str,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=200)] = 20,
    page_status: Annotated[PageFetchStatus | None, Query(alias="status")] = None,
    page_type: Annotated[PageType | None, Query(alias="pageType")] = None,
    priority: Annotated[DiscoveryPriority | None, Query(alias="priority")] = None,
    fetch_mode: Annotated[FetchMode | None, Query(alias="fetchMode")] = None,
    browser_required: Annotated[bool | None, Query(alias="browserRequired")] = None,
    include_failed: Annotated[bool, Query(alias="includeFailed")] = False,
    repository: CrawlRepository = Depends(get_crawl_repository),
) -> PageListResponse:
    result = await repository.list_pages_by_run(
        crawl_run_id,
        status=page_status,
        page_type=page_type,
        priority=priority,
        fetch_mode=fetch_mode,
        browser_required=browser_required,
        include_failed=include_failed,
        page=page,
        page_size=page_size,
    )
    return PageListResponse(
        data=[page_to_response(item) for item in result.items],
        pagination=PaginationMeta(page=page, page_size=page_size, total=result.total),
    )


@router.get("/api/pages/{page_id}", response_model=PageEnvelope)
async def get_page(
    page_id: str,
    repository: CrawlRepository = Depends(get_crawl_repository),
) -> PageEnvelope:
    page = await repository.get_page(page_id)
    if page is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(PageNotFoundError(page_id))
        )
    return PageEnvelope(data=page_to_response(page))


@router.post("/api/crawl-runs/{crawl_run_id}/cancel", response_model=CrawlRunEnvelope)
async def cancel_crawl_run(
    crawl_run_id: str,
    service: WebsiteCrawlService = Depends(get_crawl_service),
) -> CrawlRunEnvelope:
    try:
        run = await service.cancel_run(crawl_run_id)
    except CrawlRunNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    # Best-effort: cancel whichever RQ job (if any) is still queued for
    # this run — never blocks or changes the response. RQ can only
    # cleanly cancel a job that hasn't been picked up by a worker yet;
    # once running, `execute_crawl_run`'s own cooperative cancellation
    # check (between targets) is what actually stops it.
    for candidate_job_id in (crawl_run_id, f"{crawl_run_id}-retry"):
        try:
            Job.fetch(candidate_job_id, connection=get_redis_connection()).cancel()
        except NoSuchJobError:
            pass
        except Exception as error:  # any other RQ/Redis failure is logged, never raised
            logger.warning("failed to cancel RQ job %s: %s", candidate_job_id, error)

    return CrawlRunEnvelope(data=run_to_response(run))


@router.post("/api/crawl-runs/{crawl_run_id}/retry-failed", response_model=CrawlRunEnvelope)
async def retry_failed_targets(
    crawl_run_id: str,
    service: WebsiteCrawlService = Depends(get_crawl_service),
    queue: Queue = Depends(get_crawl_queue),
) -> CrawlRunEnvelope:
    # See `create_crawl_run`'s comment on why this import is local, not
    # at module top.
    from app.modules.crawling.infrastructure.rq_jobs import CRAWL_JOB_TIMEOUT, run_crawl_retry

    try:
        run = await service.enqueue_retry(crawl_run_id)
    except CrawlRunNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    queue.enqueue_call(
        func=run_crawl_retry,
        args=(crawl_run_id,),
        job_id=f"{crawl_run_id}-retry",
        # See `create_crawl_run`'s comment on this same pyright ignore.
        timeout=CRAWL_JOB_TIMEOUT,  # pyright: ignore[reportArgumentType]
    )
    return CrawlRunEnvelope(data=run_to_response(run))
