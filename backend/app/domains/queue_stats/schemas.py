"""Response models for `GET /api/queue-stats`.

Flat-convention snake_case field names — matching
`backend/app/domains/companies/models.py`'s existing precedent, not the
hexagonal modules' camelCase-DTO convention, since this is a flat
domain (see the feature contract's Decision 2).
"""

from pydantic import BaseModel, Field


class QueueCounts(BaseModel):
    """Current job counts for one RQ queue, one field per RQ registry
    (plus the queue's own pending-job count). All non-negative; all zero
    is a normal, expected state (e.g. before any job has ever run), not
    an error.
    """

    queued: int = Field(ge=0)  # Queue.count — jobs waiting, not yet dequeued by a worker
    started: int = Field(ge=0)  # StartedJobRegistry(queue=...).count
    finished: int = Field(ge=0)  # FinishedJobRegistry(queue=...).count
    failed: int = Field(ge=0)  # FailedJobRegistry(queue=...).count
    deferred: int = Field(ge=0)  # DeferredJobRegistry(queue=...).count
    scheduled: int = Field(ge=0)  # ScheduledJobRegistry(queue=...).count


class QueueStatsResponse(BaseModel):
    """Response body for `GET /api/queue-stats`. A point-in-time snapshot
    only — no history, no time series (out of scope, see the task brief)."""

    queue: str
    counts: QueueCounts
    failed_job_ids: list[str]
    workers_alive: int = Field(ge=0)
