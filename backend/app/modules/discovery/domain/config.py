"""Tunable configuration for the discovery module.

A plain, injectable Pydantic model — never reads `os.environ` itself
(that stays confined to `backend/app/config.py`, off-limits to this
module). Wiring real values from application `Settings` is a required
integration step, not done here.
"""

from pydantic import BaseModel, Field

from app.modules.discovery.domain.enums import DiscoveryPriority, PageType


class DiscoveryConfig(BaseModel):
    # HTTP safety.
    connect_timeout_s: float = 5.0
    read_timeout_s: float = 10.0
    max_redirects: int = 5
    max_response_size_bytes: int = 2_000_000
    max_concurrent_requests: int = 4
    user_agent: str = "LeadIntelligenceDiscoveryBot/1.0 (+https://example.invalid/bot)"

    # Sitemap limits.
    max_sitemap_files: int = 50
    max_sitemap_depth: int = 5
    max_urls_per_run: int = 2000
    large_sitemap_threshold: int = 200
    sitemap_sample_size: int = 50
    max_xml_elements_per_document: int = 200_000

    # Priority overrides — merged over `priority_assigner.DEFAULT_PRIORITY_MAP`,
    # so callers never need to edit the hardcoded default map directly.
    priority_overrides: dict[PageType, DiscoveryPriority] = Field(default_factory=dict)
