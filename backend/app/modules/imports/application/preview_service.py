"""Preview: parse + validate + detect duplicates, without writing anything."""

from app.modules.imports.domain.enums import DuplicateStatus, ImportSource, ValidationStatus
from app.modules.imports.domain.format_detector import detect_storeleads_format
from app.modules.imports.domain.gateway import CompanyImportGateway
from app.modules.imports.domain.models import ImportBatchSummary, ImportPreview, ImportRow
from app.modules.imports.domain.row_builder import build_import_row
from app.modules.imports.domain.storeleads_html_parser import (
    RawStoreLeadsRow,
    parse_storeleads_table,
)
from app.modules.imports.domain.vaadin_grid_parser import parse_storeleads_vaadin_grid

_FORMAT_SOURCES: dict[str, ImportSource] = {
    "table": ImportSource.STORELEADS_HTML,
    "vaadin_grid": ImportSource.STORELEADS_VAADIN_GRID,
}


def _parse_raw_rows(html: str) -> tuple[list[RawStoreLeadsRow], ImportSource]:
    detected_format = detect_storeleads_format(html)
    if detected_format == "vaadin_grid":
        return parse_storeleads_vaadin_grid(html), _FORMAT_SOURCES[detected_format]
    return parse_storeleads_table(html), _FORMAT_SOURCES[detected_format]


def _build_summary(rows: list[ImportRow]) -> ImportBatchSummary:
    valid_rows = [row for row in rows if row.validation_status == ValidationStatus.VALID]
    existing_companies = sum(1 for row in rows if row.duplicate_status == DuplicateStatus.EXISTING)
    duplicate_rows_in_file = sum(
        1 for row in rows if row.duplicate_status == DuplicateStatus.DUPLICATE_IN_FILE
    )
    return ImportBatchSummary(
        rows_found=len(rows),
        valid_rows=len(valid_rows),
        invalid_rows=len(rows) - len(valid_rows),
        existing_companies=existing_companies,
        duplicate_rows_in_file=duplicate_rows_in_file,
        # Rows the gateway couldn't classify (`unknown`) are still counted
        # as importable — the import step will attempt them regardless,
        # and correctness there doesn't depend on the preview's guess.
        importable_rows=len(valid_rows) - existing_companies - duplicate_rows_in_file,
    )


class ImportPreviewService:
    """Never writes to MongoDB — read-only by construction (only calls
    `gateway.exists_by_domain`, never `create_imported_company`)."""

    def __init__(self, gateway: CompanyImportGateway) -> None:
        self._gateway = gateway

    async def preview_storeleads_html(self, html: str) -> ImportPreview:
        raw_rows, source = _parse_raw_rows(html)

        rows: list[ImportRow] = []
        seen_at_row: dict[str, int] = {}

        for row_number, raw in enumerate(raw_rows, start=1):
            row = build_import_row(row_number, raw)

            if row.validation_status == ValidationStatus.VALID and row.normalized_domain:
                if row.normalized_domain in seen_at_row:
                    row = row.model_copy(
                        update={"duplicate_status": DuplicateStatus.DUPLICATE_IN_FILE}
                    )
                else:
                    seen_at_row[row.normalized_domain] = row_number
                    exists = await self._gateway.exists_by_domain(row.normalized_domain)
                    duplicate_status = (
                        DuplicateStatus.EXISTING
                        if exists is True
                        else DuplicateStatus.NEW
                        if exists is False
                        else DuplicateStatus.UNKNOWN
                    )
                    row = row.model_copy(update={"duplicate_status": duplicate_status})

            rows.append(row)

        return ImportPreview(
            source=source,
            summary=_build_summary(rows),
            rows=rows,
        )
