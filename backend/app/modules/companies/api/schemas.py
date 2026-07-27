"""Request/response DTOs for the companies-module HTTP API.

All JSON crossing this boundary is camelCase, via a shared
`alias_generator`. Kept separate from the domain `Company` model —
camelCase aliasing is an API-layer concern, not a domain one — so a
mapper (`company_to_response`/`company_to_list_item`) translates between
them.
"""

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.modules.companies.domain.enums import ProcessingStatus, WorkflowStatus
from app.modules.companies.domain.models import Company


class CamelCaseModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class CreateCompanyRequest(CamelCaseModel):
    domain: str = Field(min_length=1)
    company_name: str | None = None
    platform: str | None = None
    country: str | None = None
    city: str | None = None


class UpdateProcessingStatusRequest(CamelCaseModel):
    status: ProcessingStatus


class UpdateWorkflowStatusRequest(CamelCaseModel):
    status: WorkflowStatus


class CompanyIdentityResponse(CamelCaseModel):
    company_name: str | None
    platform: str | None
    country: str | None
    city: str | None


class CompanyProcessingResponse(CamelCaseModel):
    status: ProcessingStatus
    latest_discovery_run_id: str | None
    latest_crawl_run_id: str | None
    latest_extraction_run_id: str | None
    latest_analysis_run_id: str | None
    latest_scoring_run_id: str | None


class CompanyWorkflowResponse(CamelCaseModel):
    manual_status: WorkflowStatus
    shortlisted: bool
    notes_count: int


class CompanyResponse(CamelCaseModel):
    """Full company detail — the response for create/get/patch endpoints."""

    company_id: str
    domain: str
    normalized_domain: str
    identity: CompanyIdentityResponse
    processing: CompanyProcessingResponse
    workflow: CompanyWorkflowResponse
    created_at: str
    updated_at: str
    document_version: int


class CompanyListItemResponse(CamelCaseModel):
    """The flattened list projection returned by `GET /api/companies`."""

    company_id: str
    company_name: str | None
    domain: str
    platform: str | None
    country: str | None
    city: str | None
    opportunity_score: float | None
    confidence: str | None
    main_reason: str | None
    processing_status: ProcessingStatus
    workflow_status: WorkflowStatus
    updated_at: str


class PaginationMeta(CamelCaseModel):
    page: int
    page_size: int
    total: int


class CompanyListResponse(CamelCaseModel):
    data: list[CompanyListItemResponse]
    pagination: PaginationMeta


def company_to_response(company: Company) -> CompanyResponse:
    return CompanyResponse(
        company_id=company.company_id,
        domain=company.domain,
        normalized_domain=company.normalized_domain,
        identity=CompanyIdentityResponse(**company.identity.model_dump()),
        processing=CompanyProcessingResponse(**company.processing.model_dump()),
        workflow=CompanyWorkflowResponse(**company.workflow.model_dump()),
        created_at=company.created_at.isoformat(),
        updated_at=company.updated_at.isoformat(),
        document_version=company.document_version,
    )


def company_to_list_item(company: Company) -> CompanyListItemResponse:
    """Maps a domain `Company` to the list projection.

    `opportunity_score`/`confidence`/`main_reason` are always `None` —
    scoring hasn't been implemented yet (see task constraints), so these
    stay permanent nulls at the API layer rather than becoming
    placeholder fields on the domain model.
    """
    return CompanyListItemResponse(
        company_id=company.company_id,
        company_name=company.identity.company_name,
        domain=company.domain,
        platform=company.identity.platform,
        country=company.identity.country,
        city=company.identity.city,
        opportunity_score=None,
        confidence=None,
        main_reason=None,
        processing_status=company.processing.status,
        workflow_status=company.workflow.manual_status,
        updated_at=company.updated_at.isoformat(),
    )
