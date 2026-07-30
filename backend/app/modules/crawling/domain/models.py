"""Domain models for the crawling module. Pure Pydantic — no FastAPI or MongoDB imports.

`CrawlTarget.page_type`/`CrawlTarget.priority` (and the equivalent fields
on `CrawledPage`) reuse `app.modules.discovery.domain.enums.PageType`/
`DiscoveryPriority` directly rather than redefining a second, redundant
enum — the same pure-value-type cross-module reuse precedent already
used for `ProcessingStatus` in `modules/discovery/domain/gateway.py`.
"""

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from app.modules.crawling.domain.enums import (
    BrowserFallbackReason,
    BrowserPolicy,
    ContentStorageMode,
    CrawlStatus,
    FetchMode,
    PageFetchStatus,
)
from app.modules.discovery.domain.enums import DiscoveryPriority, PageType


def _as_utc(value: datetime) -> datetime:
    """Treat a naive datetime as UTC rather than rejecting it.

    Same rationale as `modules/discovery/domain/models.py`'s `_as_utc`
    helper (duplicated locally, not imported): Motor returns naive
    datetimes on read unless the client is constructed with
    `tz_aware=True`.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class RedirectHop(BaseModel):
    """One hop in a page-fetch redirect chain.

    A local duplicate of `modules.discovery.domain.models.RedirectHop`,
    matching discovery's own precedent of duplicating small pure
    helpers/models rather than cross-importing them.
    """

    url: str
    status_code: int


class HttpMetadata(BaseModel):
    status_code: int | None = None
    content_type: str | None = None
    content_length: int | None = None
    etag: str | None = None
    last_modified: str | None = None
    redirect_history: list[RedirectHop] = Field(default_factory=list)
    response_headers_allowlist: dict[str, str] = Field(default_factory=dict)
    duration_ms: int = 0
    remote_ip_validation_result: str | None = None


class PageMetadata(BaseModel):
    title: str | None = None
    meta_description: str | None = None
    canonical_url: str | None = None
    language: str | None = None
    robots_meta: str | None = None
    og_site_name: str | None = None
    og_title: str | None = None
    generator: str | None = None
    html_size_bytes: int = 0
    cleaned_html_size_bytes: int = 0
    extracted_text_length: int = 0
    link_count: int = 0
    script_count: int = 0
    stylesheet_count: int = 0

    # Documented additions (contract T2): raw, page-level technology
    # signals (section 9) — never interpreted into a company-facing
    # technology profile by this module.
    technology_signals: dict = Field(default_factory=dict)

    # Documented additions (contract T2): cleaning/extraction are
    # versioned (section 7/8), so a later re-run with different rules can
    # be distinguished from an earlier one.
    cleaning_rules_version: str = "v1"
    text_extraction_rules_version: str = "v1"


class ContentHashes(BaseModel):
    raw_content_sha256: str | None = None
    cleaned_html_sha256: str | None = None
    extracted_text_sha256: str | None = None
    structural_hash: str | None = None


class ContentReference(BaseModel):
    """An opaque handle to externally-stored content.

    Never a filesystem path — `LocalFilesystemContentStorage` re-derives
    and re-validates the real path from these fields on every
    `load_content`/`delete_content` call rather than trusting a cached
    path (see `infrastructure/local_filesystem_content_storage.py`).
    """

    reference_id: str
    company_id: str
    crawl_run_id: str
    page_id: str
    kind: Literal["raw", "cleaned", "text"]


class ContentStorageInfo(BaseModel):
    """Reconciles the task brief's single `content_storage: ContentStorageMode`
    field (section 1) into a 3-artifact-aware structure — raw content's own
    reference stays at `CrawledPage.raw_content_reference` exactly as the
    brief's literal field list already has it; this only covers cleaned
    HTML and extracted text, which may additionally be stored inline.
    """

    raw_content_mode: ContentStorageMode = ContentStorageMode.NONE
    cleaned_html_mode: ContentStorageMode = ContentStorageMode.NONE
    cleaned_html_reference: ContentReference | None = None
    extracted_text_mode: ContentStorageMode = ContentStorageMode.NONE
    extracted_text_reference: ContentReference | None = None


class CrawlRunOptions(BaseModel):
    """Per-run overrides accepted by `POST /api/companies/{id}/crawl-runs`
    (section 17's request body) — everything else comes from the
    injected `CrawlConfig`."""

    max_pages: int | None = None
    browser_policy: BrowserPolicy | None = None
    force_refresh: bool = False
    include_page_types: list[PageType] = Field(default_factory=list)
    exclude_page_types: list[PageType] = Field(default_factory=list)
    manual_urls: list[str] = Field(default_factory=list)


class CrawlWarning(BaseModel):
    code: str
    message: str
    url: str | None = None
    page_id: str | None = None
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def timestamp_is_utc(cls, value: datetime) -> datetime:
        return _as_utc(value)


class CrawlSummary(BaseModel):
    targets_selected: int = 0
    pages_fetched: int = 0
    pages_unchanged: int = 0
    pages_skipped: int = 0
    pages_blocked_by_robots: int = 0
    pages_failed: int = 0
    pages_requiring_browser: int = 0
    pages_browser_fetched: int = 0
    bytes_downloaded: int = 0
    warnings: int = 0
    duration_ms: int = 0


class CrawlTarget(BaseModel):
    crawl_target_id: str = Field(default_factory=lambda: str(uuid4()))
    crawl_run_id: str
    company_id: str
    discovery_run_id: str
    discovered_url_id: str | None = None

    url: str
    normalized_url: str
    page_type: PageType
    priority: DiscoveryPriority
    fetch_mode: FetchMode = FetchMode.HTTP
    depth: int = Field(default=0, ge=0)
    expected_content_type: str | None = None

    previous_page_id: str | None = None
    previous_content_hash: str | None = None

    status: PageFetchStatus = PageFetchStatus.QUEUED
    attempt_count: int = Field(default=0, ge=0)

    created_at: datetime
    updated_at: datetime
    document_version: int = 1

    @field_validator("created_at", "updated_at")
    @classmethod
    def timestamps_are_utc(cls, value: datetime) -> datetime:
        return _as_utc(value)


class CrawlRun(BaseModel):
    crawl_run_id: str = Field(default_factory=lambda: str(uuid4()))
    company_id: str
    discovery_run_id: str

    status: CrawlStatus = CrawlStatus.QUEUED
    started_at: datetime | None = None
    completed_at: datetime | None = None

    configuration_snapshot: dict = Field(default_factory=dict)
    # Added alongside the RQ enqueue/execute split (Task 017):
    # `enqueue_crawl_run` persists the caller's full `CrawlRunOptions`
    # here (as a JSON-mode dump, mirroring `configuration_snapshot`'s own
    # pattern) so `execute_crawl_run` — looked up later by `crawl_run_id`
    # alone, possibly from a separate worker process — can recover
    # `force_refresh`/`include_page_types`/`exclude_page_types`/
    # `manual_urls` exactly as requested, rather than silently falling
    # back to defaults. A run persisted before this field existed
    # defaults to `{}`, which `CrawlRunOptions.model_validate({})`
    # resolves to an all-default `CrawlRunOptions()` — the same behavior
    # this field is fixing forward from, not a breaking change for
    # already-persisted documents.
    options_snapshot: dict = Field(default_factory=dict)
    summary: CrawlSummary = Field(default_factory=CrawlSummary)
    warnings: list[CrawlWarning] = Field(default_factory=list)
    error: str | None = None

    created_at: datetime
    updated_at: datetime

    # Documented addition (contract T2): needed for idempotency
    # (section 16) — computed by the application service before target
    # selection runs (see `application/website_crawl_service.py`).
    idempotency_key: str

    document_version: int = 1

    @field_validator("started_at", "completed_at", "created_at", "updated_at")
    @classmethod
    def timestamps_are_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value) if value is not None else None


class CrawledPage(BaseModel):
    page_id: str = Field(default_factory=lambda: str(uuid4()))
    crawl_run_id: str
    company_id: str
    discovery_run_id: str
    discovered_url_id: str | None = None

    original_url: str
    final_url: str | None = None
    normalized_url: str
    page_type: PageType
    priority: DiscoveryPriority
    fetch_mode: FetchMode = FetchMode.HTTP
    fetch_status: PageFetchStatus = PageFetchStatus.QUEUED

    http_metadata: HttpMetadata = Field(default_factory=HttpMetadata)
    page_metadata: PageMetadata | None = None
    content_storage: ContentStorageInfo = Field(default_factory=ContentStorageInfo)
    content_hashes: ContentHashes = Field(default_factory=ContentHashes)

    cleaned_html: str | None = None
    extracted_text: str | None = None
    raw_content_reference: ContentReference | None = None

    previous_page_id: str | None = None
    unchanged_from_page_id: str | None = None
    browser_fallback_reason: BrowserFallbackReason | None = None

    warnings: list[CrawlWarning] = Field(default_factory=list)

    fetched_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    document_version: int = 1

    @field_validator("fetched_at", "created_at", "updated_at")
    @classmethod
    def timestamps_are_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value) if value is not None else None
