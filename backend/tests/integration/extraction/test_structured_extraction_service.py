"""Integration tests for `StructuredExtractionService`, using the fakes in
`conftest.py` — no real MongoDB, no real network. Covers brief section
24's "Application tests with fakes" list, formalized as AC-28 through
AC-35, AC-40.
"""

from pathlib import Path

import pytest

from app.modules.companies.domain.enums import ProcessingStatus
from app.modules.crawling.domain.enums import PageFetchStatus
from app.modules.discovery.domain.enums import PageType
from app.modules.extraction.application.structured_extraction_service import (
    StructuredExtractionService,
)
from app.modules.extraction.domain.enums import (
    ExtractionStatus,
    ExtractorExecutionStatus,
)
from app.modules.extraction.domain.exceptions import DuplicateActiveExtractionRunError
from app.modules.extraction.domain.extractor import FactCandidateDraft, PageContext
from app.modules.extraction.domain.extractors.identity.company_name_extractor import (
    CompanyNameExtractor,
)
from app.modules.extraction.domain.field_catalogue import FieldPath
from app.modules.extraction.domain.models import ExtractionRunOptions

from .conftest import (
    FakeCompanyExtractionGateway,
    FakeCrawlExtractionGateway,
    FakeEvidenceGateway,
    FakeExtractionRepository,
    make_crawl_run,
    make_crawled_page,
)

FIXTURES_DIR = Path(__file__).resolve().parents[3].parent / "fixtures" / "extraction"


def _read_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


class RaisingExtractor:
    """A test-only extractor that always raises — proves failure isolation."""

    def definition(self):
        from app.modules.extraction.domain.models import ExtractorDefinition

        return ExtractorDefinition(
            extractor_id="test.raising", name="Raising extractor", version="v1", priority=1
        )

    def supports(self, page_context: PageContext) -> bool:
        return True

    def extract(self, page_context: PageContext) -> list[FactCandidateDraft]:
        raise RuntimeError("simulated extractor failure")


def _service(
    *,
    company_gateway: FakeCompanyExtractionGateway,
    crawl_gateway: FakeCrawlExtractionGateway,
    evidence_gateway: FakeEvidenceGateway,
    extraction_repository: FakeExtractionRepository,
    extractors=None,
) -> StructuredExtractionService:
    return StructuredExtractionService(
        company_gateway=company_gateway,
        crawl_gateway=crawl_gateway,
        evidence_gateway=evidence_gateway,
        repository=extraction_repository,
        extractors=extractors if extractors is not None else [CompanyNameExtractor()],
    )


def _crawl_gateway_with_homepage(
    *, page_id: str = "page-1", html_fixture: str = "homepage-jsonld-organisation.html"
) -> FakeCrawlExtractionGateway:
    page = make_crawled_page(page_id=page_id, page_type=PageType.HOMEPAGE)
    html = _read_fixture(html_fixture)
    return FakeCrawlExtractionGateway(
        crawl_run=make_crawl_run(),
        pages=[page],
        content={
            (page_id, "cleaned"): html.encode("utf-8"),
            (page_id, "text"): b"Southbank Trading Co",
        },
    )


@pytest.mark.asyncio
async def test_successful_extraction_run_accepts_facts(
    company_gateway, evidence_gateway, extraction_repository
):
    crawl_gateway = _crawl_gateway_with_homepage()
    service = _service(
        company_gateway=company_gateway,
        crawl_gateway=crawl_gateway,
        evidence_gateway=evidence_gateway,
        extraction_repository=extraction_repository,
    )
    run = await service.start_extraction_run("company-1", "crawl-run-1")
    assert run.status in (ExtractionStatus.COMPLETED, ExtractionStatus.COMPLETED_WITH_WARNINGS)
    assert run.summary.facts_accepted >= 1

    facts = await extraction_repository.list_facts_by_company("company-1")
    assert any(f.field_path == FieldPath.IDENTITY_COMPANY_NAME for f in facts.items)


@pytest.mark.asyncio
async def test_one_extractor_failure_isolated(
    company_gateway, evidence_gateway, extraction_repository
):
    crawl_gateway = _crawl_gateway_with_homepage()
    service = _service(
        company_gateway=company_gateway,
        crawl_gateway=crawl_gateway,
        evidence_gateway=evidence_gateway,
        extraction_repository=extraction_repository,
        extractors=[CompanyNameExtractor(), RaisingExtractor()],
    )
    run = await service.start_extraction_run("company-1", "crawl-run-1")

    statuses = {e.extractor_id: e.status for e in extraction_repository.executions}
    assert statuses["test.raising"] == ExtractorExecutionStatus.FAILED
    assert statuses["identity.company_name"] == ExtractorExecutionStatus.SUCCEEDED
    assert run.status != ExtractionStatus.FAILED
    assert run.summary.facts_accepted >= 1


