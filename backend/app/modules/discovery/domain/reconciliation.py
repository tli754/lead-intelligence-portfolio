"""Merges per-source discovery candidates for the same normalized URL
into one `DiscoveredUrl`.

Each `DiscoveryCandidate` is already classified and prioritized by the
caller (classification needs per-occurrence context — anchor text,
sitemap hints — that's only available before merging). This module's job
is purely the merge: union sources/anchors/source-urls, keep the
strongest classification, the best priority, and the shallowest depth.
"""

from datetime import datetime

from pydantic import BaseModel

from app.modules.discovery.domain.enums import DiscoveryPriority, DiscoverySource
from app.modules.discovery.domain.models import ClassificationResult, DiscoveredUrl
from app.modules.discovery.domain.page_classifier import CLASSIFICATION_RULES_VERSION

_PRIORITY_RANK: dict[DiscoveryPriority, int] = {
    DiscoveryPriority.PRIORITY_1: 0,
    DiscoveryPriority.PRIORITY_2: 1,
    DiscoveryPriority.PRIORITY_3: 2,
    DiscoveryPriority.EXCLUDED: 3,
}


class DiscoveryCandidate(BaseModel):
    """One (URL, source) occurrence, before cross-source merging."""

    url: str
    normalized_url: str
    source: DiscoverySource
    source_url: str
    anchor_text: str | None
    depth: int
    classification: ClassificationResult
    is_same_domain: bool
    priority: DiscoveryPriority


def _best_priority(priorities: list[DiscoveryPriority]) -> DiscoveryPriority:
    return min(priorities, key=lambda priority: _PRIORITY_RANK[priority])


def reconcile(
    candidates: list[DiscoveryCandidate],
    *,
    company_id: str,
    discovery_run_id: str,
    discovered_at: datetime,
) -> list[DiscoveredUrl]:
    groups: dict[str, list[DiscoveryCandidate]] = {}
    for candidate in candidates:
        groups.setdefault(candidate.normalized_url, []).append(candidate)

    results: list[DiscoveredUrl] = []
    for normalized_url, group in groups.items():
        sources: list[DiscoverySource] = []
        source_urls: list[str] = []
        anchor_texts: list[str] = []
        for candidate in group:
            if candidate.source not in sources:
                sources.append(candidate.source)
            if candidate.source_url not in source_urls:
                source_urls.append(candidate.source_url)
            if candidate.anchor_text and candidate.anchor_text not in anchor_texts:
                anchor_texts.append(candidate.anchor_text)

        winner = max(group, key=lambda candidate: candidate.classification.confidence)

        alternates: list[dict[str, object]] = []
        seen_alt_keys: set[tuple[str, str]] = set()
        for candidate in group:
            for classification in (candidate.classification, *candidate.classification.alternates):
                if (
                    classification.page_type == winner.classification.page_type
                    and classification.rule_id == winner.classification.rule_id
                ):
                    continue
                key = (classification.page_type.value, classification.rule_id)
                if key in seen_alt_keys:
                    continue
                seen_alt_keys.add(key)
                alternates.append(
                    {
                        "page_type": classification.page_type.value,
                        "confidence": classification.confidence,
                        "rule_id": classification.rule_id,
                    }
                )

        metadata: dict[str, object] = {"classification_rules_version": CLASSIFICATION_RULES_VERSION}
        if alternates:
            metadata["alternate_classifications"] = alternates

        results.append(
            DiscoveredUrl(
                discovery_run_id=discovery_run_id,
                company_id=company_id,
                url=group[0].url,
                normalized_url=normalized_url,
                page_type=winner.classification.page_type,
                page_type_confidence=winner.classification.confidence,
                priority=_best_priority([candidate.priority for candidate in group]),
                discovery_sources=sources,
                source_urls=source_urls,
                anchor_texts=anchor_texts,
                depth=min(candidate.depth for candidate in group),
                is_same_domain=any(candidate.is_same_domain for candidate in group),
                is_allowed=True,
                first_discovered_at=discovered_at,
                last_discovered_at=discovered_at,
                metadata=metadata,
            )
        )

    return results
