"""Import: actually create companies for valid, new rows.

Company creation only ever happens through `CompanyImportGateway` —
never MongoDB directly.
"""

from app.modules.imports.application.preview_service import ImportPreviewService
from app.modules.imports.domain.enums import (
    DuplicateStatus,
    ImportRowOutcome,
    ImportSource,
    ValidationStatus,
)
from app.modules.imports.domain.gateway import CompanyAlreadyExistsError, CompanyImportGateway
from app.modules.imports.domain.models import ImportResult, ImportRow


class ImportService:
    """Imports valid, new rows from raw StoreLeads HTML.

    Safe to retry: each row's creation goes through `gateway.create_imported_company`,
    which raises a typed `CompanyAlreadyExistsError` on a duplicate domain
    (backed, in the real adapter, by MongoDB's unique index) — so running
    the same file twice creates nothing the second time, regardless of
    what a prior preview predicted.
    """

    def __init__(self, gateway: CompanyImportGateway) -> None:
        self._gateway = gateway
        self._preview_service = ImportPreviewService(gateway)

    async def import_storeleads_html(self, html: str) -> ImportResult:
        preview = await self._preview_service.preview_storeleads_html(html)

        created = 0
        skipped_existing = 0
        skipped_invalid = 0
        failed = 0
        result_rows: list[ImportRow] = []

        for row in preview.rows:
            if row.validation_status == ValidationStatus.INVALID:
                skipped_invalid += 1
                result_rows.append(
                    row.model_copy(update={"outcome": ImportRowOutcome.SKIPPED_INVALID})
                )
                continue

            if row.duplicate_status == DuplicateStatus.DUPLICATE_IN_FILE:
                # Already seen earlier in this same file — the first
                # occurrence was (or will be) attempted; skip this repeat
                # without a second gateway call.
                skipped_existing += 1
                result_rows.append(
                    row.model_copy(update={"outcome": ImportRowOutcome.SKIPPED_EXISTING})
                )
                continue

            assert row.normalized_domain is not None  # guaranteed by validation_status == VALID

            try:
                await self._gateway.create_imported_company(
                    normalized_domain=row.normalized_domain,
                    platform=row.platform,
                    country=row.country,
                    city=row.city,
                )
            except CompanyAlreadyExistsError:
                skipped_existing += 1
                result_rows.append(
                    row.model_copy(
                        update={
                            "outcome": ImportRowOutcome.SKIPPED_EXISTING,
                            "duplicate_status": DuplicateStatus.EXISTING,
                        }
                    )
                )
            except Exception:
                # Deliberately broad: one bad row must not fail the whole batch.
                failed += 1
                result_rows.append(row.model_copy(update={"outcome": ImportRowOutcome.FAILED}))
            else:
                created += 1
                result_rows.append(
                    row.model_copy(
                        update={
                            "outcome": ImportRowOutcome.CREATED,
                            "duplicate_status": DuplicateStatus.NEW,
                        }
                    )
                )

        return ImportResult(
            source=ImportSource.STORELEADS_HTML,
            created=created,
            skipped_existing=skipped_existing,
            skipped_invalid=skipped_invalid,
            failed=failed,
            rows=result_rows,
        )