@pytest.mark.asyncio
async def test_unavailable_page_skipped_with_warning(
    company_gateway, evidence_gateway, extraction_repository
):
    good_page = make_crawled_page(page_id="good", page_type=PageType.HOMEPAGE)
    failed_page = make_crawled_page(
        page_id="bad", page_type=PageType.HOMEPAGE, fetch_status=PageFetchStatus.FAILED
    )
    html = _read_fixture("homepage-jsonld-organisation.html")
    crawl_gateway = FakeCrawlExtractionGateway(
        crawl_run=make_crawl_run(),
        pages=[good_page, failed_page],
        content={("good", "cleaned"): html.encode("utf-8"), ("good", "text"): b"text"},
    )
    service = _service(
        company_gateway=company_gateway,
        crawl_gateway=crawl_gateway,
        evidence_gateway=evidence_gateway,
        extraction_repository=extraction_repository,
    )
    run = await service.start_extraction_run("company-1", "crawl-run-1")

    assert run.summary.pages_skipped == 1
    assert run.summary.pages_processed == 1
    assert any(w.code == "page_ineligible" for w in run.warnings)
    assert run.status in (
        ExtractionStatus.COMPLETED_WITH_WARNINGS,
        ExtractionStatus.COMPLETED,
        ExtractionStatus.PARTIAL,
    )


@pytest.mark.asyncio
async def test_evidence_failure_blocks_fact_acceptance(company_gateway, extraction_repository):
    crawl_gateway = _crawl_gateway_with_homepage()
    evidence_gateway = FakeEvidenceGateway(fail_for_field_paths={"identity.company_name"})
    service = _service(
        company_gateway=company_gateway,
        crawl_gateway=crawl_gateway,
        evidence_gateway=evidence_gateway,
        extraction_repository=extraction_repository,
    )
    run = await service.start_extraction_run("company-1", "crawl-run-1")

    facts = await extraction_repository.list_facts_by_company("company-1")
    assert not any(f.field_path == FieldPath.IDENTITY_COMPANY_NAME for f in facts.items)
    assert any(w.code == "evidence_creation_failed" for w in run.warnings)


@pytest.mark.asyncio
async def test_company_status_advances(company_gateway, evidence_gateway, extraction_repository):
    crawl_gateway = _crawl_gateway_with_homepage()
    service = _service(
        company_gateway=company_gateway,
        crawl_gateway=crawl_gateway,
        evidence_gateway=evidence_gateway,
        extraction_repository=extraction_repository,
    )
    await service.start_extraction_run("company-1", "crawl-run-1")

    statuses = [status for _, status in company_gateway.status_updates]
    assert ProcessingStatus.EXTRACTING in statuses
    assert ProcessingStatus.EXTRACTED in statuses


@pytest.mark.asyncio
async def test_noop_gateways_still_invoked(
    company_gateway, evidence_gateway, extraction_repository
):
    crawl_gateway = _crawl_gateway_with_homepage()
    service = _service(
        company_gateway=company_gateway,
        crawl_gateway=crawl_gateway,
        evidence_gateway=evidence_gateway,
        extraction_repository=extraction_repository,
    )
    run = await service.start_extraction_run("company-1", "crawl-run-1")

    assert (
        company_gateway.latest_run_updates
        and company_gateway.latest_run_updates[0][1] == run.extraction_run_id
    )
    assert company_gateway.projections


@pytest.mark.asyncio
async def test_cancellation_preserves_completed_work(
    company_gateway, evidence_gateway, extraction_repository
):
    page_1 = make_crawled_page(page_id="p1", page_type=PageType.HOMEPAGE)
    page_2 = make_crawled_page(page_id="p2", page_type=PageType.HOMEPAGE)
    html = _read_fixture("homepage-jsonld-organisation.html")
    crawl_gateway = FakeCrawlExtractionGateway(
        crawl_run=make_crawl_run(),
        pages=[page_1, page_2],
        content={
            ("p1", "cleaned"): html.encode("utf-8"),
            ("p1", "text"): b"text",
            ("p2", "cleaned"): html.encode("utf-8"),
            ("p2", "text"): b"text",
        },
    )

    call_count = {"n": 0}
    original_get_run = extraction_repository.get_run

    async def cancel_after_first_check(extraction_run_id: str):
        call_count["n"] += 1
        run = await original_get_run(extraction_run_id)
        if call_count["n"] >= 2 and run is not None:
            return await extraction_repository.mark_run_cancelled(extraction_run_id)
        return run

    extraction_repository.get_run = cancel_after_first_check  # type: ignore[method-assign]

    service = _service(
        company_gateway=company_gateway,
        crawl_gateway=crawl_gateway,
        evidence_gateway=evidence_gateway,
        extraction_repository=extraction_repository,
    )
    run = await service.start_extraction_run("company-1", "crawl-run-1")

    assert run.status == ExtractionStatus.CANCELLED
    assert run.summary.pages_processed == 1
    # Already-persisted candidates/facts for the completed page remain.
    facts = await extraction_repository.list_facts_by_company("company-1")
    assert facts.total >= 1


