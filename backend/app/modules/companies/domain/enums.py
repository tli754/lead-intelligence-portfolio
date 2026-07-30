"""Enumerations for the companies module's pipeline and workflow state.

Pure Python — no FastAPI or MongoDB imports.
"""

from enum import StrEnum


class ProcessingStatus(StrEnum):
    """Where a company sits in the discovery -> scoring pipeline.

    Each `-ing` stage has its own `-ed` completion state (e.g. `crawling`
    -> `crawled`) before the next stage begins — see `transitions.py` for
    the allowed edges between these.
    """

    IMPORTED = "imported"
    DISCOVERING = "discovering"
    DISCOVERED = "discovered"
    CRAWLING = "crawling"
    CRAWLED = "crawled"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    ANALYSING = "analysing"
    ANALYSED = "analysed"
    SCORING = "scoring"
    READY = "ready"
    PARTIAL = "partial"
    FAILED = "failed"
    STALE = "stale"


class WorkflowStatus(StrEnum):
    """A human reviewer's manual disposition of a company."""

    UNREVIEWED = "unreviewed"
    REVIEWED = "reviewed"
    SHORTLISTED = "shortlisted"
    NOT_SUITABLE = "not_suitable"
    CONTACTED = "contacted"
    CUSTOMER = "customer"
    ARCHIVED = "archived"
