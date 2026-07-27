"""Unit tests for the freshness policy (AC-13's freshness half)."""

from datetime import UTC, datetime, timedelta

from app.modules.extraction.domain.field_catalogue import FieldPath
from app.modules.extraction.domain.freshness_policy import (
    FreshnessPolicy,
    apply_staleness_penalty,
    is_stale,
)

_NOW = datetime(2026, 7, 26, tzinfo=UTC)


def test_recent_fact_not_stale():
    recent = _NOW - timedelta(days=5)
    assert is_stale(FieldPath.GROWTH_EXPANSION, recent, now=_NOW) is False


def test_old_announcement_marked_stale():
    old = _NOW - timedelta(days=200)
    assert is_stale(FieldPath.GROWTH_EXPANSION, old, now=_NOW) is True


def test_careers_window_shorter_than_growth_window():
    policy = FreshnessPolicy()
    assert policy.days_for(FieldPath.GROWTH_HIRING) < policy.days_for(FieldPath.GROWTH_EXPANSION)


def test_identity_window_longest():
    policy = FreshnessPolicy()
    assert policy.days_for(FieldPath.IDENTITY_COMPANY_NAME) == 365


def test_configurable_policy():
    custom = FreshnessPolicy(growth_days=1)
    old = _NOW - timedelta(days=5)
    assert is_stale(FieldPath.GROWTH_EXPANSION, old, now=_NOW, policy=custom) is True


def test_staleness_penalty_lowers_confidence():
    old = _NOW - timedelta(days=400)
    penalized = apply_staleness_penalty(80, FieldPath.IDENTITY_COMPANY_NAME, old, now=_NOW)
    assert penalized < 80


def test_no_penalty_when_fresh():
    recent = _NOW - timedelta(days=1)
    unchanged = apply_staleness_penalty(80, FieldPath.IDENTITY_COMPANY_NAME, recent, now=_NOW)
    assert unchanged == 80
