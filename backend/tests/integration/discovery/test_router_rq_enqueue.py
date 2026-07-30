"""Router-level tests for Task 020's RQ-enqueue behavior
(`docs/contracts/active/020-rq-discovery-vertical-slice.md`) — AC-01,
AC-02. No real MongoDB, no real network, and no real Redis — a
locally-defined `FakeQueue` overrides `get_discovery_queue` via
`client_factory`'s `queue` keyword parameter, recording `enqueue_call`
invocations instead of talking to RQ.
"""

from app.modules.discovery.infrastructure.rq_jobs import (
    DISCOVERY_JOB_TIMEOUT,
    run_discovery_execution,
)

from .conftest import ClientFactory, FakeCompanyDiscoveryGateway, FakeDiscoveryRepository

# RQ's own default job timeout — the concrete regression guard for AC-02's
# "a timeout other than RQ's default" assertion.
RQ_DEFAULT_TIMEOUT = 180


class FakeQueue:
    """Records every `enqueue_call` invocation instead of talking to real
    Redis/RQ — proves the router enqueues work instead of executing it
    inline (AC-01, AC-02)."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def enqueue_call(self, **kwargs) -> None:
        self.calls.append(kwargs)


class RaisingHttpDiscoveryClient:
    """A `HttpDiscoveryClient` double whose every method raises — proves
    `execute_discovery_run` (and therefore any real discovery network I/O)
    was never invoked synchronously within the request."""

    async def resolve_homepage(self, candidates: list[str]):
        raise AssertionError("resolve_homepage must never be called synchronously by the router")

    async def fetch_html(self, url: str):
        raise AssertionError("fetch_html must never be called synchronously by the router")

    async def fetch_text(self, url: str):
        raise AssertionError("fetch_text must never be called synchronously by the router")

    async def fetch_binary(self, url: str):
        raise AssertionError("fetch_binary must never be called synchronously by the router")


class TestCreateDiscoveryRunEnqueues:
    async def test_create_discovery_run_returns_queued_without_executing(
        self,
        client_factory: ClientFactory,
        company_gateway: FakeCompanyDiscoveryGateway,
        discovery_repository: FakeDiscoveryRepository,
    ) -> None:
        http_client = RaisingHttpDiscoveryClient()

        async with client_factory(
            company_gateway,
            discovery_repository,
            http_client,
            queue=FakeQueue(),
        ) as client:
            response = await client.post("/api/companies/company-1/discovery-runs")

        assert response.status_code == 201
        assert response.json()["data"]["status"] == "queued"

    async def test_enqueue_call_arguments(
        self,
        client_factory: ClientFactory,
        company_gateway: FakeCompanyDiscoveryGateway,
        discovery_repository: FakeDiscoveryRepository,
    ) -> None:
        http_client = RaisingHttpDiscoveryClient()
        queue = FakeQueue()

        async with client_factory(
            company_gateway,
            discovery_repository,
            http_client,
            queue=queue,
        ) as client:
            response = await client.post("/api/companies/company-1/discovery-runs")

        run_id = response.json()["data"]["discoveryRunId"]
        assert len(queue.calls) == 1
        call = queue.calls[0]
        assert call["func"] is run_discovery_execution
        assert call["args"] == (run_id,)
        assert call["job_id"] == run_id
        assert call["timeout"] == DISCOVERY_JOB_TIMEOUT
        assert call["timeout"] != RQ_DEFAULT_TIMEOUT
