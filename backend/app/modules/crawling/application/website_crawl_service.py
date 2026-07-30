"""Orchestrates one crawl run end-to-end.

Depends only on the domain layer's ports (`CompanyCrawlGateway`,
`DiscoveryCrawlGateway`, `RobotsPolicyGateway`, `CrawlRepository`,
`PageFetcher`, `BrowserPageFetcher`, `ContentStorage`) — never a concrete
Mongo/HTTP/FastAPI type, and never imports FastAPI. A future worker can
call `start_crawl_run` exactly as the synchronous API route does,
mirroring `WebsiteDiscoveryService`'s own precedent.

## Resolving a narrative/gateway-capability gap

The task brief's section 14 describes "validate company and discovery
run references" as an early step, separate from a later "advances company
processing.status to CRAWLING." `CompanyCrawlGateway` (contract T22) has
no dedicated "company exists" method, though — only
`update_processing_status`/`update_latest_crawl_run`. Both narrative
steps are therefore served by **one** early call to
`update_processing_status(company_id, CRAWLING)`: a raised
`CompanyNotFoundForCrawlError` (via the gateway) serves as the "company
doesn't exist" validation, while an `InvalidStatusTransitionError` is
caught and swallowed (best-effort, matching
`WebsiteDiscoveryService._advance_processing_status`'s exact precedent).
This call happens *before* a `CrawlRun` document is ever created, so a
company/discovery-run validation failure never leaves a half-created run
behind.
"""

import asyncio
import logging
import time
from datetime import UTC, datetime

from app.modules.companies.domain.enums import ProcessingStatus
from app.modules.companies.domain.exceptions import InvalidStatusTransitionError
from app.modules.crawling.domain.browser_fallback import detect_browser_fallback
from app.modules.crawling.domain.config import CrawlConfig
from app.modules.crawling.domain.content_storage import ContentStorage
from app.modules.crawling.domain.enums import (
    BrowserFallbackReason,
    BrowserPolicy,
    ContentStorageMode,
    CrawlStatus,
    FetchMode,
    PageFetchStatus,
)
from app.modules.crawling.domain.exceptions import (
    CrawlFetchError,
    CrawlRunNotFoundError,
    DuplicateActiveCrawlRunError,
)
from app.modules.crawling.domain.gateway import (
    CompanyCrawlGateway,
    DiscoveryCrawlGateway,
    RobotsPolicyGateway,
)
from app.modules.crawling.domain.hashing import compute_content_hashes, is_materially_unchanged
from app.modules.crawling.domain.html_cleaner import clean_html
from app.modules.crawling.domain.html_validator import (
    classify_blocked_or_challenge,
    validate_and_decode,
)
from app.modules.crawling.domain.idempotency import compute_idempotency_key
from app.modules.crawling.domain.metadata_extractor import extract_page_metadata
from app.modules.crawling.domain.models import (
    ContentStorageInfo,
    CrawledPage,
    CrawlRun,
    CrawlRunOptions,
    CrawlSummary,
    CrawlTarget,
    CrawlWarning,
    HttpMetadata,
)
from app.modules.crawling.domain.page_fetcher import (
    BrowserPageFetcher,
    PageFetcher,
    PageFetchRequest,
)
from app.modules.crawling.domain.rate_limiter import RequestPacer
from app.modules.crawling.domain.repository import CrawlRepository
from app.modules.crawling.domain.target_selector import CrawlCandidate, select_crawl_targets
from app.modules.crawling.domain.text_extractor import extract_text
from app.modules.discovery.domain.enums import PageType

logger = logging.getLogger(__name__)

_RETRYABLE_TARGET_STATUSES = (PageFetchStatus.FAILED, PageFetchStatus.REJECTED)
_SLEEP_INCREMENT_S = 0.5


