"""Field-specific freshness rules.

`FreshnessPolicy` is a plain injectable Pydantic config — never reads
`os.environ` itself, matching `CrawlConfig`'s own documented pattern.
Suggested defaults are brief section 18's own category windows (days).

Stale facts/evidence are never deleted — only marked `stale` (status
transition), still queryable. `ExtractionRepository.mark_previous_facts_stale`
performs that transition at run-start, not any delete path here.
"""

from datetime import datetime

from pydantic import BaseModel

from app.modules.extraction.domain.field_catalogue import FieldPath
from app.modules.extraction.domain.models import ConfidenceScore

FRESHNESS_POLICY_VERSION = "v1"

_STALENESS_PENALTY = 30

_ORGANISATION_CONTACT_FIELDS = frozenset(
    {
        FieldPath.ORGANISATION_EMAILS,
        FieldPath.ORGANISATION_PHONE_NUMBERS,
        FieldPath.ORGANISATION_PEOPLE,
        FieldPath.ORGANISATION_INTERNAL_IT_STATUS,
        FieldPath.ORGANISATION_RECOMMENDED_CONTACT_CANDIDATES,
    }
)


class FreshnessPolicy(BaseModel):
    identity_days: int = 365
    platform_days: int = 180
    contact_days: int = 180
    business_capabilities_days: int = 180
    physical_locations_days: int = 180
    technology_days: int = 90
    catalogue_estimates_days: int = 30
    growth_days: int = 90
    careers_days: int = 30

    def days_for(self, field_path: FieldPath) -> int:
        category = _category_for_field(field_path)
        return getattr(self, f"{category}_days")


def _category_for_field(field_path: FieldPath) -> str:
    if field_path == FieldPath.IDENTITY_PLATFORM:
        return "platform"
    if field_path in _ORGANISATION_CONTACT_FIELDS:
        return "contact"
    if field_path == FieldPath.GROWTH_HIRING:
        return "careers"
    prefix = field_path.value.split(".", 1)[0]
    return {
        "identity": "identity",
        "business": "business_capabilities",
        "operations": "physical_locations",
        "technology": "technology",
        "catalogue": "catalogue_estimates",
        "growth": "growth",
    }.get(prefix, "identity")


def is_stale(
    field_path: FieldPath,
    last_verified_at: datetime,
    *,
    now: datetime,
    policy: FreshnessPolicy | None = None,
) -> bool:
    policy = policy or FreshnessPolicy()
    window_days = policy.days_for(field_path)
    age_days = (now - last_verified_at).days
    return age_days > window_days


def apply_staleness_penalty(
    confidence: ConfidenceScore,
    field_path: FieldPath,
    last_verified_at: datetime,
    *,
    now: datetime,
    policy: FreshnessPolicy | None = None,
) -> ConfidenceScore:
    if is_stale(field_path, last_verified_at, now=now, policy=policy):
        return max(0, confidence - _STALENESS_PENALTY)
    return confidence
