"""Shared fixtures for extraction-module integration tests.

No real MongoDB and no real network — matching
`backend/tests/integration/crawling/conftest.py`'s exact style. Fakes for
every port `StructuredExtractionService` depends on
(`CompanyExtractionGateway`, `CrawlExtractionGateway`, `EvidenceGateway`,
`ExtractionRepository`).
"""

from datetime import UTC, datetime

import pytest

from app.modules.companies.domain.enums import ProcessingStatus
from app.modules.crawling.domain.enums import PageFetchStatus
from app.modules.crawling.domain.models import CrawledPage, CrawlRun
from app.modules.discovery.domain.enums import DiscoveryPriority, PageType
from app.modules.evidence.domain.evidence_factory import EvidenceDraft, create_evidence_record
from app.modules.evidence.domain.models import EvidenceRecord
from app.modules.extraction.domain.company_projection import CompanyFactsProjection
from app.modules.extraction.domain.enums import FactStatus, VerificationState
from app.modules.extraction.domain.exceptions import (
    CompanyNotFoundForExtractionError,
    CrawlRunNotFoundForExtractionError,
)
from app.modules.extraction.domain.gateway import (
    CompanyExtractionGateway,
    CrawlExtractionGateway,
    EvidenceGateway,
)
from app.modules.extraction.domain.models import (
    ExtractionRun,
    ExtractorExecution,
    FactCandidate,
    FactConflict,
    FactRecord,
)
from app.modules.extraction.domain.repository import (
    CandidatePage,
    ExtractionRepository,
    ExtractionRunPage,
    FactPage,
)

_CURRENT_FACT_STATUSES = (FactStatus.ACCEPTED, FactStatus.CONFLICTING)


# --- Fakes -----------------------------------------------------------------


class FakeCompanyExtractionGateway(CompanyExtractionGateway):
    def __init__(self, *, known_company_ids: set[str] | None = None) -> None:
        self._known = set(known_company_ids or {"company-1"})
        self.status_updates: list[tuple[str, ProcessingStatus]] = []
        self.latest_run_updates: list[tuple[str, str]] = []
        self.projections: list[tuple[str, CompanyFactsProjection]] = []

    async def update_processing_status(self, company_id: str, status: ProcessingStatus) -> None:
        if company_id not in self._known:
            raise CompanyNotFoundForExtractionError(company_id)
        self.status_updates.append((company_id, status))

    async def update_latest_extraction_run(self, company_id: str, extraction_run_id: str) -> None:
        self.latest_run_updates.append((company_id, extraction_run_id))

    async def project_latest_facts(
        self, company_id: str, projection: CompanyFactsProjection
    ) -> None:
        self.projections.append((company_id, projection))


class FakeCrawlExtractionGateway(CrawlExtractionGateway):
    def __init__(
        self,
        *,
        crawl_run: CrawlRun | None = None,
        pages: list[CrawledPage] | None = None,
        content: dict[tuple[str, str], bytes] | None = None,
    ) -> None:
        self._run = crawl_run
        self._pages = pages or []
        self._content = content or {}

    async def get_crawl_run(self, crawl_run_id: str) -> CrawlRun:
        if self._run is None or self._run.crawl_run_id != crawl_run_id:
            raise CrawlRunNotFoundForExtractionError(crawl_run_id)
        return self._run

    async def list_pages(
        self, crawl_run_id: str, *, statuses=None, page_types=None
    ) -> list[CrawledPage]:
        pages = [p for p in self._pages if p.crawl_run_id == crawl_run_id]
        if statuses is not None:
            pages = [p for p in pages if p.fetch_status in statuses]
        if page_types is not None:
            pages = [p for p in pages if p.page_type in page_types]
        return pages

    async def load_page_content(self, page_id: str, content_kind: str) -> bytes | None:
        return self._content.get((page_id, content_kind))


