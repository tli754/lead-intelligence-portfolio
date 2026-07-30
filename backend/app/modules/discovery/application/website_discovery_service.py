"""Orchestrates a full discovery run.

Depends only on the domain layer's ports (`CompanyDiscoveryGateway`,
`DiscoveryRepository`, `HttpDiscoveryClient`) — never a concrete Mongo
class or `httpx` directly, and never imports FastAPI.

Since Task 020 (`docs/contracts/active/020-rq-discovery-vertical-
slice.md`), the work `run_discovery` used to do in one call is split
into `enqueue_discovery_run` (fast: persists a `queued` `DiscoveryRun`,
no network I/O — safe to call synchronously from an HTTP request) and
`execute_discovery_run` (the actual homepage/robots/sitemap pipeline,
re-anchored on a `discovery_run_id` looked up fresh from the repository —
callable by an RQ worker with nothing but that id, per
`infrastructure/rq_jobs.py`). `run_discovery` is kept as a thin composed
wrapper of the two, unchanged in external behavior, for backward
compatibility and for local development without a running Redis/worker.
"""

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import urlsplit

from app.modules.companies.domain.enums import ProcessingStatus
from app.modules.companies.domain.exceptions import InvalidStatusTransitionError
from app.modules.discovery.domain.config import DiscoveryConfig
from app.modules.discovery.domain.domain_relationships import (
    is_same_domain,
    is_same_registrable_domain,
)
from app.modules.discovery.domain.enums import DiscoverySource, DiscoveryStatus
from app.modules.discovery.domain.exceptions import DiscoveryFetchError, DiscoveryRunNotFoundError
from app.modules.discovery.domain.gateway import CompanyDiscoveryGateway
from app.modules.discovery.domain.html_link_extractor import (
    ExtractedLink,
    ExtractionResult,
    extract_links,
)
from app.modules.discovery.domain.http_client import HttpDiscoveryClient
from app.modules.discovery.domain.models import ClassificationResult, DiscoveryRun, DiscoverySummary
from app.modules.discovery.domain.page_classifier import PageType, classify_page_type
from app.modules.discovery.domain.priority_assigner import assign_priority
from app.modules.discovery.domain.reconciliation import DiscoveryCandidate, reconcile
from app.modules.discovery.domain.repository import DiscoveryRepository
from app.modules.discovery.domain.robots_parser import parse_robots_txt
from app.modules.discovery.domain.sitemap_parser import parse_sitemap_document
from app.modules.discovery.domain.url_normalizer import extract_hostname, normalize_discovered_url

logger = logging.getLogger(__name__)

_HOMEPAGE_CLASSIFICATION = ClassificationResult(
    page_type=PageType.HOMEPAGE, confidence=100, rule_id="path:homepage:/"
)

CancellationCheck = Callable[[], bool]


def homepage_candidate_urls(root_domain: str) -> list[str]:
    """The four homepage candidates, in the task's exact preference order."""
    return [
        f"https://{root_domain}",
        f"https://www.{root_domain}",
        f"http://{root_domain}",
        f"http://www.{root_domain}",
    ]


