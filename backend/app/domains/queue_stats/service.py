"""Pure, Redis-free computation for queue statistics.

Everything here takes plain `int`/`str`/`list[str]` arguments — no RQ
object is constructed and no Redis connection exists anywhere in this
file. `router.py` is the only place that talks to Redis/RQ; it passes
already-fetched values in here to be assembled into the response model.
"""

from app.domains.queue_stats.schemas import QueueCounts, QueueStatsResponse

FAILED_JOB_ID_LIMIT = 50


def summarize_worker_liveness(worker_states: list[str]) -> int:
    """Count workers whose RQ state is not 'suspended' — see the feature
    contract's Decision 2 for why suspended workers don't count as alive."""
    return sum(1 for state in worker_states if state != "suspended")


def build_queue_stats(
    *,
    queue_name: str,
    counts: QueueCounts,
    failed_job_ids: list[str],
    worker_states: list[str],
) -> QueueStatsResponse:
    return QueueStatsResponse(
        queue=queue_name,
        counts=counts,
        failed_job_ids=failed_job_ids[:FAILED_JOB_ID_LIMIT],
        workers_alive=summarize_worker_liveness(worker_states),
    )
