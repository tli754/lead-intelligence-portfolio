"""Queue statistics router.

`GET /api/queue-stats` — a small, flat, non-hexagonal-module router for
a cross-cutting, infrastructure-level concern (RQ/Redis queue state),
following `backend/app/domains/health/router.py`'s precedent. See the
feature contract's Decision 1 for why this is not bolted onto
`modules/crawling/api/router.py`.

Depends only on `app.queue.get_queue` (already cross-cutting,
non-module-owned) — reads Redis/RQ state directly via RQ's own `Queue`/
registry/`Worker` classes, nothing from `modules/crawling/**`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from rq import Queue
from rq.registry import (
    DeferredJobRegistry,
    FailedJobRegistry,
    FinishedJobRegistry,
    ScheduledJobRegistry,
    StartedJobRegistry,
)
from rq.worker import Worker

from app.domains.queue_stats.schemas import QueueCounts, QueueStatsResponse
from app.domains.queue_stats.service import FAILED_JOB_ID_LIMIT, build_queue_stats
from app.queue import get_queue

router = APIRouter(prefix="/api", tags=["queue-stats"])


def get_queue_by_name(queue: Annotated[str, Query()] = "crawling") -> Queue:
    """Resolve an RQ Queue by name from the `?queue=` query param, defaulting
    to "crawling" — the only queue this repository has adopted RQ for today
    (ADR 0004's module-by-module rollout). Generalizes to any future queue
    name (discovery, extraction, ...) with no change here."""
    return get_queue(queue)


@router.get("/queue-stats", response_model=QueueStatsResponse)
async def get_queue_stats(
    queue: Annotated[str, Query()] = "crawling",
    rq_queue: Queue = Depends(get_queue_by_name),
) -> QueueStatsResponse:
    counts = QueueCounts(
        queued=rq_queue.count,
        started=StartedJobRegistry(queue=rq_queue).count,
        finished=FinishedJobRegistry(queue=rq_queue).count,
        failed=FailedJobRegistry(queue=rq_queue).count,
        deferred=DeferredJobRegistry(queue=rq_queue).count,
        scheduled=ScheduledJobRegistry(queue=rq_queue).count,
    )
    failed_job_ids = FailedJobRegistry(queue=rq_queue).get_job_ids(0, FAILED_JOB_ID_LIMIT - 1)
    worker_states = [worker.get_state() for worker in Worker.all(queue=rq_queue)]
    return build_queue_stats(
        queue_name=queue,
        counts=counts,
        failed_job_ids=failed_job_ids,
        worker_states=worker_states,
    )