class WebsiteDiscoveryService:
    def __init__(
        self,
        *,
        company_gateway: CompanyDiscoveryGateway,
        discovery_repository: DiscoveryRepository,
        http_client: HttpDiscoveryClient,
        config: DiscoveryConfig | None = None,
    ) -> None:
        self._company_gateway = company_gateway
        self._repository = discovery_repository
        self._http_client = http_client
        self._config = config or DiscoveryConfig()

    async def enqueue_discovery_run(self, company_id: str) -> DiscoveryRun:
        """Validates the company reference and persists a fresh `queued`
        `DiscoveryRun` — everything `run_discovery` used to do *before*
        execution started. No homepage resolution, robots/sitemap fetch, or
        link extraction is attempted here, and company `processing.status`
        is **not** advanced here (see `execute_discovery_run` for why).
        This method's only I/O is the company-domain lookup and the run's
        own persistence, so it is safe and fast to run synchronously inside
        an HTTP request."""
        now = datetime.now(UTC)
        root_domain = await self._company_gateway.get_company_domain(company_id)

        run = DiscoveryRun(
            company_id=company_id, root_domain=root_domain, created_at=now, updated_at=now
        )
        return await self._repository.create_run(run)

    async def execute_discovery_run(
        self,
        discovery_run_id: str,
        *,
        cancellation_check: CancellationCheck | None = None,
    ) -> DiscoveryRun:
        """Runs the actual discovery pass for a run previously created by
        `enqueue_discovery_run`, looked up fresh from the repository —
        callable by a worker with nothing but the `discovery_run_id`.
        Everything `run_discovery` used to do *after* run creation,
        unchanged in substance."""
        run = await self._repository.get_run(discovery_run_id)
        if run is None:
            raise DiscoveryRunNotFoundError(discovery_run_id)

        start = time.monotonic()
        now = datetime.now(UTC)
        company_id = run.company_id
        root_domain = run.root_domain

        run.status = DiscoveryStatus.RUNNING
        run.started_at = now
        run.updated_at = run.started_at
        run = await self._repository.update_run(run) or run

        # The companies module's ProcessingStatus transition graph requires
        # DISCOVERING as an intermediate step before DISCOVERED — going
        # straight from e.g. IMPORTED to DISCOVERED is rejected as an
        # invalid transition. Every resting state that can start a *new*
        # discovery run (imported, ready, partial, failed, stale) allows
        # DISCOVERING. Re-running discovery on a company already past that
        # point (discovered, crawling, ...) does not — best-effort here,
        # since the discovery run itself is still valid and shouldn't be
        # discarded over a status-graph disagreement in another module.
        await self._advance_processing_status(company_id, ProcessingStatus.DISCOVERING)

        if self._is_cancelled(cancellation_check):
            return await self._finish_as_cancelled(run, start)

        try:
            resolution = await self._http_client.resolve_homepage(
                homepage_candidate_urls(root_domain)
            )
        except Exception as error:  # a homepage-resolution bug must still fail cleanly
            return await self._finish_as_failed(run, start, error=str(error))

        if not resolution.success or resolution.html is None or resolution.homepage_url is None:
            return await self._finish_as_failed(
                run,
                start,
                error=resolution.failure_reason or "homepage resolution failed",
            )

        run.homepage_url = resolution.homepage_url
        warnings: list[str] = []
        all_candidates: list[DiscoveryCandidate] = []

        all_candidates.append(
            DiscoveryCandidate(
                url=resolution.homepage_url,
                normalized_url=resolution.homepage_url,
                source=DiscoverySource.HOMEPAGE,
                source_url=resolution.homepage_url,
                anchor_text=None,
                depth=0,
                classification=_HOMEPAGE_CLASSIFICATION,
                is_same_domain=True,
                priority=assign_priority(
                    page_type=PageType.HOMEPAGE,
                    normalized_url=resolution.homepage_url,
                    is_same_domain=True,
                    config=self._config,
                ),
            )
        )

        if self._is_cancelled(cancellation_check):
            return await self._finish_as_cancelled(run, start)

        extraction = extract_links(resolution.html, source_url=resolution.homepage_url)
        all_candidates.extend(
            self._candidates_from_extraction(extraction, root_domain=root_domain)
        )

        if self._is_cancelled(cancellation_check):
            return await self._finish_as_cancelled(run, start)

        robots_sitemap_urls = await self._fetch_robots_sitemaps(resolution.homepage_url, warnings)
        summary_robots_urls_found = len(robots_sitemap_urls)

        if self._is_cancelled(cancellation_check):
            return await self._finish_as_cancelled(run, start)

        sitemap_candidates, sitemap_urls_found = await self._process_sitemaps(
            robots_sitemap_urls, root_domain=root_domain, warnings=warnings
        )
        all_candidates.extend(sitemap_candidates)

        if self._is_cancelled(cancellation_check):
            return await self._finish_as_cancelled(run, start)

        urls_found = len(all_candidates)
        if len(all_candidates) > self._config.max_urls_per_run:
            warnings.append(
                f"discovery exceeded max_urls_per_run ({self._config.max_urls_per_run}); "
                f"truncated {len(all_candidates) - self._config.max_urls_per_run} candidates"
            )
            all_candidates = all_candidates[: self._config.max_urls_per_run]

        reconciled = reconcile(
            all_candidates,
            company_id=company_id,
            discovery_run_id=run.discovery_run_id,
            discovered_at=now,
        )

        existing_urls = {
            candidate.normalized_url
            for candidate in reconciled
            if await self._repository.find_existing_url(
                run.discovery_run_id, candidate.normalized_url
            )
        }
        to_save = [url for url in reconciled if url.normalized_url not in existing_urls]
        await self._repository.save_discovered_urls(to_save)

        urls_excluded = sum(1 for url in reconciled if url.priority.value == "excluded")
        urls_accepted = len(reconciled) - urls_excluded

        run.summary = DiscoverySummary(
            urls_found=urls_found,
            urls_accepted=urls_accepted,
            urls_excluded=urls_excluded,
            sitemap_urls_found=sitemap_urls_found,
            robots_urls_found=summary_robots_urls_found,
            duplicate_urls_merged=len(all_candidates) - len(reconciled),
            warnings=len(warnings),
            duration_ms=int((time.monotonic() - start) * 1000),
        )
        run.status = (
            DiscoveryStatus.COMPLETED_WITH_WARNINGS if warnings else DiscoveryStatus.COMPLETED
        )
        run.completed_at = datetime.now(UTC)
        run.updated_at = run.completed_at
        run = await self._repository.update_run(run) or run

        await self._advance_processing_status(company_id, ProcessingStatus.DISCOVERED)
        await self._company_gateway.update_latest_discovery_run(company_id, run.discovery_run_id)

        return run

    async def run_discovery(
        self,
        company_id: str,
        *,
        cancellation_check: CancellationCheck | None = None,
    ) -> DiscoveryRun:
        """Composed convenience, kept for backward compatibility: calls
        `enqueue_discovery_run` then `execute_discovery_run` in sequence,
        exactly reproducing the pre-RQ synchronous behavior. Preserved
        (not deleted) so the existing fakes-based integration suite keeps
        passing unmodified, and so a non-queue, synchronous code path
        remains available for local development without a running
        Redis/worker. The router no longer calls this method."""
        run = await self.enqueue_discovery_run(company_id)
        return await self.execute_discovery_run(
            run.discovery_run_id, cancellation_check=cancellation_check
        )

    def _candidates_from_extraction(
        self, extraction: ExtractionResult, *, root_domain: str
    ) -> list[DiscoveryCandidate]:
        candidates: list[DiscoveryCandidate] = []
        for link in extraction.links:
            candidates.extend(self._candidates_for_link(link, root_domain=root_domain))

        for candidate_url, source in (
            (extraction.canonical_url, DiscoverySource.CANONICAL),
            *((url, DiscoverySource.ALTERNATE) for url in extraction.alternate_urls),
        ):
            if not candidate_url:
                continue
            candidates.append(
                self._single_candidate(
                    href=candidate_url,
                    normalized_url=candidate_url,
                    source=source,
                    source_url=(
                        extraction.links[0].source_url if extraction.links else candidate_url
                    ),
                    anchor_text=None,
                    depth=1,
                    root_domain=root_domain,
                )
            )
        return candidates

    def _candidates_for_link(
        self, link: ExtractedLink, *, root_domain: str
    ) -> list[DiscoveryCandidate]:
        host = extract_hostname(link.resolved_url)
        same_domain = is_same_domain_or_registrable(host, root_domain)
        classification = classify_page_type(
            normalized_path=urlsplit(link.resolved_url).path, anchor_texts=link.anchor_texts
        )
        priority = assign_priority(
            page_type=classification.page_type,
            normalized_url=link.resolved_url,
            is_same_domain=same_domain,
            config=self._config,
        )
        anchor_iter: list[str | None] = list(link.anchor_texts) if link.anchor_texts else [None]

        candidates: list[DiscoveryCandidate] = []
        for source in link.sources:
            for anchor_text in anchor_iter:
                candidates.append(
                    DiscoveryCandidate(
                        url=link.href,
                        normalized_url=link.resolved_url,
                        source=source,
                        source_url=link.source_url,
                        anchor_text=anchor_text,
                        depth=link.depth,
                        classification=classification,
                        is_same_domain=same_domain,
                        priority=priority,
                    )
                )
        return candidates

    def _single_candidate(
        self,
        *,
        href: str,
        normalized_url: str,
        source: DiscoverySource,
        source_url: str,
        anchor_text: str | None,
        depth: int,
        root_domain: str,
    ) -> DiscoveryCandidate:
        host = extract_hostname(normalized_url)
        same_domain = is_same_domain_or_registrable(host, root_domain)
        classification = classify_page_type(normalized_path=urlsplit(normalized_url).path)
        priority = assign_priority(
            page_type=classification.page_type,
            normalized_url=normalized_url,
            is_same_domain=same_domain,
            config=self._config,
        )
        return DiscoveryCandidate(
            url=href,
            normalized_url=normalized_url,
            source=source,
            source_url=source_url,
            anchor_text=anchor_text,
            depth=depth,
            classification=classification,
            is_same_domain=same_domain,
            priority=priority,
        )

    async def _fetch_robots_sitemaps(self, homepage_url: str, warnings: list[str]) -> list[str]:
        robots_url = _robots_url_for(homepage_url)
        try:
            result = await self._http_client.fetch_text(robots_url)
        except DiscoveryFetchError as error:
            # A missing/unreachable robots.txt is normal, not a failure.
            logger.info("robots.txt unavailable for %s: %s", robots_url, error)
            return []
        except Exception as error:  # any other robots-phase problem is non-fatal
            warnings.append(f"robots.txt fetch failed: {error}")
            return []

        try:
            policy = parse_robots_txt(result.text)
        except Exception as error:
            warnings.append(f"robots.txt parse failed: {error}")
            return []

        warnings.extend(policy.warnings)
        return policy.sitemap_urls

    async def _process_sitemaps(
        self, sitemap_urls: list[str], *, root_domain: str, warnings: list[str]
    ) -> tuple[list[DiscoveryCandidate], int]:
        visited: set[str] = set()
        candidates: list[DiscoveryCandidate] = []
        queue: list[tuple[str, int, bool]] = [(url, 0, False) for url in sitemap_urls]
        files_fetched = 0
        total_urls_found = 0

        while queue and files_fetched < self._config.max_sitemap_files:
            raw_url, depth, via_index = queue.pop(0)

            normalization = normalize_discovered_url(raw_url, retain_query=True)
            if not normalization.is_valid or normalization.normalized_url is None:
                warnings.append(f"skipped invalid sitemap URL: {raw_url!r}")
                continue

            sitemap_url = normalization.normalized_url
            if sitemap_url in visited:
                continue
            visited.add(sitemap_url)

            if depth > self._config.max_sitemap_depth:
                warnings.append(f"sitemap nesting exceeded max depth at {sitemap_url!r}")
                continue

            files_fetched += 1
            try:
                fetch_result = await self._http_client.fetch_binary(sitemap_url)
            except DiscoveryFetchError as error:
                warnings.append(f"failed to fetch sitemap {sitemap_url!r}: {error}")
                continue
            except Exception as error:  # one bad sitemap must not fail the whole run
                warnings.append(f"unexpected error fetching sitemap {sitemap_url!r}: {error}")
                continue

            try:
                parsed = parse_sitemap_document(
                    fetch_result.body,
                    content_type=fetch_result.content_type,
                    source_sitemap_url=sitemap_url,
                    root_domain=root_domain,
                    config=self._config,
                )
            except Exception as error:
                warnings.append(f"failed to parse sitemap {sitemap_url!r}: {error}")
                continue

            warnings.extend(parsed.warnings)

            if parsed.is_index:
                for nested_url in parsed.nested_sitemap_urls:
                    queue.append((nested_url, depth + 1, True))
                continue

            total_urls_found += parsed.total_url_count
            source = DiscoverySource.SITEMAP_INDEX if via_index else DiscoverySource.SITEMAP
            sitemap_context = "product" if parsed.product_sitemap_detected else None

            for entry in parsed.url_entries:
                host = extract_hostname(entry.normalized_url)
                same_domain = is_same_domain_or_registrable(host, root_domain)
                classification = classify_page_type(
                    normalized_path=urlsplit(entry.normalized_url).path,
                    sitemap_context=sitemap_context,
                )
                priority = assign_priority(
                    page_type=classification.page_type,
                    normalized_url=entry.normalized_url,
                    is_same_domain=same_domain,
                    config=self._config,
                )
                candidates.append(
                    DiscoveryCandidate(
                        url=entry.loc,
                        normalized_url=entry.normalized_url,
                        source=source,
                        source_url=sitemap_url,
                        anchor_text=None,
                        depth=1,
                        classification=classification,
                        is_same_domain=same_domain,
                        priority=priority,
                    )
                )

        return candidates, total_urls_found

    def _is_cancelled(self, cancellation_check: CancellationCheck | None) -> bool:
        return cancellation_check is not None and cancellation_check()

    async def _finish_as_failed(
        self, run: DiscoveryRun, start: float, *, error: str
    ) -> DiscoveryRun:
        run.status = DiscoveryStatus.FAILED
        run.error = error
        run.completed_at = datetime.now(UTC)
        run.updated_at = run.completed_at
        run.summary.duration_ms = int((time.monotonic() - start) * 1000)
        run = await self._repository.update_run(run) or run
        await self._advance_processing_status(run.company_id, ProcessingStatus.FAILED)
        return run

    async def _finish_as_cancelled(self, run: DiscoveryRun, start: float) -> DiscoveryRun:
        return await self._finish_as_failed(run, start, error="cancelled")

    async def _advance_processing_status(self, company_id: str, status: ProcessingStatus) -> None:
        """Best-effort: another pipeline stage may have already moved the
        company past `status` (e.g. re-running discovery on a company
        that's already been crawled) — the companies module's transition
        graph then rejects the move. That disagreement is logged and
        swallowed rather than allowed to crash the whole discovery run,
        since discovery's own results are still valid regardless of
        whether this side-effect status update lands."""
        try:
            await self._company_gateway.update_processing_status(company_id, status)
        except InvalidStatusTransitionError as error:
            logger.warning(
                "could not advance company %s processing_status to %s: %s",
                company_id,
                status.value,
                error,
            )


def is_same_domain_or_registrable(host: str | None, root_domain: str) -> bool:
    """`DiscoveredUrl.is_same_domain` is interpreted as "same registrable
    domain as the company's root domain" — the more useful check in
    practice, since a resolved homepage often lives on `www.` or another
    subdomain of the root domain rather than an exact match."""
    return is_same_domain(host, root_domain) or is_same_registrable_domain(host, root_domain)


def _robots_url_for(homepage_url: str) -> str:
    parts = urlsplit(homepage_url)
    return f"{parts.scheme}://{parts.netloc}/robots.txt"
