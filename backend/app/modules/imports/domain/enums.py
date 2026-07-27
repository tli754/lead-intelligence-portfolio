"""Enumerations for the imports module. Pure Python — no FastAPI or MongoDB imports."""

from enum import StrEnum


class ImportSource(StrEnum):
    STORELEADS_HTML = "storeleads_html"


class ValidationStatus(StrEnum):
    VALID = "valid"
    INVALID = "invalid"


class DuplicateStatus(StrEnum):
    NEW = "new"
    EXISTING = "existing"
    DUPLICATE_IN_FILE = "duplicate_in_file"
    UNKNOWN = "unknown"


class ImportRowOutcome(StrEnum):
    """What actually happened to a row during an import run.

    Only set on rows returned by `ImportService` — preview rows always
    have `outcome=None`, since nothing has been attempted yet.
    """

    CREATED = "created"
    SKIPPED_EXISTING = "skipped_existing"
    SKIPPED_INVALID = "skipped_invalid"
    FAILED = "failed"
