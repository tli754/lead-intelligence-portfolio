"""Unit tests for the confidence policy (AC-21)."""

from app.modules.extraction.domain.confidence_policy import ConfidenceInputs, compute_confidence


def test_clamped_to_0_100():
    high = compute_confidence(
        ConfidenceInputs(
            source_authority=100,
            extractor_reliability=100,
            page_type_relevance=100,
            directness=100,
            agreeing_source_count=3,
        )
    )
    assert 0 <= high <= 100

    low = compute_confidence(
        ConfidenceInputs(
            source_authority=0,
            extractor_reliability=0,
            page_type_relevance=0,
            directness=0,
            freshness_days=10_000,
        )
    )
    assert 0 <= low <= 100
    assert low == 0


def test_deterministic():
    inputs = ConfidenceInputs(
        source_authority=80, extractor_reliability=70, page_type_relevance=60, directness=90
    )
    assert compute_confidence(inputs) == compute_confidence(inputs)


def test_conflict_penalty_lowers_score():
    without_conflict = compute_confidence(
        ConfidenceInputs(
            source_authority=90,
            extractor_reliability=90,
            page_type_relevance=90,
            directness=90,
            has_active_conflict=False,
        )
    )
    with_conflict = compute_confidence(
        ConfidenceInputs(
            source_authority=90,
            extractor_reliability=90,
            page_type_relevance=90,
            directness=90,
            has_active_conflict=True,
        )
    )
    assert with_conflict < without_conflict


def test_inference_cap_below_75():
    score = compute_confidence(
        ConfidenceInputs(
            source_authority=100,
            extractor_reliability=100,
            page_type_relevance=100,
            directness=100,
            is_inference=True,
        )
    )
    assert score < 75


def test_freshness_penalty_lowers_score():
    fresh = compute_confidence(
        ConfidenceInputs(
            source_authority=80,
            extractor_reliability=80,
            page_type_relevance=80,
            directness=80,
            freshness_days=0,
        )
    )
    stale = compute_confidence(
        ConfidenceInputs(
            source_authority=80,
            extractor_reliability=80,
            page_type_relevance=80,
            directness=80,
            freshness_days=365,
        )
    )
    assert stale < fresh


def test_agreement_boost_raises_score():
    single = compute_confidence(
        ConfidenceInputs(
            source_authority=70,
            extractor_reliability=70,
            page_type_relevance=70,
            directness=70,
            agreeing_source_count=1,
        )
    )
    agreeing = compute_confidence(
        ConfidenceInputs(
            source_authority=70,
            extractor_reliability=70,
            page_type_relevance=70,
            directness=70,
            agreeing_source_count=2,
        )
    )
    assert agreeing > single


def test_single_authoritative_source_may_exceed_85():
    score = compute_confidence(
        ConfidenceInputs(
            source_authority=100, extractor_reliability=100, page_type_relevance=100, directness=100
        )
    )
    assert score > 85


def test_two_agreeing_strong_sources_may_exceed_90():
    score = compute_confidence(
        ConfidenceInputs(
            source_authority=90,
            extractor_reliability=90,
            page_type_relevance=90,
            directness=90,
            agreeing_source_count=2,
        )
    )
    assert score > 90
