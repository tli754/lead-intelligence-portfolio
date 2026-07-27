"""API tests for the evidence module (AC-38) — a locally-scoped `FastAPI()`
app containing only this module's router, never `app.main.app` (the
evidence router is deliberately not registered there)."""

from collections.abc import AsyncGenerator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.modules.evidence.api.router import get_evidence_repository, router
from app.modules.evidence.domain.repository import EvidenceRepository

from .conftest import FakeEvidenceRepository, make_evidence_record


def _build_app(repository: EvidenceRepository) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_evidence_repository] = lambda: repository
    return app


@pytest.fixture
async def client(evidence_repository: FakeEvidenceRepository) -> AsyncGenerator[AsyncClient, None]:
    app = _build_app(evidence_repository)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client


@pytest.mark.asyncio
async def test_get_evidence_is_camel_case_and_capped(
    client: AsyncClient, evidence_repository: FakeEvidenceRepository
):
    record = make_evidence_record()
    await evidence_repository.save_evidence(record)

    response = await client.get(f"/api/evidence/{record.evidence_id}")
    assert response.status_code == 200
    body = response.json()
    assert "evidenceId" in body["data"]
    assert "factFieldPath" in body["data"]
    assert len(body["data"]["excerpt"]["text"]) <= 300


@pytest.mark.asyncio
async def test_get_missing_evidence_returns_404(client: AsyncClient):
    response = await client.get("/api/evidence/missing-id")
    assert response.status_code == 404
