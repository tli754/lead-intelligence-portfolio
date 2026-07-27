from pathlib import Path
from typing import Any

from httpx import AsyncClient

FIXTURES_DIR = Path(__file__).resolve().parents[4] / "fixtures" / "storeleads"


def _load(name: str) -> str:
    return (FIXTURES_DIR / name).read_text()


async def _run_import(client: AsyncClient, html: str) -> dict[str, Any]:
    response = await client.post("/api/imports/storeleads", json={"html": html})
    assert response.status_code == 200, response.text
    return response.json()


class TestImportCreatesValidNewCompanies:
    async def test_creates_every_valid_new_row(self, client: AsyncClient, gateway) -> None:
        body = await _run_import(client, _load("standard_table.html"))

        assert body["data"]["created"] == 3
        assert body["data"]["skippedExisting"] == 0
        assert body["data"]["skippedInvalid"] == 0
        assert body["data"]["failed"] == 0
        assert {row["normalized_domain"] for row in gateway.created} == {
            "summitoutfitters.com",
            "quickcartbargains.com",
            "lumenhomegoods.com",
        }
        assert all(row["outcome"] == "created" for row in body["data"]["rows"])

    async def test_maps_fields_onto_the_company_gateway_call(
        self, client: AsyncClient, gateway
    ) -> None:
        await _run_import(client, _load("standard_table.html"))

        summit = next(
            c for c in gateway.created if c["normalized_domain"] == "summitoutfitters.com"
        )
        assert summit["platform"] == "shopify"
        assert summit["country"] == "United States"
        assert summit["city"] == "Denver"


class TestImportSkipsExisting:
    async def test_skips_a_domain_that_already_exists(self, client_factory, make_gateway) -> None:
        gateway = make_gateway(existing_domains={"summitoutfitters.com"})
        async with client_factory(gateway) as client:
            body = await _run_import(client, _load("standard_table.html"))

        assert body["data"]["created"] == 2
        assert body["data"]["skippedExisting"] == 1
        summit_row = next(
            row for row in body["data"]["rows"] if row["normalizedDomain"] == "summitoutfitters.com"
        )
        assert summit_row["outcome"] == "skipped_existing"

    async def test_within_file_duplicates_are_skipped_without_a_second_create_call(
        self, client_factory, make_gateway
    ) -> None:
        gateway = make_gateway()
        async with client_factory(gateway) as client:
            body = await _run_import(client, _load("duplicate_websites.html"))

        # 2 unique domains created (summitoutfitters.com, lumenhomegoods.com);
        # the other 2 rows are the same domain repeated in-file.
        assert body["data"]["created"] == 2
        assert body["data"]["skippedExisting"] == 2
        assert len(gateway.created) == 2


class TestImportSkipsInvalid:
    async def test_skips_invalid_rows_without_calling_the_gateway(
        self, client_factory, make_gateway
    ) -> None:
        gateway = make_gateway()
        async with client_factory(gateway) as client:
            body = await _run_import(client, _load("invalid_websites.html"))

        assert body["data"]["skippedInvalid"] == 4
        assert body["data"]["created"] == 1  # ashgrovetextiles.com is the only valid row
        assert len(gateway.created) == 1


class TestImportIsSafeToRetry:
    async def test_running_the_same_file_twice_creates_nothing_the_second_time(
        self, client_factory, make_gateway
    ) -> None:
        gateway = make_gateway()
        html = _load("standard_table.html")
        async with client_factory(gateway) as client:
            first = await _run_import(client, html)
            second = await _run_import(client, html)

        assert first["data"]["created"] == 3
        assert second["data"]["created"] == 0
        assert second["data"]["skippedExisting"] == 3
        assert len(gateway.created) == 3


class TestOneFailedRowDoesNotFailTheBatch:
    async def test_a_single_gateway_failure_is_isolated_to_its_row(
        self, client_factory, make_gateway
    ) -> None:
        gateway = make_gateway(fail_domains={"quickcartbargains.com"})
        async with client_factory(gateway) as client:
            body = await _run_import(client, _load("standard_table.html"))

        assert body["data"]["created"] == 2
        assert body["data"]["failed"] == 1
        failed_row = next(
            row
            for row in body["data"]["rows"]
            if row["normalizedDomain"] == "quickcartbargains.com"
        )
        assert failed_row["outcome"] == "failed"
        # The other two rows still succeeded.
        assert {c["normalized_domain"] for c in gateway.created} == {
            "summitoutfitters.com",
            "lumenhomegoods.com",
        }
