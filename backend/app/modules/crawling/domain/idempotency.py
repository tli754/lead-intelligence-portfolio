"""Idempotency-key computation (section 16), pure and deterministic.

Computed from the **request**, before target selection runs — deliberately,
so a duplicate-request short-circuit doesn't require doing any selection/
fetch work first.
"""

import hashlib
import json

from app.modules.crawling.domain.config import CrawlConfig
from app.modules.crawling.domain.models import CrawlRunOptions

# `CrawlConfig` fields that are `frozenset`s — their JSON-dumped list order
# depends on Python's per-process string-hash randomization, not on
# insertion order, so it must be sorted explicitly before hashing.
# Otherwise the identical logical configuration could hash differently
# across process restarts, defeating idempotency across restarts.
_UNORDERED_CONFIG_FIELDS = (
    "response_headers_allowlist",
    "retryable_status_codes",
    "always_browser_page_types",
)


def _sha256_of_json(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def _deterministic_config_snapshot(config: CrawlConfig) -> dict:
    snapshot = config.model_dump(mode="json")
    for field_name in _UNORDERED_CONFIG_FIELDS:
        value = snapshot.get(field_name)
        if isinstance(value, list):
            snapshot[field_name] = sorted(value)
    return snapshot


def compute_idempotency_key(
    company_id: str,
    discovery_run_id: str,
    *,
    config: CrawlConfig,
    options: CrawlRunOptions,
) -> str:
    """`idempotency_key = sha256(company_id | discovery_run_id |
    sha256(json(config_snapshot)) | sha256(json(sorted(manualUrls),
    sorted(includePageTypes), sorted(excludePageTypes), maxPages,
    browserPolicy, forceRefresh)))`.

    `forceRefresh` only changes in-run fetch behavior (see the
    application service) — it does **not** bypass the active-run conflict
    check, so it's deliberately included in the key like every other
    option: two otherwise-identical requests differing only in
    `forceRefresh` are two distinct idempotency keys, but a request
    repeated with the *same* `forceRefresh` value still conflicts with
    its own still-active run.
    """
    config_hash = _sha256_of_json(_deterministic_config_snapshot(config))
    options_hash = _sha256_of_json(
        {
            "manual_urls": sorted(options.manual_urls),
            "include_page_types": sorted(pt.value for pt in options.include_page_types),
            "exclude_page_types": sorted(pt.value for pt in options.exclude_page_types),
            "max_pages": options.max_pages,
            "browser_policy": options.browser_policy.value if options.browser_policy else None,
            "force_refresh": options.force_refresh,
        }
    )
    combined = f"{company_id}|{discovery_run_id}|{config_hash}|{options_hash}"
    return hashlib.sha256(combined.encode()).hexdigest()
