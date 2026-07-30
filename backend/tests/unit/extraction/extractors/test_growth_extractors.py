"""Unit tests for the growth-signal extractor family (AC-03, AC-13, AC-14)."""

from app.modules.discovery.domain.enums import PageType
from app.modules.extraction.domain.extractors.growth.growth_extractor import GrowthSignalExtractor
from app.modules.extraction.domain.field_catalogue import FieldPath

from ..conftest import make_page_context, read_fixture


def test_hiring_signal_with_growth_context():
    html = read_fixture("careers-technology.html")
    page = make_page_context(html=html, page_type=PageType.CAREERS)
    candidates = GrowthSignalExtractor().extract(page)
    hiring = [c for c in candidates if c.field_path == FieldPath.GROWTH_HIRING]
    assert hiring


def test_new_store_signal():
    html = read_fixture("news-new-store.html")
    page = make_page_context(html=html, page_type=PageType.NEWS)
    candidates = GrowthSignalExtractor().extract(page)
    new_store = [c for c in candidates if c.field_path == FieldPath.GROWTH_NEW_STORE]
    assert new_store


def test_warehouse_move_signal():
    html = "<html><body><p>We are moving to a new warehouse next month.</p></body></html>"
    page = make_page_context(html=html, page_type=PageType.NEWS)
    candidates = GrowthSignalExtractor().extract(page)
    warehouse = [c for c in candidates if c.field_path == FieldPath.GROWTH_WAREHOUSE_CHANGE]
    assert warehouse


def test_platform_migration_signal():
    html = "<html><body><p>We are migrating to a new platform this quarter.</p></body></html>"
    page = make_page_context(html=html, page_type=PageType.NEWS)
    candidates = GrowthSignalExtractor().extract(page)
    migration = [c for c in candidates if c.field_path == FieldPath.GROWTH_PLATFORM_MIGRATION]
    assert migration


def test_old_announcement_marked_stale_via_freshness_policy():
    from datetime import UTC, datetime, timedelta

    from app.modules.extraction.domain.freshness_policy import is_stale

    html = read_fixture("news-old-expansion.html")
    page = make_page_context(html=html, page_type=PageType.NEWS)
    candidates = GrowthSignalExtractor().extract(page)
    expansion = next(c for c in candidates if c.field_path == FieldPath.GROWTH_EXPANSION)
    publication_date = datetime.fromisoformat(
        expansion.normalized_value["publication_date"]
    ).replace(tzinfo=UTC)
    now = datetime(2026, 7, 26, tzinfo=UTC)
    assert now - publication_date > timedelta(days=90)
    assert is_stale(FieldPath.GROWTH_EXPANSION, publication_date, now=now) is True


def test_publication_vs_event_date():
    html = read_fixture("news-new-store.html")
    page = make_page_context(html=html, page_type=PageType.NEWS)
    candidates = GrowthSignalExtractor().extract(page)
    new_store = next(c for c in candidates if c.field_path == FieldPath.GROWTH_NEW_STORE)
    assert new_store.normalized_value["publication_date"] == "2026-07-20"
    assert new_store.normalized_value["event_date"] == "2026-07-20"
    assert "publication_date" in new_store.normalized_value
    assert "event_date" in new_store.normalized_value


def test_routine_vacancy_not_treated_as_expansion():
    html = read_fixture("careers-general.html")
    page = make_page_context(html=html, page_type=PageType.CAREERS)
    candidates = GrowthSignalExtractor().extract(page)
    hiring = [c for c in candidates if c.field_path == FieldPath.GROWTH_HIRING]
    assert hiring == []


def test_original_statement_preserved_in_evidence():
    html = read_fixture("news-new-store.html")
    page = make_page_context(html=html, page_type=PageType.NEWS)
    candidates = GrowthSignalExtractor().extract(page)
    new_store = next(c for c in candidates if c.field_path == FieldPath.GROWTH_NEW_STORE)
    assert new_store.evidence_drafts
    assert "new store" in new_store.evidence_drafts[0].source_fragment.lower()


def test_deterministic_output_and_input_not_mutated():
    html = read_fixture("news-new-store.html")
    page = make_page_context(html=html, page_type=PageType.NEWS)
    extractor = GrowthSignalExtractor()
    before = page.model_dump()
    assert extractor.extract(page) == extractor.extract(page)
    assert page.model_dump() == before
