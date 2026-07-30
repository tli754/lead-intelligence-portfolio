"""FastAPI application entrypoint.

Registers routers and wires up startup hooks (e.g. ensuring MongoDB
indexes exist). Route registration only — no business logic lives here.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import get_database
from app.domains.health.router import router as health_router
from app.domains.queue_stats.router import router as queue_stats_router
from app.modules.companies.api.router import router as companies_module_router
from app.modules.companies.infrastructure.mongo_repository import MongoCompanyRepository
from app.modules.crawling.api.router import router as crawling_router
from app.modules.crawling.infrastructure.mongo_crawl_repository import MongoCrawlRepository
from app.modules.discovery.api.router import router as discovery_router
from app.modules.discovery.infrastructure.mongo_discovery_repository import (
    MongoDiscoveryRepository,
)
from app.modules.evidence.api.router import router as evidence_router
from app.modules.evidence.infrastructure.mongo_evidence_repository import MongoEvidenceRepository
from app.modules.extraction.api.router import router as extraction_router
from app.modules.extraction.infrastructure.mongo_extraction_repository import (
    MongoExtractionRepository,
)
from app.modules.imports.api.router import router as imports_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Ensure MongoDB indexes exist before the app starts serving traffic."""
    await MongoCompanyRepository(get_database()).ensure_indexes()
    await MongoDiscoveryRepository(get_database()).ensure_indexes()
    await MongoCrawlRepository(get_database()).ensure_indexes()
    await MongoExtractionRepository(get_database()).ensure_indexes()
    await MongoEvidenceRepository(get_database()).ensure_indexes()
    yield


app = FastAPI(title="Lead Intelligence API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(companies_module_router)
app.include_router(discovery_router)
app.include_router(crawling_router)
app.include_router(evidence_router)
app.include_router(extraction_router)
app.include_router(imports_router)
app.include_router(queue_stats_router)
