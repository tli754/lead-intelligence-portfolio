import pytest

from app.modules.companies.domain.enums import ProcessingStatus, WorkflowStatus
from app.modules.companies.domain.exceptions import InvalidStatusTransitionError
from app.modules.companies.domain.transitions import (
    validate_processing_transition,
    validate_workflow_transition,
)


class TestProcessingTransitions:
    @pytest.mark.parametrize(
        ("current", "attempted"),
        [
            (ProcessingStatus.IMPORTED, ProcessingStatus.DISCOVERING),
            (ProcessingStatus.DISCOVERING, ProcessingStatus.DISCOVERED),
            (ProcessingStatus.DISCOVERING, ProcessingStatus.FAILED),
            (ProcessingStatus.SCORING, ProcessingStatus.READY),
            (ProcessingStatus.SCORING, ProcessingStatus.PARTIAL),
            (ProcessingStatus.READY, ProcessingStatus.STALE),
            (ProcessingStatus.READY, ProcessingStatus.DISCOVERING),
            (ProcessingStatus.FAILED, ProcessingStatus.DISCOVERING),
            (ProcessingStatus.STALE, ProcessingStatus.DISCOVERING),
        ],
    )
    def test_allows_valid_transition(
        self, current: ProcessingStatus, attempted: ProcessingStatus
    ) -> None:
        validate_processing_transition(current, attempted)  # must not raise

    def test_allows_no_op_transition(self) -> None:
        validate_processing_transition(ProcessingStatus.CRAWLING, ProcessingStatus.CRAWLING)

    @pytest.mark.parametrize(
        ("current", "attempted"),
        [
            (ProcessingStatus.IMPORTED, ProcessingStatus.READY),
            (ProcessingStatus.DISCOVERING, ProcessingStatus.CRAWLING),
            (ProcessingStatus.CRAWLING, ProcessingStatus.SCORING),
            (ProcessingStatus.READY, ProcessingStatus.PARTIAL),
            (ProcessingStatus.FAILED, ProcessingStatus.READY),
        ],
    )
    def test_rejects_invalid_transition(
        self, current: ProcessingStatus, attempted: ProcessingStatus
    ) -> None:
        with pytest.raises(InvalidStatusTransitionError) as excinfo:
            validate_processing_transition(current, attempted)
        assert excinfo.value.field == "processing_status"
        assert excinfo.value.current == current.value
        assert excinfo.value.attempted == attempted.value


class TestWorkflowTransitions:
    @pytest.mark.parametrize(
        ("current", "attempted"),
        [
            (WorkflowStatus.UNREVIEWED, WorkflowStatus.SHORTLISTED),
            (WorkflowStatus.UNREVIEWED, WorkflowStatus.NOT_SUITABLE),
            (WorkflowStatus.SHORTLISTED, WorkflowStatus.CONTACTED),
            (WorkflowStatus.CONTACTED, WorkflowStatus.CUSTOMER),
            (WorkflowStatus.CUSTOMER, WorkflowStatus.ARCHIVED),
            (WorkflowStatus.NOT_SUITABLE, WorkflowStatus.UNREVIEWED),
            (WorkflowStatus.ARCHIVED, WorkflowStatus.UNREVIEWED),
        ],
    )
    def test_allows_valid_transition(
        self, current: WorkflowStatus, attempted: WorkflowStatus
    ) -> None:
        validate_workflow_transition(current, attempted)  # must not raise

    def test_allows_no_op_transition(self) -> None:
        validate_workflow_transition(WorkflowStatus.REVIEWED, WorkflowStatus.REVIEWED)

    @pytest.mark.parametrize(
        ("current", "attempted"),
        [
            (WorkflowStatus.UNREVIEWED, WorkflowStatus.CUSTOMER),
            (WorkflowStatus.CUSTOMER, WorkflowStatus.SHORTLISTED),
            (WorkflowStatus.ARCHIVED, WorkflowStatus.CUSTOMER),
        ],
    )
    def test_rejects_invalid_transition(
        self, current: WorkflowStatus, attempted: WorkflowStatus
    ) -> None:
        with pytest.raises(InvalidStatusTransitionError) as excinfo:
            validate_workflow_transition(current, attempted)
        assert excinfo.value.field == "workflow_status"
