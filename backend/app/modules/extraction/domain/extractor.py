"""The pure extractor protocol and the input/output shapes it uses.

An `Extractor` implementation must never perform network I/O, never
import Motor/FastAPI, never mutate its `PageContext` input, and must be
deterministic for identical input (AC-03). Every concrete extractor's own
unit tests enforce this discipline directly (one `test_deterministic_output`
and one `test_input_not_mutated` case per extractor family).
"""

from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field

from app.modules.discovery.domain.enums import PageType
from app.modules.evidence.domain.evidence_factory import EvidenceDraft
from app.modules.extraction.domain.enums import FactSourceType, VerificationState
from app.modules.extraction.domain.field_catalogue import FieldPath, FieldValueType
from app.modules.extraction.domain.models import ConfidenceScore, ExtractorDefinition


class PageContext(BaseModel):
    """Everything one extractor invocation needs, and nothing more.

    Deliberately does **not** carry crawling's own `PageMetadata` Pydantic
    model — `page_metadata` here is a narrow, extraction-owned `dict`
    (built by the application service / `CrawlExtractionGateway` adapter
    from crawling's model), so this domain layer never imports a whole
    other module's record type.
    """

    model_config = {"frozen": True}

    page_id: str
    company_id: str
    source_url: str
    normalized_url: str
    page_type: PageType
    cleaned_html: str
    extracted_text: str
    page_metadata: dict[str, Any] = Field(default_factory=dict)
    raw_technology_signals: dict[str, Any] = Field(default_factory=dict)
    fetched_at: datetime
    content_hashes: dict[str, Any] = Field(default_factory=dict)


class FactCandidateDraft(BaseModel):
    """An extractor's raw output before candidate/evidence IDs are assigned."""

    field_path: FieldPath
    value: Any = None
    normalized_value: Any = None
    value_type: FieldValueType
    source_type: FactSourceType
    confidence: ConfidenceScore
    verification_state: VerificationState
    qualifiers: dict[str, Any] = Field(default_factory=dict)
    evidence_drafts: list[EvidenceDraft] = Field(default_factory=list)


class Extractor(Protocol):
    """A pure, deterministic extractor. See module docstring for the
    discipline every implementation must uphold."""

    def definition(self) -> ExtractorDefinition: ...

    def supports(self, page_context: PageContext) -> bool: ...

    def extract(self, page_context: PageContext) -> list[FactCandidateDraft]: ...
