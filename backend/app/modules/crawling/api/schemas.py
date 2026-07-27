"""Request/response DTOs for the crawling-module HTTP API. All JSON is camelCase.

A small local `CamelCaseModel` base, not imported from any other module —
matching `modules/discovery/api/schemas.py`'s exact precedent (duplicated,
not cross-imported).

`PageResponse` never includes raw HTML or the full (untruncated)
`extracted_text` by default — only a capped preview
(`extractedTextPreview`, distinct from and smaller than the storage-layer
250,000-char cap), plus an opaque `{referenceId}` per artifact where
applicable, never a filesystem path. `HttpMetadata.response_headers_allowlist`
passes through only the headers already filtered at fetch time — this
layer trusts the domain model, it does not re-filter.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from app.modules.crawling.domain.enums import BrowserPolicy
from app.modules.crawling.domain.models import (
    CrawledPage,
    CrawlRun,
    CrawlRunOptions,
    CrawlSummary,
    CrawlTarget,
)
from app.modules.discovery.domain.enums import PageType

EXTRACTED_TEXT_PREVIEW_CAP = 2_000


class CamelCaseModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# --- Requests -----------------------------------------------------------------


class CrawlRunOptionsRequest(CamelCaseModel):
    max_pages: int | None = None
    browser_policy: BrowserPolicy | None = None
    force_refresh: bool = False
    include_page_types: list[PageType] = []
    exclude_page_types: list[PageType] = []
    manual_urls: list[str] = []

    def to_domain(self) -> CrawlRunOptions:
        return CrawlRunOptions(
            max_pages=self.max_pages,
            browser_policy=self.browser_policy,
            force_refresh=self.force_refresh,
            include_page_types=self.include_page_types,
            exclude_page_types=self.exclude_page_types,
            manual_urls=self.manual_urls,
        )


class CreateCrawlRunRequest(CamelCaseModel):
    discovery_run_id: str
    options: CrawlRunOptionsRequest | None = None

    def options_or_default(self) -> CrawlRunOptions:
        return self.options.to_domain() if self.options is not None else CrawlRunOptions()


# --- Shared response fragments -------------------------------------------------


class PaginationMeta(CamelCaseModel):
    page: int
    page_size: int
    total: int


class CrawlSummaryResponse(CamelCaseModel):
    targets_selected: int
    pages_fetched: int
    pages_unchanged: int
    pages_skipped: int
    pages_blocked_by_robots: int
    pages_failed: int
    pages_requiring_browser: int
    pages_browser_fetched: int
    bytes_downloaded: int
    warnings: int
    duration_ms: int


def summary_to_response(summary: CrawlSummary) -> CrawlSummaryResponse:
    return CrawlSummaryResponse(**summary.model_dump())


class ContentReferenceResponse(CamelCaseModel):
    reference_id: str


class HttpMetadataResponse(CamelCaseModel):
    status_code: int | None
    content_type: str | None
    content_length: int | None
    etag: str | None
    last_modified: str | None
    response_headers_allowlist: dict[str, str]
    duration_ms: int
    remote_ip_validation_result: str | None


class PageMetadataResponse(CamelCaseModel):
    title: str | None
    meta_description: str | None
    canonical_url: str | None
    language: str | None
    robots_meta: str | None
    og_site_name: str | None
    og_title: str | None
    generator: str | None
    html_size_bytes: int
    cleaned_html_size_bytes: int
    extracted_text_length: int
    link_count: int
    script_count: int
    stylesheet_count: int
    technology_signals: dict[str, Any]


class ContentHashesResponse(CamelCaseModel):
    raw_content_sha256: str | None
    cleaned_html_sha256: str | None
    extracted_text_sha256: str | None
    structural_hash: str | None


class ContentStorageInfoResponse(CamelCaseModel):
    raw_content_mode: str
    cleaned_html_mode: str
    cleaned_html_reference: ContentReferenceResponse | None
    extracted_text_mode: str
    extracted_text_reference: ContentReferenceResponse | None


# --- Crawl runs -----------------------------------------------------------------


class CrawlRunResponse(CamelCaseModel):
    crawl_run_id: str
    company_id: str
    discovery_run_id: str
    status: str
    started_at: str | None
    completed_at: str | None
    summary: CrawlSummaryResponse
    warnings_count: int
    error: str | None
    created_at: str
    updated_at: str


class CrawlRunEnvelope(CamelCaseModel):
    data: CrawlRunResponse


def run_to_response(run: CrawlRun) -> CrawlRunResponse:
    return CrawlRunResponse(
        crawl_run_id=run.crawl_run_id,
        company_id=run.company_id,
        discovery_run_id=run.discovery_run_id,
        status=run.status.value,
        started_at=run.started_at.isoformat() if run.started_at else None,
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
        summary=summary_to_response(run.summary),
        warnings_count=len(run.warnings),
        error=run.error,
        created_at=run.created_at.isoformat(),
        updated_at=run.updated_at.isoformat(),
    )


# --- Crawl targets --------------------------------------------------------------


class CrawlTargetResponse(CamelCaseModel):
    crawl_target_id: str
    crawl_run_id: str
    company_id: str
    discovery_run_id: str
    discovered_url_id: str | None
    url: str
    normalized_url: str
    page_type: str
    priority: str
    fetch_mode: str
    depth: int
    expected_content_type: str | None
    previous_page_id: str | None
    previous_content_hash: str | None
    status: str
    attempt_count: int
    created_at: str
    updated_at: str


class CrawlTargetListResponse(CamelCaseModel):
    data: list[CrawlTargetResponse]
    pagination: PaginationMeta


def target_to_response(target: CrawlTarget) -> CrawlTargetResponse:
    return CrawlTargetResponse(
        crawl_target_id=target.crawl_target_id,
        crawl_run_id=target.crawl_run_id,
        company_id=target.company_id,
        discovery_run_id=target.discovery_run_id,
        discovered_url_id=target.discovered_url_id,
        url=target.url,
        normalized_url=target.normalized_url,
        page_type=target.page_type.value,
        priority=target.priority.value,
        fetch_mode=target.fetch_mode.value,
        depth=target.depth,
        expected_content_type=target.expected_content_type,
        previous_page_id=target.previous_page_id,
        previous_content_hash=target.previous_content_hash,
        status=target.status.value,
        attempt_count=target.attempt_count,
        created_at=target.created_at.isoformat(),
        updated_at=target.updated_at.isoformat(),
    )


# --- Pages ------------------------------------------------------------------------


class PageResponse(CamelCaseModel):
    page_id: str
    crawl_run_id: str
    company_id: str
    discovery_run_id: str
    discovered_url_id: str | None
    original_url: str
    final_url: str | None
    normalized_url: str
    page_type: str
    priority: str
    fetch_mode: str
    fetch_status: str
    http_metadata: HttpMetadataResponse
    page_metadata: PageMetadataResponse | None
    content_storage: ContentStorageInfoResponse
    content_hashes: ContentHashesResponse
    extracted_text_preview: str
    extracted_text_truncated: bool
    raw_content_reference: ContentReferenceResponse | None
    previous_page_id: str | None
    unchanged_from_page_id: str | None
    browser_fallback_reason: str | None
    warnings_count: int
    fetched_at: str | None
    created_at: str
    updated_at: str


class PageEnvelope(CamelCaseModel):
    data: PageResponse


class PageListResponse(CamelCaseModel):
    data: list[PageResponse]
    pagination: PaginationMeta


def _content_reference_to_response(reference) -> ContentReferenceResponse | None:
    if reference is None:
        return None
    return ContentReferenceResponse(reference_id=reference.reference_id)


def page_to_response(page: CrawledPage) -> PageResponse:
    extracted_text = page.extracted_text or ""
    preview = extracted_text[:EXTRACTED_TEXT_PREVIEW_CAP]
    truncated = len(extracted_text) > EXTRACTED_TEXT_PREVIEW_CAP

    metadata_response = None
    if page.page_metadata is not None:
        metadata_response = PageMetadataResponse(**page.page_metadata.model_dump())

    return PageResponse(
        page_id=page.page_id,
        crawl_run_id=page.crawl_run_id,
        company_id=page.company_id,
        discovery_run_id=page.discovery_run_id,
        discovered_url_id=page.discovered_url_id,
        original_url=page.original_url,
        final_url=page.final_url,
        normalized_url=page.normalized_url,
        page_type=page.page_type.value,
        priority=page.priority.value,
        fetch_mode=page.fetch_mode.value,
        fetch_status=page.fetch_status.value,
        http_metadata=HttpMetadataResponse(
            status_code=page.http_metadata.status_code,
            content_type=page.http_metadata.content_type,
            content_length=page.http_metadata.content_length,
            etag=page.http_metadata.etag,
            last_modified=page.http_metadata.last_modified,
            response_headers_allowlist=page.http_metadata.response_headers_allowlist,
            duration_ms=page.http_metadata.duration_ms,
            remote_ip_validation_result=page.http_metadata.remote_ip_validation_result,
        ),
        page_metadata=metadata_response,
        content_storage=ContentStorageInfoResponse(
            raw_content_mode=page.content_storage.raw_content_mode.value,
            cleaned_html_mode=page.content_storage.cleaned_html_mode.value,
            cleaned_html_reference=_content_reference_to_response(
                page.content_storage.cleaned_html_reference
            ),
            extracted_text_mode=page.content_storage.extracted_text_mode.value,
            extracted_text_reference=_content_reference_to_response(
                page.content_storage.extracted_text_reference
            ),
        ),
        content_hashes=ContentHashesResponse(**page.content_hashes.model_dump()),
        extracted_text_preview=preview,
        extracted_text_truncated=truncated,
        raw_content_reference=_content_reference_to_response(page.raw_content_reference),
        previous_page_id=page.previous_page_id,
        unchanged_from_page_id=page.unchanged_from_page_id,
        browser_fallback_reason=(
            page.browser_fallback_reason.value if page.browser_fallback_reason else None
        ),
        warnings_count=len(page.warnings),
        fetched_at=page.fetched_at.isoformat() if page.fetched_at else None,
        created_at=page.created_at.isoformat(),
        updated_at=page.updated_at.isoformat(),
    )
