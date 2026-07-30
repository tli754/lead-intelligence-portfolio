"""API tests for the extraction module (AC-38, AC-39) — a locally-scoped
`FastAPI()` app containing only this module's router, never
`app.main.app` (the extraction router is deliberately not registered
there)."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.modules.extraction.api.router import get_extraction_repository, router
from app.modules.extraction.domain.enums import FactStatus, VerificationState
from app.modules.extraction.domain.field_catalogue import FieldPath, FieldValueType
from app.modules.extraction.domain.models import FactRecord

from .conftest import FakeExtractionRepository

NOW = datetime(2026, 7, 26, tzinfo=UTC)


def _fact(**overrides: Any) -> FactRecord:
    defaults: dict[str, Any] = dict(
        company_id="company-1",
        extraction_run_id="run-1",
        field_path=FieldPath.IDENTITY_COMPANY_NAME,
        value="Acme",
        normalized_value="Acme",
        value_type=FieldValueType.STRING,
        status=FactStatus.ACCEPTED,
        verification_state=VerificationState.VERIFIED,
        confidence=80,
        first_observed_at=NOW,
        last_observed_at=NOW,
        last_verified_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    defaults.update(overrides)
    return FactRecord(**defaults)


def _build_app(repository: FakeExtractionRepository) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_extraction_repository] = lambda: repository
    return app


@pytest.fixture
async def client(
    extraction_repository: FakeExtractionRepository,
) -> AsyncGenerator[AsyncClient, None]:
    app = _build_app(extraction_repository)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client


@pytest.mark.asyncio
async def test_company_facts_response_is_camel_case(client: AsyncClient, extraction_repository):
    await extraction_repository.save_facts([_fact()])
    response = await client.get("/api/companies/company-1/facts")
    assert response.status_code == 200
    body = response.json()
    assert "fieldPath" in body["data"][0]
    assert "normalizedValue" in body["data"][0]
    assert "field_path" not in body["data"][0]


@pytest.mark.asyncio
async def test_no_full_html_in_any_response(client: AsyncClient, extraction_repository):
    await extraction_repository.save_facts([_fact()])
    response = await client.get("/api/companies/company-1/facts")
    assert "<html" not in response.text.lower()


@pytest.mark.asyncio
async def test_unknown_and_false_never_conflated(client: AsyncClient, extraction_repository):
    false_fact = _fact(
        field_path=FieldPath.BUSINESS_WHOLESALE,
        value=False,
        normalized_value=False,
        value_type=FieldValueType.BOOLEAN,
    )
    await extraction_repository.save_facts([false_fact])
    response = await client.get("/api/companies/company-1/facts")
    body = response.json()
    wholesale = next(item for item in body["data"] if item["fieldPath"] == "business.wholesale")
    assert wholesale["value"] is False
    assert wholesale["normalizedValue"] is False


@pytest.mark.asyncio
async def test_estimate_metadata_present_where_applicable(
    client: AsyncClient, extraction_repository
):
    estimate_fact = _fact(
        field_path=FieldPath.CATALOGUE_PRODUCT_COUNT_ESTIMATE,
        value=100,
        normalized_value=100,
        value_type=FieldValueType.INTEGER,
        verification_state=VerificationState.INFERRED,
        qualifiers={"estimation_method": "sampled_collection", "sample_size": 8},
    )
    await extraction_repository.save_facts([estimate_fact])
    response = await client.get("/api/companies/company-1/facts")
    body = response.json()
    item = next(i for i in body["data"] if i["fieldPath"] == "catalogue.product_count_estimate")
    assert item["estimationMethod"] == "sampled_collection"
    assert item["sampleSize"] == 8


@pytest.mark.asyncio
async def test_fact_list_filters(client: AsyncClient, extraction_repository):
    await extraction_repository.save_facts(
        [
            _fact(field_path=FieldPath.IDENTITY_COMPANY_NAME, confidence=90),
            _fact(
                field_path=FieldPath.BUSINESS_WHOLESALE,
                value=True,
                normalized_value=True,
                value_type=FieldValueType.BOOLEAN,
                confidence=60,
            ),
        ]
    )
    response = await client.get(
        "/api/companies/company-1/facts", params={"fieldPath": "identity.company_name"}
    )
    body = response.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["fieldPath"] == "identity.company_name"

    response = await client.get("/api/companies/company-1/facts", params={"minimumConfidence": 80})
    body = response.json()
    assert all(item["confidence"] >= 80 for item in body["data"])


@pytest.mark.asyncio
async def test_get_fact_by_id(client: AsyncClient, extraction_repository):
    fact = _fact()
    await extraction_repository.save_facts([fact])
    response = await client.get(f"/api/facts/{fact.fact_id}")
    assert response.status_code == 200
    assert response.json()["data"]["factId"] == fact.fact_id


@pytest.mark.asyncio
async def test_get_fact_not_found_returns_404(client: AsyncClient):
    response = await client.get("/api/facts/missing-id")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_extraction_runs_response_shape_and_pagination(
    client: AsyncClient, extraction_repository: FakeExtractionRepository
):
    from app.modules.extraction.domain.models import ExtractionRun

    await extraction_repository.create_run(
        ExtractionRun(
            company_id="company-1",
            crawl_run_id="crawl-run-1",
            idempotency_key="key-a",
            created_at=NOW,
            updated_at=NOW,
        )
    )

    response = await client.get("/api/extraction-runs", params={"page": 1, "pageSize": 10})

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {"data", "pagination"}
    assert set(body["pagination"].keys()) == {"page", "pageSize", "total"}
    assert body["pagination"]["total"] == 1
    assert "extractionRunId" in body["data"][0]


@pytest.mark.asyncio
async def test_list_extraction_runs_status_filter(
    client: AsyncClient, extraction_repository: FakeExtractionRepository
):
    from app.modules.extraction.domain.enums import ExtractionStatus
    from app.modules.extraction.domain.models import ExtractionRun

    await extraction_repository.create_run(
        ExtractionRun(
            company_id="company-1",
            crawl_run_id="crawl-run-1",
            status=ExtractionStatus.COMPLETED,
            idempotency_key="key-a",
            created_at=NOW,
            updated_at=NOW,
        )
    )
    await extraction_repository.create_run(
        ExtractionRun(
            company_id="company-1",
            crawl_run_id="crawl-run-1",
            status=ExtractionStatus.FAILED,
            idempotency_key="key-b",
            created_at=NOW,
            updated_at=NOW,
        )
    )

    matching = await client.get("/api/extraction-runs", params={"status": "failed"})
    assert matching.json()["pagination"]["total"] == 1
    assert matching.json()["data"][0]["status"] == "failed"

    non_matching = await client.get("/api/extraction-runs", params={"status": "cancelled"})
    assert non_matching.json()["pagination"]["total"] == 0
    assert non_matching.json()["data"] == []


@pytest.mark.asyncio
async def test_create_extraction_run_conflict_returns_409(
    client: AsyncClient, extraction_repository, company_gateway, crawl_gateway, evidence_gateway
):
    from app.modules.extraction.api.router import (
        get_company_extraction_gateway,
        get_crawl_extraction_gateway,
        get_evidence_extraction_gateway,
    )
    from app.modules.extraction.domain.enums import ExtractionStatus
    from app.modules.extraction.domain.idempotency import compute_idempotency_key
    from app.modules.extraction.domain.models import ExtractionRun, ExtractionRunOptions

    app = _build_app(extraction_repository)
    app.dependency_overrides[get_company_extraction_gateway] = lambda: company_gateway
    app.dependency_overrides[get_crawl_extraction_gateway] = lambda: crawl_gateway
    app.dependency_overrides[get_evidence_extraction_gateway] = lambda: evidence_gateway

    key = compute_idempotency_key("company-1", "crawl-run-1", ExtractionRunOptions())
    active_run = ExtractionRun(
        company_id="company-1",
        crawl_run_id="crawl-run-1",
        status=ExtractionStatus.RUNNING,
        idempotency_key=key,
        created_at=NOW,
        updated_at=NOW,
    )
    await extraction_repository.create_run(active_run)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        response = await test_client.post(
            "/api/companies/company-1/extraction-runs", json={"crawlRunId": "crawl-run-1"}
        )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_fact_evidence_list_filters(extraction_repository):
    from app.modules.evidence.api.router import get_evidence_service
    from app.modules.evidence.application.evidence_service import EvidenceService
    from tests.integration.evidence.conftest import FakeEvidenceRepository, make_evidence_record

    fact = _fact(evidence_ids=["e1", "e2"])
    await extraction_repository.save_facts([fact])

    evidence_repository = FakeEvidenceRepository()
    e1 = make_evidence_record(evidence_id="e1", page_id="page-a")
    e2 = make_evidence_record(evidence_id="e2", page_id="page-b")
    await evidence_repository.save_evidence(e1)
    await evidence_repository.save_evidence(e2)

    app = _build_app(extraction_repository)
    app.dependency_overrides[get_evidence_service] = lambda: EvidenceService(evidence_repository)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        response = await test_client.get(f"/api/facts/{fact.fact_id}/evidence")
        assert response.status_code == 200
        body = response.json()
        assert body["pagination"]["total"] == 2

        filtered = await test_client.get(
            f"/api/facts/{fact.fact_id}/evidence", params={"pageId": "page-a"}
        )
        filtered_body = filtered.json()
        assert filtered_body["pagination"]["total"] == 1
        assert filtered_body["data"][0]["evidenceId"] == "e1"
