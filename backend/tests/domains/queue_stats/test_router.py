"""Router tests against a locally-scoped `FastAPI()` app containing only
`queue_stats_router` — no real Redis. See `conftest.py` for the fakes.
"""

from app.domains.queue_stats.service import FAILED_JOB_ID_LIMIT


async def test_queue_stats_defaults_to_crawling_and_handles_empty_state(
    configure_fakes,
    client_factory,
):
    """AC-01: with all-zero/empty fakes and no `?queue=` param, the
    response is a normal 200, not an error, defaulting to `"crawling"`."""
    fakes = configure_fakes()

    async with client_factory(fakes.queue) as client:
        response = await client.get("/api/queue-stats")

    assert response.status_code == 200
    body = response.json()
    assert body["queue"] == "crawling"
    assert body["counts"] == {
        "queued": 0,
        "started": 0,
        "finished": 0,
        "failed": 0,
        "deferred": 0,
        "scheduled": 0,
    }
    assert body["failed_job_ids"] == []
    assert body["workers_alive"] == 0


async def test_queue_stats_accepts_arbitrary_queue_name(
    configure_fakes,
    client_factory,
):
    """AC-02: a never-adopted queue name is accepted without error — no
    404, no validation error, same all-zero-shaped response."""
    fakes = configure_fakes()

    async with client_factory(fakes.queue) as client:
        response = await client.get("/api/queue-stats", params={"queue": "discovery"})

    assert response.status_code == 200
    body = response.json()
    assert body["queue"] == "discovery"
    assert body["counts"] == {
        "queued": 0,
        "started": 0,
        "finished": 0,
        "failed": 0,
        "deferred": 0,
        "scheduled": 0,
    }
    assert body["failed_job_ids"] == []
    assert body["workers_alive"] == 0


async def test_router_requests_bounded_failed_job_id_range(
    configure_fakes,
    client_factory,
):
    """AC-07: the router requests at most `FAILED_JOB_ID_LIMIT` failed
    ids from RQ — proven by inspecting the fake `FailedJobRegistry`'s
    recorded `get_job_ids` call args."""
    fakes = configure_fakes(failed=5, failed_job_ids=["job-1", "job-2"])

    async with client_factory(fakes.queue) as client:
        response = await client.get("/api/queue-stats")

    assert response.status_code == 200
    assert fakes.failed_registry.calls == [(0, FAILED_JOB_ID_LIMIT - 1)]
