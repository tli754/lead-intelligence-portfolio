"""Domain models for the discovery module. Pure Pydantic — no FastAPI or MongoDB imports."""

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

from app.modules.discovery.domain.enums import (
    DiscoveryPriority,
    DiscoverySource,
    DiscoveryStatus,
    PageType,
)


def _as_utc(value: datetime) -> datetime:
    """Treat a naive datetime as UTC rather than rejecting it.

    Same rationale as `modules/companies/domain/models.py`'s `_as_utc`
    helper (duplicated locally, not imported cross-module): Motor returns
    naive datetimes on read unless the client is constructed with
    `tz_aware=True`.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class RedirectHop(BaseModel):
    """One hop in a homepage-resolution redirect chain."""

    url: str
    status_code: int


class ClassificationResult(BaseModel):
    """The outcome of classifying one URL's page type.

    `alternates` retains every other rule that also matched, each tagged
    with its own rule id, so a disagreement between classifiers is
    preserved rather than silently dropped (reconciliation needs this).
    """

    page_type: PageType
    confidence: int = Field(ge=0, le=100)
    rule_id: str
    alternates: list["ClassificationResult"] = Field(default_factory=list)


class RobotsRuleGroup(BaseModel):
    """One `User-agent` block from robots.txt, captured for a *future*
    crawler to enforce — this module does no matching/enforcement itself."""

    user_agents: list[str] = Field(default_factory=list)
    disallow: list[str] = Field(default_factory=list)
    allow: list[str] = Field(default_factory=list)


class RobotsPolicyResult(BaseModel):
    sitemap_urls: list[str] = Field(default_factory=list)
    rule_groups: list[RobotsRuleGroup] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    found: bool = False


class UrlValidationResult(BaseModel):
    """The outcome of validating/normalizing one raw URL string."""

    is_valid: bool
    normalized_url: str | None = None
    rejection_reason: str | None = None


class DiscoverySummary(BaseModel):
    urls_found: int = 0
    urls_accepted: int = 0
    urls_excluded: int = 0
    sitemap_urls_found: int = 0
    robots_urls_found: int = 0
    duplicate_urls_merged: int = 0
    warnings: int = 0
    duration_ms: int = 0


class DiscoveredUrl(BaseModel):
    """One URL discovered during a run, reconciled across every source
    that surfaced it."""

    discovered_url_id: str = Field(default_factory=lambda: str(uuid4()))
    discovery_run_id: str
    company_id: str

    url: str
    normalized_url: str

    page_type: PageType
    page_type_confidence: int = Field(ge=0, le=100)
    priority: DiscoveryPriority

    discovery_sources: list[DiscoverySource] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    anchor_texts: list[str] = Field(default_factory=list)

    depth: int = Field(ge=0)
    is_same_domain: bool
    is_allowed: bool = True

    first_discovered_at: datetime
    last_discovered_at: datetime

    metadata: dict = Field(default_factory=dict)

    @field_validator("first_discovered_at", "last_discovered_at")
    @classmethod
    def timestamps_are_utc(cls, value: datetime) -> datetime:
        return _as_utc(value)


class DiscoveryRun(BaseModel):
    discovery_run_id: str = Field(default_factory=lambda: str(uuid4()))
    company_id: str
    root_domain: str
    homepage_url: str | None = None

    status: DiscoveryStatus = DiscoveryStatus.QUEUED
    started_at: datetime | None = None
    completed_at: datetime | None = None

    summary: DiscoverySummary = Field(default_factory=DiscoverySummary)
    error: str | None = None

    created_at: datetime
    updated_at: datetime

    @field_validator("started_at", "completed_at", "created_at", "updated_at")
    @classmethod
    def timestamps_are_utc(cls, value: datetime | None) -> datetime | None:
        return _as_utc(value) if value is not None else None
