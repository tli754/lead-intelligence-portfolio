"""Shared fixtures for the queue_stats router tests.

Locally-scoped `FastAPI()` app containing only `queue_stats_router` — no
real Redis, following Task 017's own `FakeQueue`/`modules/imports`'s
locally-scoped-app precedent (`backend/tests/integration/imports/conftest.py`),
not the shared `app.main.app`.

`monkeypatch.setattr` targets the five registry classes and `Worker` as
imported into `app.domains.queue_stats.router` specifically (not the
`rq` package globally) — matching that module's own
`from rq.registry import ...` / `from rq.worker import Worker` imports.
"""

from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import app.domains.queue_stats.router as router_module
from app.domains.queue_stats.router import get_queue_by_name, router


class FakeQueue:
    """Placeholder standing in for `rq.Queue` — records nothing itself
    beyond the `count` a test configures."""

    def __init__(self, count: int = 0) -> None:
        self.count = count


def make_fake_registry_class(count: int = 0, job_ids: list[str] | None = None) -> type:
    """Returns a fresh class standing in for one RQ registry
    (StartedJobRegistry/FinishedJobRegistry/FailedJobRegistry/
    DeferredJobRegistry/ScheduledJobRegistry). The router constructs
    each as `SomeRegistry(queue=rq_queue)` and reads `.count`;
    `FailedJobRegistry` additionally calls `.get_job_ids(start, end)`.

    `calls` (a class attribute on the returned class) records every
    `get_job_ids` call's `(start, end)` args, so AC-07 can assert the
    router itself bounds the Redis read, not just `build_queue_stats`
    after the fact.
    """
    resolved_job_ids = job_ids if job_ids is not None else []

    class _FakeRegistry:
        calls: list[tuple[int, int]] = []

        def __init__(self, *, queue: object = None) -> None:
            self.queue = queue

        @property
        def count(self) -> int:
            return count

        def get_job_ids(self, start: int = 0, end: int = -1) -> list[str]:
            self.calls.append((start, end))
            return resolved_job_ids

    return _FakeRegistry


def make_fake_worker_class(states: list[str]) -> type:
    """Stand-in for `rq.worker.Worker` — only `Worker.all(queue=...)` is
    used by the router, returning fake worker objects exposing only
    `.get_state()`."""

    class _FakeWorkerInstance:
        def __init__(self, state: str) -> None:
            self._state = state

        def get_state(self) -> str:
            return self._state

    class _FakeWorker:
        @staticmethod
        def all(queue: object = None) -> list[_FakeWorkerInstance]:
            return [_FakeWorkerInstance(state) for state in states]

    return _FakeWorker


@dataclass
class RouterFakes:
    queue: FakeQueue
    failed_registry: type


@pytest.fixture
def configure_fakes(monkeypatch: pytest.MonkeyPatch) -> Callable[..., RouterFakes]:
    """Returns a function each test calls to wire up the five registry
    fakes, the `Worker` fake, and a `FakeQueue`, all scoped to that one
    test via `monkeypatch`."""

    def _configure(
        *,
        queued: int = 0,
        started: int = 0,
        finished: int = 0,
        failed: int = 0,
        deferred: int = 0,
        scheduled: int = 0,
        failed_job_ids: list[str] | None = None,
        worker_states: list[str] | None = None,
    ) -> RouterFakes:
        queue = FakeQueue(count=queued)
        failed_registry = make_fake_registry_class(failed, job_ids=failed_job_ids)

        monkeypatch.setattr(
            router_module, "StartedJobRegistry", make_fake_registry_class(started)
        )
        monkeypatch.setattr(
            router_module, "FinishedJobRegistry", make_fake_registry_class(finished)
        )
        monkeypatch.setattr(router_module, "FailedJobRegistry", failed_registry)
        monkeypatch.setattr(
            router_module, "DeferredJobRegistry", make_fake_registry_class(deferred)
        )
        monkeypatch.setattr(
            router_module, "ScheduledJobRegistry", make_fake_registry_class(scheduled)
        )
        monkeypatch.setattr(router_module, "Worker", make_fake_worker_class(worker_states or []))

        return RouterFakes(queue=queue, failed_registry=failed_registry)

    return _configure


ClientFactory = Callable[[FakeQueue], AbstractAsyncContextManager[AsyncClient]]


@pytest.fixture
def client_factory() -> ClientFactory:
    @asynccontextmanager
    async def _factory(queue: FakeQueue) -> AsyncGenerator[AsyncClient, None]:
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_queue_by_name] = lambda: queue
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
            yield test_client

    return _factory
