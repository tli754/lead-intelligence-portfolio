from datetime import UTC, datetime

from app.modules.companies.api.schemas import (
    CompanyListResponse,
    PaginationMeta,
    company_to_list_item,
    company_to_response,
)
from app.modules.companies.domain.models import Company, CompanyIdentity


def _company() -> Company:
    now = datetime.now(UTC)
    return Company(
        domain="example.com",
        normalized_domain="example.com",
        identity=CompanyIdentity(company_name="Example", platform="Shopify"),
        created_at=now,
        updated_at=now,
    )


class TestCompanyResponseSerialization:
    def test_serializes_with_camel_case_keys(self) -> None:
        response = company_to_response(_company())
        body = response.model_dump(by_alias=True)

        assert "companyId" in body
        assert "normalizedDomain" in body
        assert "documentVersion" in body
        assert "createdAt" in body
        assert "updatedAt" in body
        assert body["processing"]["status"] == "imported"
        assert "manualStatus" in body["workflow"]
        # snake_case keys must not leak into the camelCase response.
        assert "company_id" not in body
        assert "normalized_domain" not in body


class TestCompanyListItemSerialization:
    def test_serializes_with_camel_case_keys_and_null_scoring_fields(self) -> None:
        company = _company()
        item = company_to_list_item(company)
        body = item.model_dump(by_alias=True)

        assert body["companyId"]
        assert body["companyName"] == "Example"
        assert body["platform"] == "Shopify"
        assert body["processingStatus"] == "imported"
        assert body["workflowStatus"] == "unreviewed"
        # Scoring hasn't been implemented yet — these stay null.
        assert body["opportunityScore"] is None
        assert body["confidence"] is None
        assert body["mainReason"] is None
        assert body["updatedAt"] == company.updated_at.isoformat()


class TestPaginationMetaSerialization:
    def test_serializes_with_camel_case_keys(self) -> None:
        pagination = PaginationMeta(page=2, page_size=20, total=43)
        body = pagination.model_dump(by_alias=True)

        assert body == {"page": 2, "pageSize": 20, "total": 43}

    def test_list_response_envelope_shape(self) -> None:
        item = company_to_list_item(_company())
        envelope = CompanyListResponse(
            data=[item], pagination=PaginationMeta(page=1, page_size=20, total=1)
        )
        body = envelope.model_dump(by_alias=True)

        assert set(body.keys()) == {"data", "pagination"}
        assert len(body["data"]) == 1
        assert body["pagination"]["pageSize"] == 20
