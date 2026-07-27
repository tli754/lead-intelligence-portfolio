"""Enumerations for the evidence module. Pure Python — no FastAPI or MongoDB imports."""

from enum import StrEnum


class EvidenceType(StrEnum):
    PAGE_TEXT = "page_text"
    HTML_ATTRIBUTE = "html_attribute"
    JSON_LD = "json_ld"
    META_TAG = "meta_tag"
    LINK_TARGET = "link_target"
    FORM_FIELD = "form_field"
    SCRIPT_MARKER = "script_marker"
    COOKIE_MARKER = "cookie_marker"
    PAGE_METADATA = "page_metadata"
    SITEMAP_METADATA = "sitemap_metadata"
    IMPORTED_VALUE = "imported_value"
    DETERMINISTIC_INFERENCE = "deterministic_inference"
    MANUAL_OBSERVATION = "manual_observation"


class EvidenceStatus(StrEnum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    STALE = "stale"
    UNAVAILABLE = "unavailable"
    REJECTED = "rejected"


class EvidenceStrength(StrEnum):
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    AUTHORITATIVE = "authoritative"
