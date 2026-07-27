"""Full-pipeline integration tests (brief section 25) — real extractors,
real `fixtures/extraction/` content, through a fake-gateway-backed
`StructuredExtractionService`. No live websites, no real MongoDB.
"""

from pathlib import Path

import pytest

from app.modules.crawling.domain.enums import PageFetchStatus
from app.modules.discovery.domain.enums import PageType
from app.modules.extraction.application.structured_extraction_service import (
    StructuredExtractionService,
)
from app.modules.extraction.domain.company_projection import build_projection
from app.modules.extraction.domain.extractors.business.business_model_extractor import (
    BusinessModelExtractor,
)
from app.modules.extraction.domain.extractors.identity.company_name_extractor import (
    CompanyNameExtractor,
)
from app.modules.extraction.domain.extractors.operations.operations_extractor import (
    OperationsExtractor,
)
from app.modules.extraction.domain.extractors.organisation.organisation_extractor import (
    OrganisationExtractor,
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


def _read(name: str) -> bytes:
    return (FIXTURES_DIR / name).read_bytes()


_PAGE_SPECS = [
    ("homepage", PageType.HOMEPAGE, "homepage-jsonld-organisation.html"),
    ("about", PageType.ABOUT, "about-team.html"),
    ("contact", PageType.CONTACT, "contact-address.html"),
    ("wholesale", PageType.WHOLESALE, "wholesale-explicit.html"),
    ("store-locator", PageType.STORE_LOCATOR, "store-locator-owned.html"),
    ("product", PageType.PRODUCT, "product-variants.html"),
]


def _build_pipeline_gateway() -> FakeCrawlExtractionGateway:
    pages = []
    content = {}
    for page_id, page_type, fixture_name in _PAGE_SPECS:
        pages.append(make_crawled_page(page_id=page_id, page_type=page_type))
        html = _read(fixture_name)
        content[(page_id, "cleaned")] = html
        content[(page_id, "text")] = html  # good enough for pattern-matching tests
    return FakeCrawlExtractionGateway(crawl_run=make_crawl_run(), pages=pages, content=content)


def _all_extractors():
    return [
        CompanyNameExtractor(),
        BusinessModelExtractor(),
        OrganisationExtractor(),
        OperationsExtractor(),
    ]


@pytest.mark.asyncio
async def test_full_extraction_across_page_types(
    company_gateway: FakeCompanyExtractionGateway,
    evidence_gateway: FakeEvidenceGateway,
    extraction_repository: FakeExtractionRepository,
):
    crawl_gateway = _build_pipeline_gateway()
    service = StructuredExtractionService(
        company_gateway=company_gateway,
        crawl_gateway=crawl_gateway,
        evidence_gateway=evidence_gateway,
        repository=extraction_repository,
        extractors=_all_extractors(),
    )
    run = await service.start_extraction_run("company-1", "crawl-run-1")
    assert run.summary.pages_processed == len(_PAGE_SPECS)
    assert run.summary.facts_accepted > 0

    facts = await extraction_repository.list_facts_by_company("company-1")
    field_paths = {f.field_path for f in facts.items}
    assert FieldPath.IDENTITY_COMPANY_NAME in field_paths
    assert FieldPath.BUSINESS_WHOLESALE in field_paths
    assert FieldPath.OPERATIONS_LOCATIONS in field_paths


@pytest.mark.asyncio
async def test_evidence_linked_to_facts(company_gateway, evidence_gateway, extraction_repository):
    crawl_gateway = _build_pipeline_gateway()
    service = StructuredExtractionService(
        company_gateway=company_gateway,
        crawl_gateway=crawl_gateway,
        evidence_gateway=evidence_gateway,
        repository=extraction_repository,
        extractors=_all_extractors(),
    )
    await service.start_extraction_run("company-1", "crawl-run-1")

    facts = await extraction_repository.list_facts_by_company("company-1")
    for fact in facts.items:
        assert fact.evidence_ids
        for evidence_id in fact.evidence_ids:
            evidence = await evidence_gateway.get_evidence(evidence_id)
            assert evidence is not None
            assert evidence.page_id


@pytest.mark.asyncio
async def test_company_projection_generated(
    company_gateway, evidence_gateway, extraction_repository
):
    crawl_gateway = _build_pipeline_gateway()
    service = StructuredExtractionService(
        company_gateway=company_gateway,
        crawl_gateway=crawl_gateway,
        evidence_gateway=evidence_gateway,
        repository=extraction_repository,
        extractors=_all_extractors(),
    )
    await service.start_extraction_run("company-1", "crawl-run-1")

    facts = await extraction_repository.list_facts_by_company("company-1")
    projection = build_projection(facts.items)
    assert projection.identity or projection.business or projection.operations
    assert company_gateway.projections
    assert company_gateway.projections[-1][0] == "company-1"


@pytest.mark.asyncio
async def test_retry_without_duplicate_facts(
    company_gateway, evidence_gateway, extraction_repository
):
    crawl_gateway = _build_pipeline_gateway()
    service = StructuredExtractionService(
        company_gateway=company_gateway,
        crawl_gateway=crawl_gateway,
        evidence_gateway=evidence_gateway,
        repository=extraction_repository,
        extractors=_all_extractors(),
    )
    await service.start_extraction_run("company-1", "crawl-run-1")
    before = await extraction_repository.list_facts_by_company("company-1")

    await service.start_extraction_run("company-1", "crawl-run-1")
    after = await extraction_repository.list_facts_by_company("company-1")

    assert before.total == after.total


@pytest.mark.asyncio
async def test_changed_page_content_creates_new_evidence_and_supersedes_fact(
    company_gateway, evidence_gateway, extraction_repository
):
    page = make_crawled_page(page_id="homepage", page_type=PageType.HOMEPAGE)
    crawl_gateway = FakeCrawlExtractionGateway(
        crawl_run=make_crawl_run(),
        pages=[page],
        content={
            ("homepage", "cleaned"): _read("homepage-jsonld-organisation.html"),
            ("homepage", "text"): b"text",
        },
    )
    service = StructuredExtractionService(
        company_gateway=company_gateway,
        crawl_gateway=crawl_gateway,
        evidence_gateway=evidence_gateway,
        repository=extraction_repository,
        extractors=[CompanyNameExtractor()],
    )
    await service.start_extraction_run("company-1", "crawl-run-1")
    first_fact = await extraction_repository.get_latest_fact(
        "company-1", FieldPath.IDENTITY_COMPANY_NAME
    )
    assert first_fact is not None
    first_evidence_ids = set(first_fact.evidence_ids)

    # Page content changes — a different company name now appears.
    crawl_gateway_changed = FakeCrawlExtractionGateway(
        crawl_run=make_crawl_run(),
        pages=[page],
        content={
            ("homepage", "cleaned"): _read("homepage-shopify.html"),
            ("homepage", "text"): b"text-changed",
        },
    )
    service_2 = StructuredExtractionService(
        company_gateway=company_gateway,
        crawl_gateway=crawl_gateway_changed,
        evidence_gateway=evidence_gateway,
        repository=extraction_repository,
        extractors=[CompanyNameExtractor()],
    )
    await service_2.start_extraction_run(
        "company-1", "crawl-run-1", ExtractionRunOptions(force_refresh=True)
    )

    second_fact = await extraction_repository.get_latest_fact(
        "company-1", FieldPath.IDENTITY_COMPANY_NAME
    )
    assert second_fact is not None
    assert set(second_fact.evidence_ids) != first_evidence_ids

    all_facts = await extraction_repository.list_facts_by_company("company-1", include_stale=True)
    company_name_facts = [
        f for f in all_facts.items if f.field_path == FieldPath.IDENTITY_COMPANY_NAME
    ]
    assert len(company_name_facts) == 2


@pytest.mark.asyncio
async def test_unchanged_page_still_extracted(
    company_gateway, evidence_gateway, extraction_repository
):
    # `predecessor` (page_id="predecessor") deliberately isn't constructed
    # as its own `CrawledPage` object here — only its `page_id` is
    # referenced, since `load_page_content` below is stubbed directly.
    unchanged = make_crawled_page(
        page_id="unchanged-page",
        page_type=PageType.HOMEPAGE,
        fetch_status=PageFetchStatus.UNCHANGED,
        unchanged_from_page_id="predecessor",
    )
    html = _read("homepage-jsonld-organisation.html")
    crawl_gateway = FakeCrawlExtractionGateway(
        crawl_run=make_crawl_run(),
        pages=[unchanged],  # note: `predecessor` deliberately not listed by `list_pages`
        content={("predecessor", "cleaned"): html, ("predecessor", "text"): b"text"},
    )

    async def load_page_content(page_id: str, content_kind: str):
        if page_id == "unchanged-page":
            page_id = "predecessor"  # gateway resolution — see resolution #1
        return crawl_gateway._content.get((page_id, content_kind))

    crawl_gateway.load_page_content = load_page_content  # type: ignore[method-assign]

    service = StructuredExtractionService(
        company_gateway=company_gateway,
        crawl_gateway=crawl_gateway,
        evidence_gateway=evidence_gateway,
        repository=extraction_repository,
        extractors=[CompanyNameExtractor()],
    )
    run = await service.start_extraction_run("company-1", "crawl-run-1")
    assert run.summary.pages_processed == 1
    fact = await extraction_repository.get_latest_fact("company-1", FieldPath.IDENTITY_COMPANY_NAME)
    assert fact is not None
