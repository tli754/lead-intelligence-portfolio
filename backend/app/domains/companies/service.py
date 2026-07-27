"""Business logic for importing companies from a paste.

Owns all business rules: format detection, parsing orchestration,
in-paste dedupe, DB-existing dedupe, and persistence orchestration. The
router never makes these decisions, and the repository never makes them
either.
"""

from datetime import UTC, datetime
from typing import Protocol

from app.domains.companies.models import Company, CompanySource, ImportResponse
from app.domains.companies.parsing import (
    ParsedRows,
    detect_format,
    parse_domain_list,
    parse_storeleads_html,
)

_SOURCE_BY_FORMAT: dict[str, CompanySource] = {
    "domain_list": "paste_domain_list",
    "storeleads_html": "paste_storeleads_html",
}


class CompanyRepositoryProtocol(Protocol):
    """The subset of CompanyRepository's interface the service depends on.

    Defined as a Protocol (structural typing) so unit tests can pass a
    lightweight fake repository without inheriting from the real
    MongoDB-backed CompanyRepository.
    """

    async def get_existing_domains(self, domains: list[str]) -> set[str]: ...

    async def insert_many(self, companies: list[Company]) -> list[Company]: ...


class CompanyImportService:
    """Orchestrates turning a raw paste into stored `Company` documents."""

    def __init__(self, repository: CompanyRepositoryProtocol) -> None:
        self._repository = repository

    async def import_companies(self, raw_text: str) -> ImportResponse:
        detected_format = detect_format(raw_text)
        source: CompanySource = _SOURCE_BY_FORMAT[detected_format]

        parsed: ParsedRows = (
            parse_storeleads_html(raw_text)
            if detected_format == "storeleads_html"
            else parse_domain_list(raw_text)
        )

        total_rows_detected = (
            len(parsed.rows) + len(parsed.skipped_duplicate_in_paste) + len(parsed.skipped_invalid)
        )

        candidate_domains = [row.domain for row in parsed.rows]
        existing_domains = await self._repository.get_existing_domains(candidate_domains)

        skipped_existing_in_db: list[str] = []
        companies_to_insert: list[Company] = []
        imported_at = datetime.now(UTC)

        for row in parsed.rows:
            if row.domain in existing_domains:
                skipped_existing_in_db.append(row.domain)
                continue
            companies_to_insert.append(
                Company(
                    domain=row.domain,
                    source=source,
                    url=row.url,
                    estimated_sales_yearly_usd=row.estimated_sales_yearly_usd,
                    source_created_at=row.source_created_at,
                    emails=row.emails,
                    phones=row.phones,
                    imported_at=imported_at,
                )
            )

        created = await self._repository.insert_many(companies_to_insert)

        return ImportResponse(
            detected_format=detected_format,
            total_rows_detected=total_rows_detected,
            created=created,
            created_count=len(created),
            skipped_duplicate_in_paste=parsed.skipped_duplicate_in_paste,
            skipped_existing_in_db=skipped_existing_in_db,
            skipped_invalid=parsed.skipped_invalid,
        )
