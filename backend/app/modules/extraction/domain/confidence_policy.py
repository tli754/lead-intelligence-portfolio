"""A versioned, deterministic confidence policy.

Pure — never accepts a model-generated confidence value (there is no AI
model anywhere in this task). Implements exactly brief section 14's
suggested behavior:

- integer 0-100, always clamped.
- a single authoritative source may exceed 85.
- two independent agreeing strong sources may exceed 90.
- inferred values are capped below 75.
- active conflicts cap confidence.
"""

from pydantic import BaseModel, Field

from app.modules.extraction.domain.models import ConfidenceScore

CONFIDENCE_POLICY_VERSION = "v1"

_INFERENCE_CAP = 74
_ACTIVE_CONFLICT_CAP = 60
_AGREEMENT_BOOST_PER_SOURCE = 8
_MAX_AGREEMENT_BOOST = 15
_FRESHNESS_PENALTY_PER_30_DAYS = 3
_MAX_FRESHNESS_PENALTY = 25


class ConfidenceInputs(BaseModel):
    source_authority: int = Field(ge=0, le=100)
    extractor_reliability: int = Field(ge=0, le=100)
    page_type_relevance: int = Field(ge=0, le=100)
    directness: int = Field(ge=0, le=100)
    agreeing_source_count: int = Field(default=1, ge=1)
    freshness_days: int = Field(default=0, ge=0)
    has_active_conflict: bool = False
    is_inference: bool = False


def compute_confidence(inputs: ConfidenceInputs) -> ConfidenceScore:
    base = (
        inputs.source_authority * 0.40
        + inputs.extractor_reliability * 0.25
        + inputs.page_type_relevance * 0.20
        + inputs.directness * 0.15
    )
    score = round(base)

    if inputs.agreeing_source_count > 1:
        score += min(
            _MAX_AGREEMENT_BOOST,
            (inputs.agreeing_source_count - 1) * _AGREEMENT_BOOST_PER_SOURCE,
        )

    if inputs.is_inference:
        score = min(score, _INFERENCE_CAP)

    if inputs.has_active_conflict:
        score = min(score, _ACTIVE_CONFLICT_CAP)

    freshness_penalty = min(
        _MAX_FRESHNESS_PENALTY, (inputs.freshness_days // 30) * _FRESHNESS_PENALTY_PER_30_DAYS
    )
    score -= freshness_penalty

    return max(0, min(100, score))
