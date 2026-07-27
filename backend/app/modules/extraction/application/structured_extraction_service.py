"""Orchestrates one extraction run end-to-end.

Depends only on the domain layer's ports (`CompanyExtractionGateway`,
`CrawlExtractionGateway`, `EvidenceGateway`, `ExtractionRepository`) plus
the registered `Extractor` list and the pure policy modules (T12-T14) —
never a concrete Mongo/HTTP/FastAPI type, and never imports FastAPI.
Mirrors `WebsiteCrawlService`'s/`WebsiteDiscoveryService`'s shape and
their "depend only on domain ports" discipline exactly.
"""

import logging
import time
from datetime import UTC, datetime

from app.modules.companies.domain.enums import ProcessingStatus
from app.modules.companies.domain.exceptions import InvalidStatusTransitionError
from app.modules.crawling.domain.enums import PageFetchStatus
from app.modules.crawling.domain.models import CrawledPage
from app.modules.evidence.domain.evidence_factory import EVIDENCE_FORMAT_VERSION
from app.modules.evidence.domain.exceptions import EvidenceCreationFailedError
from app.modules.extraction.domain.company_projection import (
    PROJECTION_SCHEMA_VERSION,
    build_projection,
)
from app.modules.extraction.domain.confidence_policy import CONFIDENCE_POLICY_VERSION
from app.modules.extraction.domain.enums import (
    ExtractionStatus,
    ExtractorExecutionStatus,
    FactStatus,
)
from app.modules.extraction.domain.exceptions import (
    DuplicateActiveExtractionRunError,
    ExtractionRunNotFoundError,
)
from app.modules.extraction.domain.extractor import Extractor, FactCandidateDraft, PageContext
from app.modules.extraction.domain.field_catalogue import FIELD_CATALOGUE, FIELD_CATALOGUE_VERSION
from app.modules.extraction.domain.freshness_policy import FRESHNESS_POLICY_VERSION, FreshnessPolicy
from app.modules.extraction.domain.gateway import (
    CompanyExtractionGateway,
    CrawlExtractionGateway,
    EvidenceGateway,
)
from app.modules.extraction.domain.idempotency import compute_idempotency_key
from app.modules.extraction.domain.models import (
    ExtractionRun,
    ExtractionRunOptions,
    ExtractionSummary,
    ExtractionWarning,
    ExtractorExecution,
    FactCandidate,
)
from app.modules.extraction.domain.reconciliation import (
    ReconciliationConfig,
    group_candidates,
    reconcile_candidates,
)
from app.modules.extraction.domain.reconciliation_rules import RECONCILIATION_RULES_VERSION
from app.modules.extraction.domain.repository import ExtractionRepository

logger = logging.getLogger(__name__)

_ELIGIBLE_FETCH_STATUSES = frozenset(
    {PageFetchStatus.FETCHED, PageFetchStatus.UNCHANGED, PageFetchStatus.BROWSER_FETCHED}
)

_EXTRACTOR_IMPLEMENTATION_VERSION = "v1"