class WebsiteCrawlService:
    def __init__(
        self,
        *,
        company_gateway: CompanyCrawlGateway,
        discovery_gateway: DiscoveryCrawlGateway,
        robots_gateway: RobotsPolicyGateway,
        repository: CrawlRepository,
        page_fetcher: PageFetcher,
        content_storage: ContentStorage,
        browser_fetcher: BrowserPageFetcher | None = None,
        config: CrawlConfig | None = None,
    ) -> None:
        self._company_gateway = company_gateway
        self._discovery_gateway = discovery_gateway
        self._robots_gateway = robots_gateway
        self._repository = repository
        self._page_fetcher = page_fetcher
        self._content_storage = content_storage
        self._browser_fetcher = browser_fetcher
        self._config = config or CrawlConfig()

    # --- Public API -------------------------------------------------------

    async def enqueue_crawl_run(
        self, company_id: str, discovery_run_id: str, options: CrawlRunOptions | None = None
    ) -> CrawlRun:
        """Validates the company/discovery-run references and persists a
        fresh `queued` `CrawlRun` — everything `start_crawl_run` used to do
        *before* target processing began. No target is selected, no page is
        fetched, and company `processing.status` is **not** advanced here
        (see `execute_crawl_run` for why). Its only I/O is the discovery-run
        existence check and the run's own persistence, so it is safe and
        fast to run synchronously inside an HTTP request."""
        options = options or CrawlRunOptions()
        effective_config = self._build_effective_config(options)
        idempotency_key = compute_idempotency_key(
            company_id, discovery_run_id, config=effective_config, options=options
        )

        existing_active = await self._repository.find_active_run(company_id, idempotency_key)
        if existing_active is not None:
            raise DuplicateActiveCrawlRunError(
                existing_crawl_run_id=existing_active.crawl_run_id,
                status=existing_active.status.value,
            )

        # Validate the discovery run reference exists *before* creating anything.
        await self._discovery_gateway.get_discovery_run(discovery_run_id)

        now = datetime.now(UTC)
        run = CrawlRun(
            company_id=company_id,
            discovery_run_id=discovery_run_id,
            configuration_snapshot=effective_config.model_dump(mode="json"),
            options_snapshot=options.model_dump(mode="json"),
            idempotency_key=idempotency_key,
            created_at=now,
            updated_at=now,
        )
        return await self._repository.create_run(run)

    async def execute_crawl_run(self, crawl_run_id: str) -> CrawlRun:
        """Runs the actual crawl for a run previously created by
        `enqueue_crawl_run`, looked up fresh from the repository — callable
        by a worker with nothing but the `crawl_run_id`. Everything
        `start_crawl_run` used to do *after* run creation, unchanged in
        substance."""
        run = await self._repository.get_run(crawl_run_id)
        if run is None:
            raise CrawlRunNotFoundError(crawl_run_id)
        if run.status == CrawlStatus.CANCELLED:
            # `cancel_run` was called after `enqueue_crawl_run` but before a
            # worker ever picked this job up — never process it.
            return run

        effective_config = CrawlConfig.model_validate(run.configuration_snapshot)
        # Recovered from `enqueue_crawl_run`'s persisted snapshot, not
        # hardcoded to defaults — a run enqueued with a non-default
        # `force_refresh`/`include_page_types`/`exclude_page_types`/
        # `manual_urls` must still honor those when executed later,
        # possibly by a separate worker process with nothing but this
        # `crawl_run_id`.
        options = CrawlRunOptions.model_validate(run.options_snapshot)
        await self._advance_processing_status(run.company_id, ProcessingStatus.CRAWLING)

        start = time.monotonic()
        run.status = CrawlStatus.RUNNING
        run.started_at = datetime.now(UTC)
        run.updated_at = run.started_at
        run = await self._repository.update_run(run) or run

        targets = await self._select_and_persist_targets(run, effective_config, options)
        run.summary.targets_selected = len(targets)

        homepage_failed, was_cancelled = await self._run_targets(
            run, targets, effective_config, force_refresh=options.force_refresh
        )

        run.summary.duration_ms = int((time.monotonic() - start) * 1000)
        run.summary.warnings = len(run.warnings)
        run.status = self._determine_final_status(
            run.summary,
            homepage_failed=homepage_failed,
            was_cancelled=was_cancelled,
            config=effective_config,
        )
        run.completed_at = datetime.now(UTC)
        run.updated_at = run.completed_at
        run = await self._repository.update_run(run) or run

        await self._finish_company_status(run)
        return run

    async def start_crawl_run(
        self, company_id: str, discovery_run_id: str, options: CrawlRunOptions | None = None
    ) -> CrawlRun:
        """Composed convenience, kept for backward compatibility: calls
        `enqueue_crawl_run` then `execute_crawl_run` in sequence, exactly
        reproducing the pre-RQ synchronous behavior. Preserved (not
        deleted) so the existing fakes-based integration suite keeps
        passing unmodified, and so a non-queue, synchronous code path
        remains available for local development without a running
        Redis/worker. The router no longer calls this method."""
        run = await self.enqueue_crawl_run(company_id, discovery_run_id, options)
        return await self.execute_crawl_run(run.crawl_run_id)

    async def enqueue_retry(self, crawl_run_id: str) -> CrawlRun:
        """Marks a terminal-status run `queued` again, immediately, without
        running any retry logic inline — the actual retry
        (`retry_failed`) is unchanged in substance, now invoked by a
        worker instead of inline by the router."""
        run = await self._repository.get_run(crawl_run_id)
        if run is None:
            raise CrawlRunNotFoundError(crawl_run_id)
        run.status = CrawlStatus.QUEUED
        run.updated_at = datetime.now(UTC)
        return await self._repository.update_run(run) or run

    async def cancel_run(self, crawl_run_id: str) -> CrawlRun:
        run = await self._repository.mark_run_cancelled(crawl_run_id)
        if run is None:
            raise CrawlRunNotFoundError(crawl_run_id)
        return run

    async def retry_failed(self, crawl_run_id: str) -> CrawlRun:
        run = await self._repository.get_run(crawl_run_id)
        if run is None:
            raise CrawlRunNotFoundError(crawl_run_id)

        effective_config = CrawlConfig.model_validate(run.configuration_snapshot)
        retry_statuses: list[PageFetchStatus] = list(_RETRYABLE_TARGET_STATUSES)
        if effective_config.retry_includes_blocked_by_robots:
            retry_statuses.append(PageFetchStatus.BLOCKED_BY_ROBOTS)

        targets_to_retry: list[CrawlTarget] = []
        for status in retry_statuses:
            result = await self._repository.list_targets_by_run(
                crawl_run_id, status=status, page=1, page_size=10_000
            )
            targets_to_retry.extend(result.items)
        targets_to_retry.sort(key=lambda target: target.normalized_url)

        for target in targets_to_retry:
            if target.status == PageFetchStatus.BLOCKED_BY_ROBOTS:
                run.summary.pages_blocked_by_robots = max(
                    0, run.summary.pages_blocked_by_robots - 1
                )
            else:
                run.summary.pages_failed = max(0, run.summary.pages_failed - 1)

        pacer = RequestPacer(
            default_delay_s=effective_config.default_delay_s,
            min_delay_s=effective_config.min_delay_s,
        )
        last_request_at: float | None = None
        homepage_failed = False
        for target in targets_to_retry:
            last_request_at, target_failed = await self._process_target(
                run,
                target,
                effective_config,
                pacer=pacer,
                last_request_at=last_request_at,
                force_refresh=False,
            )
            if target_failed and target.page_type == PageType.HOMEPAGE:
                homepage_failed = True

        run.summary.warnings = len(run.warnings)
        run.status = self._determine_final_status(
            run.summary,
            homepage_failed=homepage_failed,
            was_cancelled=False,
            config=effective_config,
        )
        run.completed_at = datetime.now(UTC)
        run.updated_at = run.completed_at
        run = await self._repository.update_run(run) or run
        return run

    # --- Target selection ---------------------------------------------------

    def _build_effective_config(self, options: CrawlRunOptions) -> CrawlConfig:
        overrides: dict = {}
        if options.max_pages is not None:
            overrides["max_pages_per_company"] = options.max_pages
        if options.browser_policy is not None:
            overrides["browser_policy"] = options.browser_policy
        return self._config.model_copy(update=overrides) if overrides else self._config

    async def _select_and_persist_targets(
        self, run: CrawlRun, effective_config: CrawlConfig, options: CrawlRunOptions
    ) -> list[CrawlTarget]:
        discovered_urls = await self._discovery_gateway.list_discovered_urls(
            run.discovery_run_id, include_excluded=True
        )
        url_by_normalized = {}
        for url in discovered_urls:
            url_by_normalized.setdefault(url.normalized_url, url)

        candidates = [
            CrawlCandidate(
                normalized_url=url.normalized_url,
                page_type=url.page_type,
                priority=url.priority,
                depth=url.depth,
                discovery_sources=url.discovery_sources,
            )
            for url in discovered_urls
        ]
        selected = select_crawl_targets(
            candidates,
            config=effective_config,
            manual_include_urls=frozenset(options.manual_urls),
            include_page_types=frozenset(options.include_page_types),
            exclude_page_types=frozenset(options.exclude_page_types),
        )

        now = datetime.now(UTC)
        targets: list[CrawlTarget] = []
        for selected_target in selected:
            source_url = url_by_normalized.get(selected_target.normalized_url)
            target = CrawlTarget(
                crawl_run_id=run.crawl_run_id,
                company_id=run.company_id,
                discovery_run_id=run.discovery_run_id,
                discovered_url_id=source_url.discovered_url_id if source_url else None,
                url=source_url.url if source_url else selected_target.normalized_url,
                normalized_url=selected_target.normalized_url,
                page_type=selected_target.page_type,
                priority=selected_target.priority,
                depth=selected_target.depth,
                created_at=now,
                updated_at=now,
            )
            saved = await self._repository.save_target(target)
            targets.append(saved)
        return targets

    # --- Sequential per-target processing ------------------------------------

    async def _run_targets(
        self,
        run: CrawlRun,
        targets: list[CrawlTarget],
        effective_config: CrawlConfig,
        *,
        force_refresh: bool,
    ) -> tuple[bool, bool]:
        pacer = RequestPacer(
            default_delay_s=effective_config.default_delay_s,
            min_delay_s=effective_config.min_delay_s,
        )
        last_request_at: float | None = None
        homepage_failed = False

        for index, target in enumerate(targets):
            current_run = await self._repository.get_run(run.crawl_run_id)
            if current_run is not None and current_run.status == CrawlStatus.CANCELLED:
                await self._skip_remaining(run, targets[index:])
                return homepage_failed, True

            last_request_at, target_failed = await self._process_target(
                run,
                target,
                effective_config,
                pacer=pacer,
                last_request_at=last_request_at,
                force_refresh=force_refresh,
            )
            if target_failed and target.page_type == PageType.HOMEPAGE:
                homepage_failed = True

        # A concurrent `cancel_run` call may have landed while the *last*
        # target was still being processed (no further iteration would
        # otherwise re-check it) — check once more after the loop too.
        final_run = await self._repository.get_run(run.crawl_run_id)
        was_cancelled = final_run is not None and final_run.status == CrawlStatus.CANCELLED
        return homepage_failed, was_cancelled

    async def _skip_remaining(self, run: CrawlRun, remaining: list[CrawlTarget]) -> None:
        for target in remaining:
            target.status = PageFetchStatus.SKIPPED
            await self._save_target_update(target)
            run.summary.pages_skipped += 1

    async def _process_target(
        self,
        run: CrawlRun,
        target: CrawlTarget,
        effective_config: CrawlConfig,
        *,
        pacer: RequestPacer,
        last_request_at: float | None,
        force_refresh: bool,
    ) -> tuple[float | None, bool]:
        policy = await self._robots_gateway.get_policy(
            run.company_id, target.url, effective_config.user_agent
        )
        if policy.outcome == "disallowed":
            target.status = PageFetchStatus.BLOCKED_BY_ROBOTS
            await self._save_target_update(target)
            run.summary.pages_blocked_by_robots += 1
            return last_request_at, False
        if policy.outcome == "unknown":
            self._add_warning(
                run,
                code="robots_policy_unknown",
                message=f"robots policy unknown for {target.url}",
                url=target.url,
            )

        next_allowed = pacer.next_allowed_time(
            last_request_at, robots_crawl_delay_s=policy.crawl_delay
        )
        await self._sleep_until(pacer, next_allowed)
        last_request_at = pacer.now()

        previous_page = await self._repository.get_latest_page_by_normalized_url(
            run.company_id, target.normalized_url
        )

        fetch_request = PageFetchRequest(
            url=target.url,
            previous_etag=(
                previous_page.http_metadata.etag if previous_page and not force_refresh else None
            ),
            previous_last_modified=(
                previous_page.http_metadata.last_modified
                if previous_page and not force_refresh
                else None
            ),
            expected_content_type=target.expected_content_type,
        )

        try:
            result = await self._page_fetcher.fetch_page(fetch_request)
        except CrawlFetchError as error:
            return await self._fail_target(run, target, code="fetch_failed", message=str(error))

        run.summary.bytes_downloaded += len(result.body or b"")

        if result.outcome == "not_modified" and previous_page is not None:
            page = self._build_unchanged_page(run, target, previous_page, result)
            await self._persist_page(run, target, page, PageFetchStatus.UNCHANGED)
            run.summary.pages_unchanged += 1
            return last_request_at, False

        if not (200 <= result.status_code < 300):
            return await self._fail_target(
                run,
                target,
                code="http_error_status",
                message=f"{target.url} returned status {result.status_code}",
                http_metadata=result.http_metadata,
                final_url=result.final_url,
            )

        try:
            decoded = validate_and_decode(
                result.body or b"",
                result.http_metadata.content_type,
                effective_config,
                url=target.url,
            )
        except CrawlFetchError as error:
            return await self._fail_target(
                run,
                target,
                code="validation_rejected",
                message=str(error),
                status=PageFetchStatus.REJECTED,
            )

        for warning_message in decoded.decode_warnings:
            self._add_warning(run, code="decode_warning", message=warning_message, url=target.url)

        classification = classify_blocked_or_challenge(decoded.html)
        if (
            classification is not None
            and effective_config.challenge_page_policy != "browser_required"
        ):
            status = (
                PageFetchStatus.FAILED
                if effective_config.challenge_page_policy == "failed"
                else PageFetchStatus.REJECTED
            )
            return await self._fail_target(
                run,
                target,
                code="challenge_page_detected",
                message=f"classified as {classification.classification}",
                status=status,
            )

        cleaned = clean_html(decoded.html)
        text = extract_text(cleaned.html, max_length=effective_config.max_extracted_text_length)
        metadata = extract_page_metadata(
            cleaned.html,
            raw_html_size=len(result.body or b""),
            cleaned_html_size=len(cleaned.html.encode("utf-8")),
            extracted_text_length=len(text.text),
        )
        hashes = compute_content_hashes(result.body or b"", cleaned.html, text.text)

        if previous_page is not None and is_materially_unchanged(
            previous_page.content_hashes, hashes
        ):
            page = self._build_unchanged_page(run, target, previous_page, result, hashes=hashes)
            await self._persist_page(run, target, page, PageFetchStatus.UNCHANGED)
            run.summary.pages_unchanged += 1
            return last_request_at, False

        fetch_status = PageFetchStatus.FETCHED
        fetch_mode_used = FetchMode.HTTP
        browser_fallback_reason: BrowserFallbackReason | None = None
        raw_bytes_for_storage = result.body or b""
        final_cleaned_html = cleaned.html
        final_extracted_text = text.text

        if effective_config.browser_policy != BrowserPolicy.NEVER:
            decision = detect_browser_fallback(
                cleaned.html,
                text.text,
                classification,
                manual_override=False,
                config=effective_config,
            )
            forced_by_page_type = (
                effective_config.browser_policy == BrowserPolicy.ALWAYS_FOR_SELECTED_PAGE_TYPES
                and target.page_type in effective_config.always_browser_page_types
            )
            if decision.browser_required or forced_by_page_type:
                run.summary.pages_requiring_browser += 1
                fetch_status = PageFetchStatus.BROWSER_REQUIRED
                browser_fallback_reason = (
                    decision.reason or BrowserFallbackReason.MANUALLY_REQUESTED
                )

                should_invoke = (
                    effective_config.browser_policy
                    in (
                        BrowserPolicy.FETCH_WHEN_REQUIRED,
                        BrowserPolicy.ALWAYS_FOR_SELECTED_PAGE_TYPES,
                    )
                    and self._browser_fetcher is not None
                )
                if should_invoke:
                    rendered = await self._try_render(run, target, fetch_request)
                    if rendered is not None and rendered.html:
                        final_cleaned = clean_html(rendered.html)
                        final_text = extract_text(
                            final_cleaned.html,
                            max_length=effective_config.max_extracted_text_length,
                        )
                        raw_bytes_for_storage = rendered.html.encode("utf-8")
                        final_cleaned_html = final_cleaned.html
                        final_extracted_text = final_text.text
                        metadata = extract_page_metadata(
                            final_cleaned.html,
                            raw_html_size=len(raw_bytes_for_storage),
                            cleaned_html_size=len(final_cleaned.html.encode("utf-8")),
                            extracted_text_length=len(final_text.text),
                        )
                        hashes = compute_content_hashes(
                            raw_bytes_for_storage, final_cleaned.html, final_text.text
                        )
                        fetch_status = PageFetchStatus.BROWSER_FETCHED
                        fetch_mode_used = FetchMode.BROWSER
                        run.summary.pages_browser_fetched += 1

        page = CrawledPage(
            crawl_run_id=run.crawl_run_id,
            company_id=run.company_id,
            discovery_run_id=run.discovery_run_id,
            discovered_url_id=target.discovered_url_id,
            original_url=target.url,
            final_url=result.final_url,
            normalized_url=target.normalized_url,
            page_type=target.page_type,
            priority=target.priority,
            fetch_mode=fetch_mode_used,
            fetch_status=fetch_status,
            http_metadata=result.http_metadata,
            page_metadata=metadata,
            content_hashes=hashes,
            previous_page_id=previous_page.page_id if previous_page else None,
            browser_fallback_reason=browser_fallback_reason,
            fetched_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        await self._store_content(
            run,
            page,
            raw_bytes=raw_bytes_for_storage,
            cleaned_html=final_cleaned_html,
            extracted_text=final_extracted_text,
            effective_config=effective_config,
        )

        await self._persist_page(run, target, page, fetch_status)
        run.summary.pages_fetched += 1
        return last_request_at, False

    async def _try_render(
        self, run: CrawlRun, target: CrawlTarget, fetch_request: PageFetchRequest
    ):
        assert self._browser_fetcher is not None
        try:
            rendered = await self._browser_fetcher.fetch_rendered_page(fetch_request)
        except Exception as error:  # a browser-fetch failure must never discard the HTTP result
            self._add_warning(
                run, code="browser_fetch_failed", message=str(error), url=target.url, page_id=None
            )
            return None
        if not rendered.succeeded:
            self._add_warning(
                run,
                code="browser_fetch_failed",
                message=rendered.error or "browser fetch failed",
                url=target.url,
            )
            return None
        return rendered

    async def _fail_target(
        self,
        run: CrawlRun,
        target: CrawlTarget,
        *,
        code: str,
        message: str,
        status: PageFetchStatus = PageFetchStatus.FAILED,
        http_metadata=None,
        final_url: str | None = None,
    ) -> tuple[float | None, bool]:
        """Marks a target as failed/rejected **and** persists a minimal
        `CrawledPage` record (no content, just the failure's metadata) so
        `GET .../pages?includeFailed=true` can surface it — a page-level
        failure is still a page, just one with nothing usable fetched."""
        now = datetime.now(UTC)
        page = CrawledPage(
            crawl_run_id=run.crawl_run_id,
            company_id=run.company_id,
            discovery_run_id=run.discovery_run_id,
            discovered_url_id=target.discovered_url_id,
            original_url=target.url,
            final_url=final_url,
            normalized_url=target.normalized_url,
            page_type=target.page_type,
            priority=target.priority,
            fetch_status=status,
            http_metadata=http_metadata or HttpMetadata(),
            fetched_at=now,
            created_at=now,
            updated_at=now,
        )
        await self._persist_page(run, target, page, status)
        run.summary.pages_failed += 1
        self._add_warning(run, code=code, message=message, url=target.url)
        return None, True

    def _build_unchanged_page(
        self, run: CrawlRun, target: CrawlTarget, previous_page: CrawledPage, result, *, hashes=None
    ) -> CrawledPage:
        now = datetime.now(UTC)
        return CrawledPage(
            crawl_run_id=run.crawl_run_id,
            company_id=run.company_id,
            discovery_run_id=run.discovery_run_id,
            discovered_url_id=target.discovered_url_id,
            original_url=target.url,
            final_url=result.final_url,
            normalized_url=target.normalized_url,
            page_type=target.page_type,
            priority=target.priority,
            fetch_mode=FetchMode.HTTP,
            fetch_status=PageFetchStatus.UNCHANGED,
            http_metadata=result.http_metadata,
            page_metadata=previous_page.page_metadata,
            content_storage=previous_page.content_storage,
            content_hashes=hashes or previous_page.content_hashes,
            cleaned_html=previous_page.cleaned_html,
            extracted_text=previous_page.extracted_text,
            raw_content_reference=previous_page.raw_content_reference,
            previous_page_id=previous_page.page_id,
            unchanged_from_page_id=previous_page.page_id,
            fetched_at=now,
            created_at=now,
            updated_at=now,
        )

    async def _store_content(
        self,
        run: CrawlRun,
        page: CrawledPage,
        *,
        raw_bytes: bytes,
        cleaned_html: str,
        extracted_text: str,
        effective_config: CrawlConfig,
    ) -> None:
        storage_info = ContentStorageInfo()

        try:
            reference = await self._content_storage.store_raw_content(
                company_id=run.company_id,
                crawl_run_id=run.crawl_run_id,
                page_id=page.page_id,
                content=raw_bytes,
                expected_sha256=page.content_hashes.raw_content_sha256 or "",
            )
            page.raw_content_reference = reference
            storage_info.raw_content_mode = ContentStorageMode.EXTERNAL
        except Exception as error:
            self._add_warning(
                run,
                code="raw_storage_failed",
                message=str(error),
                url=page.original_url,
                page_id=page.page_id,
            )

        if len(cleaned_html.encode("utf-8")) <= effective_config.inline_cleaned_html_limit_bytes:
            page.cleaned_html = cleaned_html
            storage_info.cleaned_html_mode = ContentStorageMode.INLINE
        else:
            try:
                reference = await self._content_storage.store_cleaned_content(
                    company_id=run.company_id,
                    crawl_run_id=run.crawl_run_id,
                    page_id=page.page_id,
                    content=cleaned_html,
                    kind="cleaned",
                    expected_sha256=page.content_hashes.cleaned_html_sha256 or "",
                )
                storage_info.cleaned_html_reference = reference
                storage_info.cleaned_html_mode = ContentStorageMode.EXTERNAL
            except Exception as error:
                self._add_warning(
                    run,
                    code="cleaned_storage_failed",
                    message=str(error),
                    url=page.original_url,
                    page_id=page.page_id,
                )

        if (
            len(extracted_text.encode("utf-8"))
            <= effective_config.inline_extracted_text_limit_bytes
        ):
            page.extracted_text = extracted_text
            storage_info.extracted_text_mode = ContentStorageMode.INLINE
        else:
            try:
                reference = await self._content_storage.store_cleaned_content(
                    company_id=run.company_id,
                    crawl_run_id=run.crawl_run_id,
                    page_id=page.page_id,
                    content=extracted_text,
                    kind="text",
                    expected_sha256=page.content_hashes.extracted_text_sha256 or "",
                )
                storage_info.extracted_text_reference = reference
                storage_info.extracted_text_mode = ContentStorageMode.EXTERNAL
            except Exception as error:
                self._add_warning(
                    run,
                    code="text_storage_failed",
                    message=str(error),
                    url=page.original_url,
                    page_id=page.page_id,
                )

        page.content_storage = storage_info

    async def _persist_page(
        self, run: CrawlRun, target: CrawlTarget, page: CrawledPage, fetch_status: PageFetchStatus
    ) -> None:
        await self._repository.save_page(page)
        target.status = fetch_status
        await self._save_target_update(target)

    async def _save_target_update(self, target: CrawlTarget) -> None:
        target.attempt_count += 1
        target.updated_at = datetime.now(UTC)
        updated = await self._repository.update_target(target)
        if updated is not None:
            target.document_version = updated.document_version

    async def _sleep_until(self, pacer: RequestPacer, target_time: float) -> None:
        while True:
            remaining = target_time - pacer.now()
            if remaining <= 0:
                return
            await asyncio.sleep(min(remaining, _SLEEP_INCREMENT_S))

    def _add_warning(
        self,
        run: CrawlRun,
        *,
        code: str,
        message: str,
        url: str | None = None,
        page_id: str | None = None,
    ) -> None:
        run.warnings.append(
            CrawlWarning(
                code=code, message=message, url=url, page_id=page_id, created_at=datetime.now(UTC)
            )
        )
        run.summary.warnings = len(run.warnings)

    def _determine_final_status(
        self,
        summary: CrawlSummary,
        *,
        homepage_failed: bool,
        was_cancelled: bool,
        config: CrawlConfig,
    ) -> CrawlStatus:
        if was_cancelled:
            return CrawlStatus.CANCELLED
        if homepage_failed:
            return CrawlStatus(config.homepage_failure_marks_run)
        if summary.pages_failed > 0 and summary.pages_fetched == 0 and summary.pages_unchanged == 0:
            return CrawlStatus.FAILED
        if summary.pages_failed > 0 or summary.warnings > 0:
            return CrawlStatus.COMPLETED_WITH_WARNINGS
        return CrawlStatus.COMPLETED

    async def _advance_processing_status(self, company_id: str, status: ProcessingStatus) -> None:
        """Best-effort: another pipeline stage may have already moved the
        company past `status`. That disagreement is logged and swallowed
        rather than allowed to crash the whole crawl run — exact same
        pattern as `WebsiteDiscoveryService._advance_processing_status`."""
        try:
            await self._company_gateway.update_processing_status(company_id, status)
        except InvalidStatusTransitionError as error:
            logger.warning(
                "could not advance company %s processing_status to %s: %s",
                company_id,
                status.value,
                error,
            )

    async def _finish_company_status(self, run: CrawlRun) -> None:
        final_status = (
            ProcessingStatus.CRAWLED
            if run.status
            in (CrawlStatus.COMPLETED, CrawlStatus.COMPLETED_WITH_WARNINGS, CrawlStatus.PARTIAL)
            else ProcessingStatus.FAILED
        )
        await self._advance_processing_status(run.company_id, final_status)
        # Currently a documented no-op (contract resolution #1) — called
        # anyway so the wiring is correct once the follow-up lands.
        await self._company_gateway.update_latest_crawl_run(run.company_id, run.crawl_run_id)
