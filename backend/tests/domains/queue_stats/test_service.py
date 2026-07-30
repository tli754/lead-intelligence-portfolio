"""Pure unit tests for `app.domains.queue_stats.service` — no Redis, no
RQ object of any kind, plain `int`/`str`/`list[str]` arguments only.
"""

from app.domains.queue_stats.schemas import QueueCounts
from app.domains.queue_stats.service import (
    FAILED_JOB_ID_LIMIT,
    build_queue_stats,
    summarize_worker_liveness,
)


def test_build_queue_stats_maps_counts_without_swapping_fields():
    """AC-03: each `QueueCounts` field must map 1:1 onto its distinct
    input value — proving no field is accidentally swapped or duplicated."""
    counts = QueueCounts(
        queued=1,
        started=2,
        finished=3,
        failed=4,
        deferred=5,
        scheduled=6,
    )

    result = build_queue_stats(
        queue_name="crawling",
        counts=counts,
        failed_job_ids=[],
        worker_states=[],
    )

    assert result.counts.queued == 1
    assert result.counts.started == 2
    assert result.counts.finished == 3
    assert result.counts.failed == 4
    assert result.counts.deferred == 5
    assert result.counts.scheduled == 6
    assert result.queue == "crawling"


def test_failed_job_ids_never_exceeds_limit():
    """AC-04: `build_queue_stats` re-slices to the cap itself, even if
    handed a longer list than the router should ever pass in."""
    oversized_ids = [f"job-{i}" for i in range(FAILED_JOB_ID_LIMIT + 10)]

    result = build_queue_stats(
        queue_name="crawling",
        counts=QueueCounts(queued=0, started=0, finished=0, failed=0, deferred=0, scheduled=0),
        failed_job_ids=oversized_ids,
        worker_states=[],
    )

    assert len(result.failed_job_ids) == FAILED_JOB_ID_LIMIT
    assert result.failed_job_ids == oversized_ids[:FAILED_JOB_ID_LIMIT]


def test_summarize_worker_liveness_excludes_suspended():
    """AC-05: suspended workers don't count as alive."""
    assert summarize_worker_liveness(["idle", "busy", "suspended"]) == 2


def test_summarize_worker_liveness_empty():
    """AC-06: zero workers returns zero, not an error."""
    assert summarize_worker_liveness([]) == 0
