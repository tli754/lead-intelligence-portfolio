"""Idempotency-key computation, pure and deterministic.

Mirrors `modules/crawling/domain/idempotency.py`'s exact construction
(including its documented `sorted(...)`-before-hashing fix for
frozenset/list ordering determinism) — `company_id | crawl_run_id |
sha256(sorted(extractorIds), sorted(pageTypes), forceRefresh)`.
"""

import hashlib
import json

from app.modules.extraction.domain.models import ExtractionRunOptions


def _sha256_of_json(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def compute_idempotency_key(
    company_id: str, crawl_run_id: str, options: ExtractionRunOptions
) -> str:
    options_hash = _sha256_of_json(
        {
            "extractor_ids": sorted(options.extractor_ids),
            "page_types": sorted(page_type.value for page_type in options.page_types),
            "force_refresh": options.force_refresh,
        }
    )
    combined = f"{company_id}|{crawl_run_id}|{options_hash}"
    return hashlib.sha256(combined.encode()).hexdigest()
