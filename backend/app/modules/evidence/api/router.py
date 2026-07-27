"""HTTP routes for the evidence module.

Built but **not** centrally registered in `backend/app/main.py` — a
required, out-of-allowed-paths integration step, mirroring
`modules/imports`/`modules/discovery`/`modules/crawling`'s already-
unregistered routers.

`get_evidence_service` is deliberately public (not underscore-prefixed) —
`modules/extraction`'s `EvidenceServiceExtractionGateway` adapter imports
it directly, the identical "import the other module's own public DI
function" shape every other cross-module gateway in this repository uses.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db import get_database
from app.modules.evidence.api.schemas import EvidenceEnvelope, evidence_to_response
from app.modules.evidence.application.evidence_service import EvidenceService
from app.modules.evidence.domain.exceptions import EvidenceNotFoundError
from app.modules.evidence.domain.repository import EvidenceRepository
from app.modules.evidence.infrastructure.mongo_evidence_repository import MongoEvidenceRepository

router = APIRouter(tags=["evidence"])


def get_evidence_repository(
    database: AsyncIOMotorDatabase = Depends(get_database),
) -> EvidenceRepository:
    return MongoEvidenceRepository(database)


def get_evidence_service(
    repository: EvidenceRepository = Depends(get_evidence_repository),
) -> EvidenceService:
    return EvidenceService(repository)


@router.get("/api/evidence/{evidence_id}", response_model=EvidenceEnvelope)
async def get_evidence(
    evidence_id: str,
    service: EvidenceService = Depends(get_evidence_service),
) -> EvidenceEnvelope:
    try:
        evidence = await service.get_evidence(evidence_id)
    except EvidenceNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    return EvidenceEnvelope(data=evidence_to_response(evidence))
