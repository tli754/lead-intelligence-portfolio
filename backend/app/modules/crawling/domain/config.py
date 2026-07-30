"""Tunable configuration for the crawling module.

A plain, injectable Pydantic model — never reads `os.environ` itself
(that stays confined to `backend/app/config.py`, off-limits to this
module). Wiring real values from application `Settings` is a required
integration step, not done here. Matches `DiscoveryConfig`'s own
documented pattern.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.modules.crawling.domain.enums import BrowserPolicy
from app.modules.discovery.domain.enums import PageType

DEFAULT_RESPONSE_HEADERS_ALLOWLIST: frozenset[str] = frozenset(
    {
        "content-type",
        "content-length",
        "etag",
        "last-modified",
        "cache-control",
        "content-language",
        "server",
        "x-powered-by",
    }
)

DEFAULT_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({408, 425, 429, 500, 502, 503, 504})


class CrawlConfig(BaseModel):
    # Target-selection caps (section 2/21).
    max_pages_per_company: int = 30
    max_product_pages: int = 5
    max_collection_pages: int = 8
    max_unknown_pages: int = 3

    # Concurrency/pacing (section 14/15/21).
    concurrency_per_company: int = 1
    default_delay_s: float = 1.0
    min_delay_s: float = 0.5
    max_honored_crawl_delay_s: float = 10.0
    max_retry_after_s: float = 60.0

    # HTTP safety/timeouts (section 4/21).
    connect_timeout_s: float = 5.0
    read_timeout_s: float = 15.0
    total_timeout_s: float = 20.0
    max_attempts: int = 3
    max_redirects: int = 5
    max_response_size_bytes: int = 5_000_000
    user_agent: str = "LeadIntelligenceCrawlBot/1.0 (+https://example.invalid/bot)"
    response_headers_allowlist: frozenset[str] = DEFAULT_RESPONSE_HEADERS_ALLOWLIST
    retryable_status_codes: frozenset[int] = DEFAULT_RETRYABLE_STATUS_CODES

    # Retry/backoff (section 4/21) — `max_retry_after_s` above caps a
    # server-supplied `Retry-After`; these two bound the fetcher's own
    # exponential backoff when no `Retry-After` is present.
    retry_base_delay_s: float = 1.0
    retry_max_delay_s: float = 30.0

    # Content handling (section 8/11/21).
    max_extracted_text_length: int = 250_000
    inline_cleaned_html_limit_bytes: int = 250_000
    inline_extracted_text_limit_bytes: int = 250_000
    content_storage_base_dir: str = "./data/crawl-content"

    # Browser fallback (section 10).
    browser_policy: BrowserPolicy = BrowserPolicy.DETECT_ONLY
    always_browser_page_types: frozenset[PageType] = Field(default_factory=frozenset)
    browser_fallback_shell_max_text_length: int = 50
    browser_fallback_script_heavy_min_scripts: int = 3
    browser_fallback_script_heavy_max_text_length: int = 300

    # HTML validation (section 6) — decides how a classified
    # blocked/challenge page becomes a `PageFetchStatus` (T13).
    challenge_page_policy: Literal["failed", "rejected", "browser_required"] = "browser_required"

    # Failure isolation (section 14) — documented default: a homepage
    # failure marks the whole run `partial`, not `failed` outright, since
    # other pages may still have useful content.
    homepage_failure_marks_run: Literal["partial", "failed"] = "partial"

    # Idempotency/retries (section 16) — whether `retry_failed` also
    # retries targets currently `blocked_by_robots`, not just
    # `failed`/`rejected`. Off by default: a robots-disallowed URL is a
    # deliberate policy decision, not a transient failure worth retrying.
    retry_includes_blocked_by_robots: bool = False
