"""RQ job entrypoints for the crawling module. Called by `app.worker`'s
worker process, never by a FastAPI request. Builds the same dependency
composition `api/router.py`'s `get_crawl_service()` assembles for a
request, but manually — RQ workers run outside FastAPI's request-scoped
DI and outside any existing asyncio event loop.
"""

import asyncio

from app.db import get_database
from app.modules.companies.api.router import get_company_service
from app.modules.crawling.api.router import (
    get_company_crawl_gateway,
    get_content_storage,
    get_crawl_repository,
    get_discovery_crawl_gateway,
    get_page_fetcher,
    get_robots_policy_gateway,
)
from app.modules.crawling.application.website_crawl_service import WebsiteCrawlService
from app.modules.crawling.domain.config import CrawlConfig
from app.modules.discovery.api.router import get_discovery_repository

# RQ's default job timeout is 180 seconds — far too short for a
# multi-target crawl run, which the crawling module's own contract
# documents as potentially taking well over that with no fixed upper
# bound on `max_pages_per_company`. See the feature contract's "Job
# timeout" section for the full rationale.
CRAWL_JOB_TIMEOUT = "1h"


def _build_service() -> WebsiteCrawlService:
    database = get_database()
    company_service = get_company_service(database=database)
    discovery_repository = get_discovery_repository(database=database)
    page_fetcher = get_page_fetcher()
    return WebsiteCrawlService(
        company_gateway=get_company_crawl_gateway(company_service=company_service),
        discovery_gateway=get_discovery_crawl_gateway(discovery_repository=discovery_repository),
        robots_gateway=get_robots_policy_gateway(page_fetcher=page_fetcher),
        repository=get_crawl_repository(database=database),
        page_fetcher=page_fetcher,
        content_storage=get_content_storage(),
        config=CrawlConfig(),
    )


def run_crawl_execution(crawl_run_id: str) -> None:
    asyncio.run(_build_service().execute_crawl_run(crawl_run_id))


def run_crawl_retry(crawl_run_id: str) -> None:
    asyncio.run(_build_service().retry_failed(crawl_run_id))
