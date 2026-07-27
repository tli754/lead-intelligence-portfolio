"""Enumerations for the extraction module. Pure Python — no FastAPI or MongoDB imports."""

from enum import StrEnum


class ExtractionStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    STALE = "stale"


class VerificationState(StrEnum):
    VERIFIED = "verified"
    MEASURED = "measured"
    INFERRED = "inferred"
    UNKNOWN = "unknown"
    CONFLICTING = "conflicting"
    STALE = "stale"


class FactStatus(StrEnum):
    CANDIDATE = "candidate"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    CONFLICTING = "conflicting"
    STALE = "stale"


class ExtractorExecutionStatus(StrEnum):
    """Documented addition (not one of the brief's literal section-1 enums):
    the per-page-per-extractor outcome `ExtractorExecution.status` needs a
    vocabulary distinct from the whole-run `ExtractionStatus` above."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class FactSourceType(StrEnum):
    JSON_LD = "json_ld"
    OPEN_GRAPH = "open_graph"
    META_TAG = "meta_tag"
    HTML_ELEMENT = "html_element"
    LINK = "link"
    FORM = "form"
    SCRIPT_MARKER = "script_marker"
    COOKIE_MARKER = "cookie_marker"
    PAGE_METADATA = "page_metadata"
    SITEMAP_SUMMARY = "sitemap_summary"
    DETERMINISTIC_INFERENCE = "deterministic_inference"
    IMPORTED = "imported"
    MANUAL = "manual"
