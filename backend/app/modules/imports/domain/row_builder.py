"""Builds a validated `ImportRow` from a raw parsed row.

Pure — no FastAPI or MongoDB imports. Never raises for ordinary bad data;
problems become structured `ImportRowError`s on the row instead.
"""

from app.modules.imports.domain.enums import DuplicateStatus, ValidationStatus
from app.modules.imports.domain.models import ImportRow, ImportRowError
from app.modules.imports.domain.platform_normalizer import normalize_platform
from app.modules.imports.domain.storeleads_html_parser import RawStoreLeadsRow
from app.modules.imports.domain.website_normalizer import (
    WebsiteNormalizationError,
    normalize_website,
)


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def build_import_row(row_number: int, raw: RawStoreLeadsRow) -> ImportRow:
    """Validates and normalizes one raw row.

    `duplicate_status` is left as `unknown` here — duplicate detection
    needs visibility across the whole file (and optionally a Company
    lookup), which is the preview/import service's job, not this
    per-row function's.
    """
    errors: list[ImportRowError] = []
    normalized_domain: str | None = None

    website = _clean_optional(raw.website)
    if website is None:
        errors.append(ImportRowError(field="website", message="missing website"))
    else:
        try:
            normalized_domain = normalize_website(website)
        except WebsiteNormalizationError as error:
            errors.append(ImportRowError(field="website", message=error.reason))

    return ImportRow(
        row_number=row_number,
        website=raw.website,
        normalized_domain=normalized_domain,
        platform=normalize_platform(raw.platform),
        country=_clean_optional(raw.country),
        city=_clean_optional(raw.city),
        validation_status=ValidationStatus.INVALID if errors else ValidationStatus.VALID,
        errors=errors,
        duplicate_status=DuplicateStatus.UNKNOWN,
    )
