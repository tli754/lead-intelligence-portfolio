"""RQ job entrypoints for the discovery module. Called by `app.worker`'s
worker process, never by a FastAPI request. Builds the same dependency
composition `api/router.py`'s `get_discovery_service()` assembles for a
request, but manually — RQ workers run outside FastAPI's request-scoped
DI and outside any existing asyncio event loop.
"""

import asyncio

from app.db import get_database
from app.modules.companies.api.router import get_company_service
from app.modules.discovery.api.router import (
    get_company_discovery_gateway,
    get_discovery_repository,
    get_http_discovery_client,
)
from app.modules.discovery.application.website_discovery_service import WebsiteDiscoveryService

# RQ's default job timeout is 180 seconds. Discovery's own worst case —
# up to max_sitemap_files (50) sequential sitemap fetches, each bounded
# by connect_timeout_s (5s) + read_timeout_s (10s) — is already
# ~12.5 minutes before accounting for the homepage/robots fetches; 20
# minutes leaves comfortable margin without being unbounded like
# crawling's "1h". See the feature contract's "Job timeout" section.
DISCOVERY_JOB_TIMEOUT = "20m"


def _build_service() -> WebsiteDiscoveryService:
    database = get_database()
    company_service = get_company_service(database=database)
    return WebsiteDiscoveryService(
        company_gateway=get_company_discovery_gateway(company_service=company_service),
        discovery_repository=get_discovery_repository(database=database),
        http_client=get_http_discovery_client(),
    )


def run_discovery_execution(discovery_run_id: str) -> None:
    asyncio.run(_build_service().execute_discovery_run(discovery_run_id))