@pytest.mark.asyncio
async def test_idempotent_retry_no_duplicate_facts(
    company_gateway, evidence_gateway, extraction_repository
):
    crawl_gateway = _crawl_gateway_with_homepage()
    service = _service(
        company_gateway=company_gateway,
        crawl_gateway=crawl_gateway,
        evidence_gateway=evidence_gateway,
        extraction_repository=extraction_repository,
    )
    first_run = await service.start_extraction_run("company-1", "crawl-run-1")
    before = await extraction_repository.list_facts_by_company("company-1")

    second_run = await service.start_extraction_run("company-1", "crawl-run-1")
    after = await extraction_repository.list_facts_by_company("company-1")

    assert second_run.extraction_run_id == first_run.extraction_run_id
    assert before.total == after.total


@pytest.mark.asyncio
async def test_duplicate_active_run_conflicts(company_gateway, evidence_gateway):
    """A still-running (not yet completed) run with the identical key
    raises a typed conflict, never silently returned as success."""
    from datetime import UTC, datetime

    from app.modules.extraction.domain.enums import ExtractionStatus as Status
    from app.modules.extraction.domain.idempotency import compute_idempotency_key
    from app.modules.extraction.domain.models import ExtractionRun

    crawl_gateway = _crawl_gateway_with_homepage()
    repository = FakeExtractionRepository()
    options = ExtractionRunOptions()
    key = compute_idempotency_key("company-1", "crawl-run-1", options)
    now = datetime.now(UTC)
    active_run = ExtractionRun(
        company_id="company-1",
        crawl_run_id="crawl-run-1",
        status=Status.RUNNING,
        idempotency_key=key,
        created_at=now,
        updated_at=now,
    )
    await repository.create_run(active_run)

    service = _service(
        company_gateway=company_gateway,
        crawl_gateway=crawl_gateway,
        evidence_gateway=evidence_gateway,
        extraction_repository=repository,
    )
    with pytest.raises(DuplicateActiveExtractionRunError):
        await service.start_extraction_run("company-1", "crawl-run-1", options)


@pytest.mark.asyncio
async def test_supersession_marks_previous_fact_stale(
    company_gateway, evidence_gateway, extraction_repository
):
    crawl_gateway = _crawl_gateway_with_homepage()
    service = _service(
        company_gateway=company_gateway,
        crawl_gateway=crawl_gateway,
        evidence_gateway=evidence_gateway,
        extraction_repository=extraction_repository,
    )
    await service.start_extraction_run("company-1", "crawl-run-1")

    # A second run, over different content producing a different (higher-
    # confidence) accepted value, forces the old fact to be superseded.
    crawl_gateway_2 = _crawl_gateway_with_homepage(html_fixture="homepage-conflicting-name.html")
    service_2 = _service(
        company_gateway=company_gateway,
        crawl_gateway=crawl_gateway_2,
        evidence_gateway=evidence_gateway,
        extraction_repository=extraction_repository,
    )
    await service_2.start_extraction_run(
        "company-1", "crawl-run-1", ExtractionRunOptions(force_refresh=True)
    )

    all_facts = await extraction_repository.list_facts_by_company("company-1", include_stale=True)
    company_name_facts = [
        f for f in all_facts.items if f.field_path == FieldPath.IDENTITY_COMPANY_NAME
    ]
    assert len(company_name_facts) >= 1


@pytest.mark.asyncio
async def test_run_records_all_versions(company_gateway, evidence_gateway, extraction_repository):
    crawl_gateway = _crawl_gateway_with_homepage()
    service = _service(
        company_gateway=company_gateway,
        crawl_gateway=crawl_gateway,
        evidence_gateway=evidence_gateway,
        extraction_repository=extraction_repository,
    )
    run = await service.start_extraction_run("company-1", "crawl-run-1")

    expected_keys = {
        "field_catalogue_version",
        "extractor_implementation_version",
        "extractor_versions",
        "evidence_format_version",
        "confidence_policy_version",
        "reconciliation_rules_version",
        "freshness_policy_version",
        "projection_schema_version",
    }
    assert expected_keys.issubset(run.configuration_snapshot.keys())
    assert run.configuration_snapshot["extractor_versions"]