class FakeEvidenceGateway(EvidenceGateway):
    def __init__(self, *, fail_for_field_paths: set[str] | None = None) -> None:
        self._records: dict[str, EvidenceRecord] = {}
        self._fail_for_field_paths = fail_for_field_paths or set()
        self.create_calls = 0

    async def create_evidence(self, draft: EvidenceDraft) -> EvidenceRecord:
        self.create_calls += 1
        if draft.fact_field_path in self._fail_for_field_paths:
            from app.modules.evidence.domain.exceptions import EvidenceCreationFailedError

            raise EvidenceCreationFailedError(reason="simulated failure")
        record = create_evidence_record(draft)
        self._records[record.evidence_id] = record
        return record

    async def get_evidence(self, evidence_id: str) -> EvidenceRecord | None:
        return self._records.get(evidence_id)

    async def list_evidence_for_fact(self, evidence_ids: list[str]) -> list[EvidenceRecord]:
        return [self._records[eid] for eid in evidence_ids if eid in self._records]


class FakeExtractionRepository(ExtractionRepository):
    """A full in-memory `ExtractionRepository`, mirroring
    `MongoExtractionRepository`'s real semantics closely enough for
    service-level tests: optimistic-concurrency runs, and a `facts`
    "current slot" model identical to the Mongo repository's own
    documented upsert-by-`(company_id, field_path, status)` behavior."""

    def __init__(self) -> None:
        self.runs: dict[str, ExtractionRun] = {}
        self.executions: list[ExtractorExecution] = []
        self.candidates: dict[str, FactCandidate] = {}
        self.facts: dict[str, FactRecord] = {}
        self.conflicts: dict[str, FactConflict] = {}

    async def create_run(self, run: ExtractionRun) -> ExtractionRun:
        self.runs[run.extraction_run_id] = run
        return run

    async def update_run(self, run: ExtractionRun) -> ExtractionRun | None:
        existing = self.runs.get(run.extraction_run_id)
        if existing is None or existing.document_version != run.document_version:
            return None
        updated = run.model_copy(update={"document_version": run.document_version + 1})
        self.runs[run.extraction_run_id] = updated
        return updated

    async def get_run(self, extraction_run_id: str) -> ExtractionRun | None:
        return self.runs.get(extraction_run_id)

    async def list_runs_by_company(
        self, company_id: str, *, page: int = 1, page_size: int = 20
    ) -> ExtractionRunPage:
        items = sorted(
            (r for r in self.runs.values() if r.company_id == company_id),
            key=lambda r: r.created_at,
            reverse=True,
        )
        start = (page - 1) * page_size
        return ExtractionRunPage(items=items[start : start + page_size], total=len(items))

    async def find_active_or_completed_run(
        self, company_id: str, idempotency_key: str
    ) -> ExtractionRun | None:
        for run in self.runs.values():
            if run.company_id == company_id and run.idempotency_key == idempotency_key:
                return run
        return None

    async def mark_run_cancelled(self, extraction_run_id: str) -> ExtractionRun | None:
        run = self.runs.get(extraction_run_id)
        if run is None:
            return None
        from app.modules.extraction.domain.enums import ExtractionStatus

        updated = run.model_copy(
            update={
                "status": ExtractionStatus.CANCELLED,
                "document_version": run.document_version + 1,
            }
        )
        self.runs[extraction_run_id] = updated
        return updated

    async def save_extractor_execution(self, execution: ExtractorExecution) -> ExtractorExecution:
        self.executions.append(execution)
        return execution

    async def save_candidates(self, candidates: list[FactCandidate]) -> list[FactCandidate]:
        for candidate in candidates:
            self.candidates[candidate.candidate_id] = candidate
        return candidates

    async def list_candidates_by_run(
        self,
        extraction_run_id: str,
        *,
        field_path=None,
        page_id=None,
        page: int = 1,
        page_size: int = 20,
    ) -> CandidatePage:
        items = [c for c in self.candidates.values() if c.extraction_run_id == extraction_run_id]
        if field_path is not None:
            items = [c for c in items if c.field_path == field_path]
        if page_id is not None:
            items = [c for c in items if c.page_id == page_id]
        start = (page - 1) * page_size
        return CandidatePage(items=items[start : start + page_size], total=len(items))

    async def save_facts(self, facts: list[FactRecord]) -> list[FactRecord]:
        for fact in facts:
            current_slot_id = None
            for existing_id, existing in self.facts.items():
                if (
                    existing.company_id == fact.company_id
                    and existing.field_path == fact.field_path
                    and existing.status in _CURRENT_FACT_STATUSES
                ):
                    current_slot_id = existing_id
                    break
            if current_slot_id is not None:
                del self.facts[current_slot_id]
            self.facts[fact.fact_id] = fact
        return facts

    async def get_fact(self, fact_id: str) -> FactRecord | None:
        return self.facts.get(fact_id)

    async def get_latest_fact(self, company_id: str, field_path) -> FactRecord | None:
        for fact in self.facts.values():
            if (
                fact.company_id == company_id
                and fact.field_path == field_path
                and fact.status in _CURRENT_FACT_STATUSES
            ):
                return fact
        return None

    async def list_facts_by_run(self, extraction_run_id: str) -> list[FactRecord]:
        return [f for f in self.facts.values() if f.extraction_run_id == extraction_run_id]

    async def list_facts_by_company(
        self,
        company_id: str,
        *,
        field_path=None,
        status=None,
        verification_state=None,
        minimum_confidence=None,
        include_stale: bool = False,
        include_conflicting: bool = True,
        page: int = 1,
        page_size: int = 20,
    ) -> FactPage:
        items = [f for f in self.facts.values() if f.company_id == company_id]
        if field_path is not None:
            items = [f for f in items if f.field_path == field_path]
        if status is not None:
            items = [f for f in items if f.status == status]
        else:
            if not include_stale:
                items = [f for f in items if f.status != FactStatus.STALE]
            if not include_conflicting:
                items = [f for f in items if f.status != FactStatus.CONFLICTING]
        if verification_state is not None:
            items = [f for f in items if f.verification_state == verification_state]
        if minimum_confidence is not None:
            items = [f for f in items if f.confidence >= minimum_confidence]
        start = (page - 1) * page_size
        return FactPage(items=items[start : start + page_size], total=len(items))

    async def mark_previous_facts_stale(
        self, company_id: str, field_path, *, exclude_fact_ids: list[str] | None = None
    ) -> int:
        exclude_fact_ids = exclude_fact_ids or []
        count = 0
        for fact_id, fact in list(self.facts.items()):
            if (
                fact.company_id == company_id
                and fact.field_path == field_path
                and fact.status in _CURRENT_FACT_STATUSES
                and fact_id not in exclude_fact_ids
            ):
                self.facts[fact_id] = fact.model_copy(
                    update={
                        "status": FactStatus.STALE,
                        "verification_state": VerificationState.STALE,
                    }
                )
                count += 1
        return count

    async def save_conflicts(self, conflicts: list[FactConflict]) -> list[FactConflict]:
        for conflict in conflicts:
            self.conflicts[conflict.conflict_id] = conflict
        return conflicts


