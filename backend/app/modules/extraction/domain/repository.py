"""Repository interface for the extraction module.

Pure abstract contract — no MongoDB or FastAPI imports. Implementations
live in `infrastructure/` (`MongoExtractionRepository`).

Beyond the brief's literal method list this adds two documented methods
(contract T8):

- `find_active_or_completed_run` — required to serve brief section 19's
  idempotent-retry requirement (same shape as `CrawlRepository.find_active_run`'s
  own justification in Task 006, extended to also match a *completed* run
  so a retry can short-circuit to the existing result).
- `get_fact` — a single-fact lookup by id, required by
  `GET /api/facts/{fact_id}` and `GET /api/facts/{fact_id}/evidence`
  (brief section 23's endpoint list needs it; nothing in the brief's
  literal method list can otherwise serve a single-fact-by-id query).
"""

from abc import ABC, abstractmethod
from typing import NamedTuple

from app.modules.extraction.domain.enums import ExtractionStatus, FactStatus, VerificationState
from app.modules.extraction.domain.field_catalogue import FieldPath
from app.modules.extraction.domain.models import (
    ExtractionRun,
    ExtractorExecution,
    FactCandidate,
    FactConflict,
    FactRecord,
)


class FactPage(NamedTuple):
    items: list[FactRecord]
    total: int


class ExtractionRunPage(NamedTuple):
    items: list[ExtractionRun]
    total: int


class CandidatePage(NamedTuple):
    items: list[FactCandidate]
    total: int


class ExtractionRepository(ABC):
    # --- Runs ---------------------------------------------------------

    @abstractmethod
    async def create_run(self, run: ExtractionRun) -> ExtractionRun: ...

    @abstractmethod
    async def update_run(self, run: ExtractionRun) -> ExtractionRun | None:
        """Optimistic-concurrency filter on `document_version` — a stale
        caller's write is rejected (`None`) rather than silently
        overwriting a newer state."""
        ...

    @abstractmethod
    async def get_run(self, extraction_run_id: str) -> ExtractionRun | None: ...

    @abstractmethod
    async def list_runs_by_company(
        self, company_id: str, *, page: int = 1, page_size: int = 20
    ) -> ExtractionRunPage:
        """A fourth documented addition (contract T8) — required to serve
        `GET /api/companies/{company_id}/extraction-runs/latest` (brief
        section 23), mirroring `CrawlRepository.list_runs_by_company`'s
        identical precedent."""
        ...

    @abstractmethod
    async def list_runs(
        self,
        *,
        status: ExtractionStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> ExtractionRunPage:
        """Lists `ExtractionRun`s across all companies, sorted by `created_at`
        descending — the cross-company counterpart to `list_runs_by_company`,
        used by the jobs-page listing endpoint (`GET /api/extraction-runs`)."""
        ...

    @abstractmethod
    async def find_active_or_completed_run(
        self, company_id: str, idempotency_key: str
    ) -> ExtractionRun | None: ...

    @abstractmethod
    async def mark_run_cancelled(self, extraction_run_id: str) -> ExtractionRun | None:
        """A second documented addition beyond the brief's literal method
        list — required for `cancel_run` (brief section 19's "cancellation
        stops new extractor executions and preserves completed work"),
        mirroring `CrawlRepository.mark_run_cancelled`'s exact precedent."""
        ...

    # --- Extractor executions -------------------------------------------

    @abstractmethod
    async def save_extractor_execution(
        self, execution: ExtractorExecution
    ) -> ExtractorExecution: ...

    # --- Candidates -------------------------------------------------------

    @abstractmethod
    async def save_candidates(self, candidates: list[FactCandidate]) -> list[FactCandidate]: ...

    @abstractmethod
    async def list_candidates_by_run(
        self,
        extraction_run_id: str,
        *,
        field_path: FieldPath | None = None,
        page_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> CandidatePage: ...

    # --- Facts -----------------------------------------------------------

    @abstractmethod
    async def save_facts(self, facts: list[FactRecord]) -> list[FactRecord]:
        """Upserts by `(company_id, field_path)` — the mechanism satisfying
        the idempotent-retry requirement (brief section 19 / AC-34)."""
        ...

    @abstractmethod
    async def get_fact(self, fact_id: str) -> FactRecord | None: ...

    @abstractmethod
    async def get_latest_fact(
        self, company_id: str, field_path: FieldPath
    ) -> FactRecord | None: ...

    @abstractmethod
    async def list_facts_by_run(self, extraction_run_id: str) -> list[FactRecord]:
        """A third documented addition (contract T8) — required to serve
        `GET /api/extraction-runs/{extraction_run_id}/facts` (brief section
        23), which the brief's literal method list can't otherwise answer
        (`list_facts_by_company` is scoped by company, not by run)."""
        ...

    @abstractmethod
    async def list_facts_by_company(
        self,
        company_id: str,
        *,
        field_path: FieldPath | None = None,
        status: FactStatus | None = None,
        verification_state: VerificationState | None = None,
        minimum_confidence: int | None = None,
        include_stale: bool = False,
        include_conflicting: bool = True,
        page: int = 1,
        page_size: int = 20,
    ) -> FactPage: ...

    @abstractmethod
    async def mark_previous_facts_stale(
        self, company_id: str, field_path: FieldPath, *, exclude_fact_ids: list[str] | None = None
    ) -> int:
        """Marks currently-accepted facts for `(company_id, field_path)`
        (other than any id in `exclude_fact_ids`) `status=superseded`/
        `verification_state=stale` — never deletes them. Returns the
        number of facts marked. Called at run-start (freshness sweep) and
        whenever a new accepted fact supersedes an old one."""
        ...

    # --- Conflicts ---------------------------------------------------------

    @abstractmethod
    async def save_conflicts(self, conflicts: list[FactConflict]) -> list[FactConflict]: ...
