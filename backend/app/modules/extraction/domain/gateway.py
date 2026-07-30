"""The extraction module's integration points with other modules.

Pure abstract contracts — no MongoDB or FastAPI imports. `ProcessingStatus`,
`CrawlRun`, `CrawledPage`, `PageFetchStatus`, `PageType`, and
`EvidenceRecord` are imported as pure value types (zero FastAPI/Mongo
imports of their own) — the same "reuse the other module's own vocabulary"
precedent `modules/crawling/domain/gateway.py` already set.

All three ports live in this one file, matching `modules/crawling`'s own
"one file, one gateway module" precedent (contract T10).
"""

from abc import ABC, abstractmethod
from typing import Literal

from app.modules.companies.domain.enums import ProcessingStatus
from app.modules.crawling.domain.enums import PageFetchStatus
from app.modules.crawling.domain.models import CrawledPage, CrawlRun
from app.modules.discovery.domain.enums import PageType
from app.modules.evidence.domain.evidence_factory import EvidenceDraft
from app.modules.evidence.domain.models import EvidenceRecord
from app.modules.extraction.domain.company_projection import CompanyFactsProjection

ContentKind = Literal["raw", "cleaned", "text"]


class CompanyExtractionGateway(ABC):
    """Port the extraction module uses to reach the Company module.

    Exactly the brief's three literal methods (section 20) — no added
    "company exists" method. Company/run validation is instead served by
    one early `update_processing_status(company_id, EXTRACTING)` call, a
    raised `CompanyNotFoundForExtractionError` doubling as the existence
    check — the identical narrative shape `WebsiteCrawlService` already
    established for `CompanyCrawlGateway` (see that service's own
    docstring for the precedent this mirrors).
    """

    @abstractmethod
    async def update_latest_extraction_run(self, company_id: str, extraction_run_id: str) -> None:
        """**Documented, logged no-op** (contract resolution #2) — see
        `infrastructure/company_service_gateway.py`'s docstring for the
        required follow-up."""
        ...

    @abstractmethod
    async def update_processing_status(self, company_id: str, status: ProcessingStatus) -> None:
        """Fully real today (contract resolution #4) —
        `CompanyService.change_processing_status` already exists."""
        ...

    @abstractmethod
    async def project_latest_facts(
        self, company_id: str, projection: CompanyFactsProjection
    ) -> None:
        """**Documented, logged no-op** (contract resolution #3) — a
        larger gap than `update_latest_extraction_run`: no field exists
        yet on `Company`/`CompanyProcessing` to write into at all. See the
        adapter's own docstring for the required follow-up."""
        ...


class CrawlExtractionGateway(ABC):
    """Port the extraction module uses to reach the Crawling module.

    Wraps `CrawlRepository`/`ContentStorage` (both interfaces, never a
    concrete Mongo/filesystem class) per contract resolution #1.
    """

    @abstractmethod
    async def get_crawl_run(self, crawl_run_id: str) -> CrawlRun:
        """Raises `CrawlRunNotFoundForExtractionError` if no such run
        exists."""
        ...

    @abstractmethod
    async def list_pages(
        self,
        crawl_run_id: str,
        *,
        statuses: list[PageFetchStatus] | None = None,
        page_types: list[PageType] | None = None,
    ) -> list[CrawledPage]:
        """Returns the full, filtered page set for one crawl run."""
        ...

    @abstractmethod
    async def load_page_content(self, page_id: str, content_kind: ContentKind) -> bytes | None:
        """Transparently follows a single `unchanged_from_page_id` hop
        when the requested page's own content for `content_kind` is empty
        (contract resolution #1's "new decision this contract makes
        explicit") — never `None` for a page that in fact has content via
        its predecessor."""
        ...


class EvidenceGateway(ABC):
    """Port the extraction module uses to reach the Evidence module.

    Wraps the evidence module's own `EvidenceService` (never
    `EvidenceRepository`/`MongoEvidenceRepository` directly) per contract
    resolution #5 — the same "import the other module's own public
    application service + its DI function" shape every other cross-module
    gateway in this repository uses.
    """

    @abstractmethod
    async def create_evidence(self, draft: EvidenceDraft) -> EvidenceRecord:
        """Raises `EvidenceCreationFailedError` on persistence failure —
        the application service must treat that as blocking acceptance of
        whatever candidate this evidence would have backed (brief section
        19 / AC-30)."""
        ...

    @abstractmethod
    async def get_evidence(self, evidence_id: str) -> EvidenceRecord | None: ...

    @abstractmethod
    async def list_evidence_for_fact(self, evidence_ids: list[str]) -> list[EvidenceRecord]: ...