# --- Test-data builders -----------------------------------------------------


def make_crawl_run(*, crawl_run_id: str = "crawl-run-1", company_id: str = "company-1") -> CrawlRun:
    now = datetime.now(UTC)
    return CrawlRun(
        crawl_run_id=crawl_run_id,
        company_id=company_id,
        discovery_run_id="discovery-run-1",
        idempotency_key="crawl-idempotency-key",
        created_at=now,
        updated_at=now,
    )


def make_crawled_page(
    *,
    page_id: str,
    crawl_run_id: str = "crawl-run-1",
    company_id: str = "company-1",
    page_type: PageType = PageType.HOMEPAGE,
    fetch_status: PageFetchStatus = PageFetchStatus.FETCHED,
    unchanged_from_page_id: str | None = None,
) -> CrawledPage:
    now = datetime.now(UTC)
    return CrawledPage(
        page_id=page_id,
        crawl_run_id=crawl_run_id,
        company_id=company_id,
        discovery_run_id="discovery-run-1",
        original_url=f"https://example.com/{page_id}",
        normalized_url=f"https://example.com/{page_id}",
        page_type=page_type,
        priority=DiscoveryPriority.PRIORITY_1,
        fetch_status=fetch_status,
        unchanged_from_page_id=unchanged_from_page_id,
        fetched_at=now,
        created_at=now,
        updated_at=now,
    )


# --- Pytest fixtures ---------------------------------------------------------


@pytest.fixture
def company_gateway() -> FakeCompanyExtractionGateway:
    return FakeCompanyExtractionGateway()


@pytest.fixture
def crawl_gateway() -> FakeCrawlExtractionGateway:
    return FakeCrawlExtractionGateway(crawl_run=make_crawl_run())


@pytest.fixture
def evidence_gateway() -> FakeEvidenceGateway:
    return FakeEvidenceGateway()


@pytest.fixture
def extraction_repository() -> FakeExtractionRepository:
    return FakeExtractionRepository()
