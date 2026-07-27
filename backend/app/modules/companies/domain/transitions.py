"""Allowed state transitions for `ProcessingStatus` and `WorkflowStatus`.

Pure Python — no FastAPI or MongoDB imports. Kept separate from
`enums.py` since these are business rules about *when* a status may
change, not the status values themselves.
"""

from app.modules.companies.domain.enums import ProcessingStatus, WorkflowStatus
from app.modules.companies.domain.exceptions import InvalidStatusTransitionError

_RETRY_FROM_REST_STATE = {ProcessingStatus.DISCOVERING}

ALLOWED_PROCESSING_TRANSITIONS: dict[ProcessingStatus, set[ProcessingStatus]] = {
    ProcessingStatus.IMPORTED: {ProcessingStatus.DISCOVERING},
    ProcessingStatus.DISCOVERING: {ProcessingStatus.DISCOVERED, ProcessingStatus.FAILED},
    ProcessingStatus.DISCOVERED: {ProcessingStatus.CRAWLING, ProcessingStatus.FAILED},
    ProcessingStatus.CRAWLING: {ProcessingStatus.CRAWLED, ProcessingStatus.FAILED},
    ProcessingStatus.CRAWLED: {ProcessingStatus.EXTRACTING, ProcessingStatus.FAILED},
    ProcessingStatus.EXTRACTING: {ProcessingStatus.EXTRACTED, ProcessingStatus.FAILED},
    ProcessingStatus.EXTRACTED: {ProcessingStatus.ANALYSING, ProcessingStatus.FAILED},
    ProcessingStatus.ANALYSING: {ProcessingStatus.ANALYSED, ProcessingStatus.FAILED},
    ProcessingStatus.ANALYSED: {ProcessingStatus.SCORING, ProcessingStatus.FAILED},
    ProcessingStatus.SCORING: {
        ProcessingStatus.READY,
        ProcessingStatus.PARTIAL,
        ProcessingStatus.FAILED,
    },
    # Resting states: any of these may be retried from scratch, and a
    # successfully-scored company may separately be marked stale (e.g. by
    # a future freshness check) without going through the whole pipeline.
    ProcessingStatus.READY: _RETRY_FROM_REST_STATE | {ProcessingStatus.STALE},
    ProcessingStatus.PARTIAL: _RETRY_FROM_REST_STATE,
    ProcessingStatus.FAILED: _RETRY_FROM_REST_STATE,
    ProcessingStatus.STALE: _RETRY_FROM_REST_STATE,
}

ALLOWED_WORKFLOW_TRANSITIONS: dict[WorkflowStatus, set[WorkflowStatus]] = {
    WorkflowStatus.UNREVIEWED: {
        WorkflowStatus.REVIEWED,
        WorkflowStatus.SHORTLISTED,
        WorkflowStatus.NOT_SUITABLE,
        WorkflowStatus.ARCHIVED,
    },
    WorkflowStatus.REVIEWED: {
        WorkflowStatus.SHORTLISTED,
        WorkflowStatus.NOT_SUITABLE,
        WorkflowStatus.CONTACTED,
        WorkflowStatus.ARCHIVED,
    },
    WorkflowStatus.SHORTLISTED: {
        WorkflowStatus.CONTACTED,
        WorkflowStatus.NOT_SUITABLE,
        WorkflowStatus.ARCHIVED,
    },
    WorkflowStatus.NOT_SUITABLE: {WorkflowStatus.ARCHIVED, WorkflowStatus.UNREVIEWED},
    WorkflowStatus.CONTACTED: {
        WorkflowStatus.CUSTOMER,
        WorkflowStatus.NOT_SUITABLE,
        WorkflowStatus.ARCHIVED,
    },
    WorkflowStatus.CUSTOMER: {WorkflowStatus.ARCHIVED},
    WorkflowStatus.ARCHIVED: {WorkflowStatus.UNREVIEWED},
}


def validate_processing_transition(
    current: ProcessingStatus, attempted: ProcessingStatus
) -> None:
    """Raise `InvalidStatusTransitionError` unless `attempted` is reachable from `current`.

    A no-op transition (`attempted == current`) is always allowed.
    """
    if attempted == current:
        return
    if attempted not in ALLOWED_PROCESSING_TRANSITIONS.get(current, set()):
        raise InvalidStatusTransitionError(
            field="processing_status", current=current.value, attempted=attempted.value
        )


def validate_workflow_transition(current: WorkflowStatus, attempted: WorkflowStatus) -> None:
    """Raise `InvalidStatusTransitionError` unless `attempted` is reachable from `current`.

    A no-op transition (`attempted == current`) is always allowed.
    """
    if attempted == current:
        return
    if attempted not in ALLOWED_WORKFLOW_TRANSITIONS.get(current, set()):
        raise InvalidStatusTransitionError(
            field="workflow_status", current=current.value, attempted=attempted.value
        )
