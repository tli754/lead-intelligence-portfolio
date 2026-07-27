"""Request/response DTOs for the discovery-module HTTP API. All JSON is camelCase.

A small local `CamelCaseModel` base, not imported from the companies or
imports modules — this module's only real coupling to `companies` is
the gateway (`infrastructure/company_service_gateway.py`).
"""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.modules.discovery.domain.models import DiscoveredUrl, DiscoveryRun, DiscoverySummary


class CamelCaseModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class DiscoverySummaryResponse(CamelCaseModel):
    urls_found: int
    urls_accepted: int
    urls_excluded: int
    sitemap_urls_found: int
    robots_urls_found: int
    duplicate_urls_merged: int
    warnings: int
    duration_ms: int


class DiscoveryRunResponse(CamelCaseModel):
    discovery_run_id: str
    company_id: str
    root_domain: str
    homepage_url: str | None
    status: str
    started_at: str | None
    completed_at: str | None
    summary: DiscoverySummaryResponse
    error: str | None
    created_at: str
    updated_at: str


class DiscoveryRunEnvelope(CamelCaseModel):
    data: DiscoveryRunResponse


class DiscoveredUrlResponse(CamelCaseModel):
    discovered_url_id: str
    discovery_run_id: str
    company_id: str
    url: str
    normalized_url: str
    page_type: str
    page_type_confidence: int
    priority: str
    discovery_sources: list[str]
    source_urls: list[str]
    anchor_texts: list[str]
    depth: int
    is_same_domain: bool
    is_allowed: bool
    first_discovered_at: str
    last_discovered_at: str
    metadata: dict


class PaginationMeta(CamelCaseModel):
    page: int
    page_size: int
    total: int


class DiscoveredUrlListResponse(CamelCaseModel):
    data: list[DiscoveredUrlResponse]
    pagination: PaginationMeta


def summary_to_response(summary: DiscoverySummary) -> DiscoverySummaryResponse:
    return DiscoverySummaryResponse(**summary.model_dump())


def run_to_response(run: DiscoveryRun) -> DiscoveryRunResponse:
    return DiscoveryRunResponse(
        discovery_run_id=run.discovery_run_id,
        company_id=run.company_id,
        root_domain=run.root_domain,
        homepage_url=run.homepage_url,
        status=run.status.value,
        started_at=run.started_at.isoformat() if run.started_at else None,
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
        summary=summary_to_response(run.summary),
        error=run.error,
        created_at=run.created_at.isoformat(),
        updated_at=run.updated_at.isoformat(),
    )


def discovered_url_to_response(url: DiscoveredUrl) -> DiscoveredUrlResponse:
    return DiscoveredUrlResponse(
        discovered_url_id=url.discovered_url_id,
        discovery_run_id=url.discovery_run_id,
        company_id=url.company_id,
        url=url.url,
        normalized_url=url.normalized_url,
        page_type=url.page_type.value,
        page_type_confidence=url.page_type_confidence,
        priority=url.priority.value,
        discovery_sources=[source.value for source in url.discovery_sources],
        source_urls=url.source_urls,
        anchor_texts=url.anchor_texts,
        depth=url.depth,
        is_same_domain=url.is_same_domain,
        is_allowed=url.is_allowed,
        first_discovered_at=url.first_discovered_at.isoformat(),
        last_discovered_at=url.last_discovered_at.isoformat(),
        metadata=url.metadata,
    )