class StructuredExtractionService:
    def __init__(
        self,
        *,
        company_gateway: CompanyExtractionGateway,
        crawl_gateway: CrawlExtractionGateway,
        evidence_gateway: EvidenceGateway,
        repository: ExtractionRepository,
        extractors: list[Extractor],
        freshness_policy: FreshnessPolicy | None = None,
        reconciliation_config: ReconciliationConfig | None = None,
    ) -> None:
        self._company_gateway = company_gateway
        self._crawl_gateway = crawl_gateway
        self._evidence_gateway = evidence_gateway
        self._repository = repository
        self._extractors = extractors
        self._freshness_policy = freshness_policy or FreshnessPolicy()
        self._reconciliation_config = reconciliation_config or ReconciliationConfig()

    # --- Public API ---------------------------------------------------------

    async def start_extraction_run(
        self, company_id: str, crawl_run_id: str, options: ExtractionRunOptions | None = None
    ) -> ExtractionRun:
        options = options or ExtractionRunOptions()
        idempotency_key = compute_idempotency_key(company_id, crawl_run_id, options)

        existing = await self._repository.find_active_or_completed_run(company_id, idempotency_key)
        if existing is not None:
            if existing.status in (ExtractionStatus.QUEUED, ExtractionStatus.RUNNING):
                raise DuplicateActiveExtractionRunError(
                    existing_extraction_run_id=existing.extraction_run_id,
                    status=existing.status.value,
                )
            return existing  # idempotent retry — same accepted facts already exist.

        crawl_run = await self._crawl_gateway.get_crawl_run(crawl_run_id)
        await self._advance_processing_status(company_id, ProcessingStatus.EXTRACTING)

        start = time.monotonic()
        now = datetime.now(UTC)
        run = ExtractionRun(
            company_id=company_id,
            crawl_run_id=crawl_run.crawl_run_id,
            configuration_snapshot=self._configuration_snapshot(options),
            idempotency_key=idempotency_key,
            created_at=now,
            updated_at=now,
        )
        run = await self._repository.create_run(run)
        run.status = ExtractionStatus.RUNNING
        run.started_at = datetime.now(UTC)
        run.updated_at = run.started_at
        run = await self._repository.update_run(run) or run

        summary = ExtractionSummary()
        warnings: list[ExtractionWarning] = []

        pages = await self._crawl_gateway.list_pages(
            crawl_run_id, page_types=options.page_types or None
        )
        summary.pages_considered = len(pages)

        all_candidates: list[FactCandidate] = []
        cancelled = False
        for page in pages:
            current_run = await self._repository.get_run(run.extraction_run_id)
            if current_run is not None and current_run.status == ExtractionStatus.CANCELLED:
                cancelled = True
                break

            if page.fetch_status not in _ELIGIBLE_FETCH_STATUSES:
                summary.pages_skipped += 1
                warnings.append(
                    self._warning(
                        "page_ineligible",
                        f"page {page.page_id} has fetch_status={page.fetch_status.value!r}, "
                        "not eligible for extraction",
                        page_id=page.page_id,
                    )
                )
                continue

            page_context = await self._build_page_context(page, company_id)
            if page_context is None:
                summary.pages_skipped += 1
                warnings.append(
                    self._warning(
                        "page_content_unavailable",
                        f"no cleaned/text content available for page {page.page_id}",
                        page_id=page.page_id,
                    )
                )
                continue

            summary.pages_processed += 1
            page_candidates, page_warnings, executions_run = await self._run_extractors(
                run, page, page_context, options
            )
            all_candidates.extend(page_candidates)
            warnings.extend(page_warnings)
            summary.extractor_executions += executions_run
            summary.candidates_created += len(page_candidates)

        if all_candidates:
            await self._repository.save_candidates(all_candidates)

        (
            accepted_facts,
            conflicts,
            reconciliation_warnings,
            had_partial_failure,
            unknown_count,
        ) = await self._reconcile(all_candidates)
        warnings.extend(reconciliation_warnings)
        for fact in accepted_facts:
            if fact.status == FactStatus.CONFLICTING:
                summary.facts_conflicting += 1
            else:
                summary.facts_accepted += 1
        summary.facts_unknown = unknown_count

        if accepted_facts:
            await self._repository.save_facts(accepted_facts)
        if conflicts:
            await self._repository.save_conflicts(conflicts)

        summary.evidence_created = sum(len(candidate.evidence_ids) for candidate in all_candidates)
        summary.duration_ms = int((time.monotonic() - start) * 1000)
        summary.warnings = len(warnings)

        run.summary = summary
        run.warnings = warnings
        run.status = self._final_status(
            summary=summary, cancelled=cancelled, had_partial_failure=had_partial_failure
        )
        run.completed_at = datetime.now(UTC)
        run.updated_at = run.completed_at
        run = await self._repository.update_run(run) or run

        await self._project_latest_facts(company_id)
        await self._finish_company_status(run)
        await self._company_gateway.update_latest_extraction_run(company_id, run.extraction_run_id)
        return run

    async def cancel_run(self, extraction_run_id: str) -> ExtractionRun:
        run = await self._repository.mark_run_cancelled(extraction_run_id)
        if run is None:
            raise ExtractionRunNotFoundError(extraction_run_id)
        return run

    # --- Page/extractor execution --------------------------------------------

    async def _run_extractors(
        self,
        run: ExtractionRun,
        page: CrawledPage,
        page_context: PageContext,
        options: ExtractionRunOptions,
    ) -> tuple[list[FactCandidate], list[ExtractionWarning], int]:
        candidates: list[FactCandidate] = []
        warnings: list[ExtractionWarning] = []
        executions_run = 0

        for extractor in self._extractors:
            definition = extractor.definition()
            if options.extractor_ids and definition.extractor_id not in options.extractor_ids:
                continue
            if not definition.enabled or not extractor.supports(page_context):
                continue

            execution_start = time.monotonic()
            started_at = datetime.now(UTC)
            extractor_warnings: list[ExtractionWarning] = []
            try:
                drafts: list[FactCandidateDraft] = extractor.extract(page_context)
                status = ExtractorExecutionStatus.SUCCEEDED
            except Exception as error:  # one extractor's failure must never fail the whole page
                drafts = []
                status = ExtractorExecutionStatus.FAILED
                warning = self._warning(
                    "extractor_failed",
                    f"extractor {definition.extractor_id!r} raised: {error}",
                    page_id=page.page_id,
                    extractor_id=definition.extractor_id,
                )
                extractor_warnings.append(warning)
                warnings.append(warning)

            execution = ExtractorExecution(
                extraction_run_id=run.extraction_run_id,
                page_id=page.page_id,
                extractor_id=definition.extractor_id,
                extractor_version=definition.version,
                status=status,
                candidates_produced=len(drafts),
                warnings=extractor_warnings,
                duration_ms=int((time.monotonic() - execution_start) * 1000),
                started_at=started_at,
                completed_at=datetime.now(UTC),
            )
            await self._repository.save_extractor_execution(execution)
            executions_run += 1

            for draft in drafts:
                candidate = await self._materialize_candidate(
                    run, page, page_context, draft, extractor_id=definition.extractor_id
                )
                if candidate is None:
                    warnings.append(
                        self._warning(
                            "evidence_creation_failed",
                            f"evidence creation failed for a {draft.field_path.value!r} candidate "
                            f"from extractor {definition.extractor_id!r}; candidate dropped",
                            page_id=page.page_id,
                            extractor_id=definition.extractor_id,
                        )
                    )
                    continue
                candidates.append(candidate)

        return candidates, warnings, executions_run

    async def _materialize_candidate(
        self,
        run: ExtractionRun,
        page: CrawledPage,
        page_context: PageContext,
        draft: FactCandidateDraft,
        *,
        extractor_id: str,
    ) -> FactCandidate | None:
        evidence_ids: list[str] = []
        for evidence_draft in draft.evidence_drafts:
            evidence_draft.extraction_run_id = run.extraction_run_id
            try:
                evidence = await self._evidence_gateway.create_evidence(evidence_draft)
            except EvidenceCreationFailedError as error:
                logger.warning(
                    "evidence creation failed for field_path=%s page_id=%s: %s",
                    draft.field_path.value,
                    page.page_id,
                    error,
                )
                return None
            evidence_ids.append(evidence.evidence_id)

        return FactCandidate(
            extraction_run_id=run.extraction_run_id,
            company_id=page_context.company_id,
            page_id=page.page_id,
            field_path=draft.field_path,
            value=draft.value,
            normalized_value=draft.normalized_value,
            value_type=draft.value_type,
            source_type=draft.source_type,
            extractor_id=extractor_id,
            extractor_version=_EXTRACTOR_IMPLEMENTATION_VERSION,
            confidence=draft.confidence,
            verification_state=draft.verification_state,
            evidence_ids=evidence_ids,
            qualifiers=draft.qualifiers,
            observed_at=page_context.fetched_at,
            created_at=datetime.now(UTC),
        )

    # --- Reconciliation -------------------------------------------------------

    async def _reconcile(
        self, candidates: list[FactCandidate]
    ) -> tuple[list, list, list[ExtractionWarning], bool, int]:
        accepted_facts = []
        conflicts = []
        warnings: list[ExtractionWarning] = []
        had_partial_failure = False
        unknown_count = 0

        for (company_id, field_path), group in group_candidates(candidates).items():
            field_definition = FIELD_CATALOGUE[field_path]
            existing_fact = await self._repository.get_latest_fact(company_id, field_path)
            try:
                outcome = reconcile_candidates(
                    group,
                    field_definition=field_definition,
                    existing_fact=existing_fact,
                    config=self._reconciliation_config,
                )
            except Exception as error:  # reconciliation failure for one field marks the run partial
                had_partial_failure = True
                warnings.append(
                    self._warning(
                        "reconciliation_failed",
                        f"reconciliation failed for field_path={field_path.value!r}: {error}",
                    )
                )
                continue

            if outcome.accepted_fact is not None:
                accepted_facts.append(outcome.accepted_fact)
            else:
                unknown_count += 1
            if outcome.conflict is not None:
                conflicts.append(outcome.conflict)
            if outcome.superseded_candidate_ids and existing_fact is not None:
                exclude_ids = [outcome.accepted_fact.fact_id] if outcome.accepted_fact else []
                await self._repository.mark_previous_facts_stale(
                    company_id, field_path, exclude_fact_ids=exclude_ids
                )

        return accepted_facts, conflicts, warnings, had_partial_failure, unknown_count

    # --- Page context construction -------------------------------------------

    async def _build_page_context(self, page: CrawledPage, company_id: str) -> PageContext | None:
        cleaned_bytes = await self._crawl_gateway.load_page_content(page.page_id, "cleaned")
        text_bytes = await self._crawl_gateway.load_page_content(page.page_id, "text")
        if cleaned_bytes is None and text_bytes is None:
            return None

        cleaned_html = cleaned_bytes.decode("utf-8", errors="replace") if cleaned_bytes else ""
        extracted_text = text_bytes.decode("utf-8", errors="replace") if text_bytes else ""

        page_metadata = self._flatten_page_metadata(page)
        raw_technology_signals = (
            page.page_metadata.technology_signals if page.page_metadata is not None else {}
        )

        return PageContext(
            page_id=page.page_id,
            company_id=company_id,
            source_url=page.original_url,
            normalized_url=page.normalized_url,
            page_type=page.page_type,
            cleaned_html=cleaned_html,
            extracted_text=extracted_text,
            page_metadata=page_metadata,
            raw_technology_signals=raw_technology_signals,
            fetched_at=page.fetched_at or datetime.now(UTC),
            content_hashes=page.content_hashes.model_dump(),
        )

    def _flatten_page_metadata(self, page: CrawledPage) -> dict:
        if page.page_metadata is None:
            return {}
        return page.page_metadata.model_dump(exclude={"technology_signals"})

    # --- Small helpers --------------------------------------------------------

    def _configuration_snapshot(self, options: ExtractionRunOptions) -> dict:
        return {
            "options": options.model_dump(mode="json"),
            "field_catalogue_version": FIELD_CATALOGUE_VERSION,
            "extractor_implementation_version": _EXTRACTOR_IMPLEMENTATION_VERSION,
            "extractor_versions": {
                extractor.definition().extractor_id: extractor.definition().version
                for extractor in self._extractors
            },
            "evidence_format_version": EVIDENCE_FORMAT_VERSION,
            "confidence_policy_version": CONFIDENCE_POLICY_VERSION,
            "reconciliation_rules_version": RECONCILIATION_RULES_VERSION,
            "freshness_policy_version": FRESHNESS_POLICY_VERSION,
            "projection_schema_version": PROJECTION_SCHEMA_VERSION,
        }

    def _warning(
        self,
        code: str,
        message: str,
        *,
        page_id: str | None = None,
        extractor_id: str | None = None,
    ) -> ExtractionWarning:
        return ExtractionWarning(
            code=code,
            message=message,
            page_id=page_id,
            extractor_id=extractor_id,
            created_at=datetime.now(UTC),
        )

    def _final_status(
        self, *, summary: ExtractionSummary, cancelled: bool, had_partial_failure: bool
    ) -> ExtractionStatus:
        if cancelled:
            return ExtractionStatus.CANCELLED
        if had_partial_failure:
            return ExtractionStatus.PARTIAL
        if summary.pages_processed == 0 and summary.pages_considered > 0:
            return ExtractionStatus.PARTIAL
        if summary.warnings > 0:
            return ExtractionStatus.COMPLETED_WITH_WARNINGS
        return ExtractionStatus.COMPLETED

    async def _advance_processing_status(self, company_id: str, status: ProcessingStatus) -> None:
        """Best-effort: another pipeline stage may have already moved the
        company past `status`, or the company may not exist at all (that
        second case surfaces `CompanyNotFoundForExtractionError`, which is
        allowed to propagate — it is this call's "does the company exist"
        validation, exactly `WebsiteCrawlService`'s own precedent)."""
        try:
            await self._company_gateway.update_processing_status(company_id, status)
        except InvalidStatusTransitionError as error:
            logger.warning(
                "could not advance company %s processing_status to %s: %s",
                company_id,
                status.value,
                error,
            )

    async def _finish_company_status(self, run: ExtractionRun) -> None:
        final_status = (
            ProcessingStatus.EXTRACTED
            if run.status
            in (
                ExtractionStatus.COMPLETED,
                ExtractionStatus.COMPLETED_WITH_WARNINGS,
                ExtractionStatus.PARTIAL,
            )
            else ProcessingStatus.FAILED
        )
        await self._advance_processing_status(run.company_id, final_status)

    async def _project_latest_facts(self, company_id: str) -> None:
        fact_page = await self._repository.list_facts_by_company(
            company_id, page=1, page_size=10_000, include_stale=True
        )
        projection = build_projection(fact_page.items)
        # Currently a documented no-op (contract resolution #3) — called
        # anyway so the wiring is correct once the follow-up lands.
        await self._company_gateway.project_latest_facts(company_id, projection)
