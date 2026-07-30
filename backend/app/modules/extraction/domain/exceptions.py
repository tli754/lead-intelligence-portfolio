"""Domain-level errors for the extraction module."""


class ExtractionDomainError(Exception):
    """Base class for extraction-module domain errors."""


class CompanyNotFoundForExtractionError(ExtractionDomainError):
    def __init__(self, company_id: str) -> None:
        super().__init__(f"no company with company_id={company_id!r}")
        self.company_id = company_id


class CrawlRunNotFoundForExtractionError(ExtractionDomainError):
    def __init__(self, crawl_run_id: str) -> None:
        super().__init__(f"no crawl run with crawl_run_id={crawl_run_id!r}")
        self.crawl_run_id = crawl_run_id


class ExtractionRunNotFoundError(ExtractionDomainError):
    def __init__(self, extraction_run_id: str) -> None:
        super().__init__(f"no extraction run with extraction_run_id={extraction_run_id!r}")
        self.extraction_run_id = extraction_run_id


class FactNotFoundError(ExtractionDomainError):
    def __init__(self, fact_id: str) -> None:
        super().__init__(f"no fact with fact_id={fact_id!r}")
        self.fact_id = fact_id


class DuplicateActiveExtractionRunError(ExtractionDomainError):
    """Raised instead of silently returning the existing run under a 200.

    The router translates this to HTTP 409 Conflict, carrying the
    existing run's id/status in the error body — mirroring
    `DuplicateActiveCrawlRunError`'s established 409 precedent.
    """

    def __init__(self, *, existing_extraction_run_id: str, status: str) -> None:
        super().__init__(
            f"an active extraction run {existing_extraction_run_id!r} (status={status!r}) "
            "already exists for this company/crawl-run/options combination"
        )
        self.existing_extraction_run_id = existing_extraction_run_id
        self.status = status


class ExtractorExecutionError(ExtractionDomainError):
    """Raised internally by a single extractor's execution wrapper.

    Never propagated raw out of the application service — caught per
    extractor, per page, and turned into a `failed` `ExtractorExecution`
    plus a structured `ExtractionWarning` (brief section 19's failure-
    isolation rule).
    """

    def __init__(self, extractor_id: str, *, page_id: str, reason: str) -> None:
        super().__init__(f"extractor {extractor_id!r} failed on page {page_id!r}: {reason}")
        self.extractor_id = extractor_id
        self.page_id = page_id
        self.reason = reason
