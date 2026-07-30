from pathlib import Path
from typing import Any

from httpx import AsyncClient

FIXTURES_DIR = Path(__file__).resolve().parents[4] / "fixtures" / "storeleads"


def _load(name: str) -> str:
    return (FIXTURES_DIR / name).read_text()


async def _preview(client: AsyncClient, html: str) -> dict[str, Any]:
    response = await client.post("/api/imports/storeleads/preview", json={"html": html})
    assert response.status_code == 200, response.text
    return response.json()


class TestPreviewPerformsNoWrites:
    async def test_preview_never_creates_a_company(self, client: AsyncClient, gateway) -> None:
        await _preview(client, _load("standard_table.html"))

        assert gateway.created == []


class TestPreviewSummaryCounts:
    async def test_standard_table_counts(self, client: AsyncClient) -> None:
        body = await _preview(client, _load("standard_table.html"))

        summary = body["data"]["summary"]
        assert summary == {
            "rowsFound": 3,
            "validRows": 3,
            "invalidRows": 0,
            "existingCompanies": 0,
            "duplicateRowsInFile": 0,
            "importableRows": 3,
        }
        assert len(body["data"]["rows"]) == 3

    async def test_invalid_rows_are_counted_and_carry_errors(self, client: AsyncClient) -> None:
        body = await _preview(client, _load("invalid_websites.html"))

        summary = body["data"]["summary"]
        assert summary["rowsFound"] == 5
        assert summary["invalidRows"] == 4  # missing, localhost, IP, malformed
        assert summary["validRows"] == 1

        invalid_rows = [row for row in body["data"]["rows"] if row["validationStatus"] == "invalid"]
        assert len(invalid_rows) == 4
        assert all(row["errors"] for row in invalid_rows)

    async def test_duplicate_rows_in_file_are_detected(self, client: AsyncClient) -> None:
        body = await _preview(client, _load("duplicate_websites.html"))

        summary = body["data"]["summary"]
        assert summary["rowsFound"] == 4
        assert summary["duplicateRowsInFile"] == 2  # rows 2 and 3 both normalize to row 1's domain
        assert summary["importableRows"] == 2  # 4 valid rows, minus the 2 duplicates

        statuses = [row["duplicateStatus"] for row in body["data"]["rows"]]
        assert statuses == ["new", "duplicate_in_file", "duplicate_in_file", "new"]

    async def test_existing_companies_are_detected_via_the_gateway(
        self, client_factory, make_gateway
    ) -> None:
        gateway = make_gateway(existing_domains={"summitoutfitters.com"})
        async with client_factory(gateway) as client:
            body = await _preview(client, _load("duplicate_websites.html"))

        summary = body["data"]["summary"]
        assert summary["existingCompanies"] == 1
        assert summary["importableRows"] == 1  # only lumenhomegoods.com is new

    async def test_empty_table_produces_zero_counts(self, client: AsyncClient) -> None:
        body = await _preview(client, _load("empty_table.html"))

        assert body["data"]["summary"] == {
            "rowsFound": 0,
            "validRows": 0,
            "invalidRows": 0,
            "existingCompanies": 0,
            "duplicateRowsInFile": 0,
            "importableRows": 0,
        }
        assert body["data"]["rows"] == []


class TestVaadinGridSummaryCounts:
    """Parallels TestPreviewSummaryCounts, using Vaadin-grid fixtures instead
    of `<table>` fixtures — same endpoint, auto-detected input format."""

    async def test_standard_vaadin_grid_counts(self, client: AsyncClient) -> None:
        body = await _preview(client, _load("vaadin_grid_standard.html"))

        summary = body["data"]["summary"]
        assert summary == {
            "rowsFound": 4,
            "validRows": 4,
            "invalidRows": 0,
            "existingCompanies": 0,
            "duplicateRowsInFile": 0,
            "importableRows": 4,
        }
        rows = body["data"]["rows"]
        assert len(rows) == 4
        first = rows[0]
        assert first["website"] == "www.northfieldsupply.com"
        assert first["normalizedDomain"] == "northfieldsupply.com"
        assert first["platform"] == "shopify"
        assert first["country"] == "US"
        assert first["city"] == "Austin"

    async def test_vaadin_invalid_domain_cell_produces_an_invalid_row(
        self, client: AsyncClient
    ) -> None:
        body = await _preview(client, _load("vaadin_grid_invalid_and_duplicate_domains.html"))

        summary = body["data"]["summary"]
        assert summary["rowsFound"] == 3
        assert summary["invalidRows"] == 1

        invalid_rows = [
            row for row in body["data"]["rows"] if row["validationStatus"] == "invalid"
        ]
        assert len(invalid_rows) == 1
        assert invalid_rows[0]["errors"][0]["field"] == "website"

    async def test_vaadin_duplicate_domains_in_file_are_detected(
        self, client: AsyncClient
    ) -> None:
        body = await _preview(client, _load("vaadin_grid_invalid_and_duplicate_domains.html"))

        summary = body["data"]["summary"]
        assert summary["duplicateRowsInFile"] == 1
        assert summary["importableRows"] == 1  # 2 valid rows minus 1 in-file duplicate

        duplicate_rows = [
            row for row in body["data"]["rows"] if row["duplicateStatus"] == "duplicate_in_file"
        ]
        assert len(duplicate_rows) == 1
        assert duplicate_rows[0]["normalizedDomain"] == "dupemarket.com"

    async def test_vaadin_grid_existing_companies_are_detected_via_the_gateway(
        self, client_factory, make_gateway
    ) -> None:
        gateway = make_gateway(existing_domains={"northfieldsupply.com"})
        async with client_factory(gateway) as client:
            body = await _preview(client, _load("vaadin_grid_standard.html"))

        summary = body["data"]["summary"]
        assert summary["existingCompanies"] == 1
        assert summary["importableRows"] == 3

    async def test_vaadin_grid_reordered_columns_extract_the_same_data(
        self, client: AsyncClient
    ) -> None:
        body = await _preview(client, _load("vaadin_grid_reordered_columns.html"))

        summary = body["data"]["summary"]
        assert summary["rowsFound"] == 2
        assert summary["validRows"] == 2
        assert body["data"]["rows"][0]["normalizedDomain"] == "northfieldsupply.com"

    async def test_vaadin_grid_malformed_and_empty_inputs_produce_zero_rows(
        self, client: AsyncClient
    ) -> None:
        for fixture in ("vaadin_grid_malformed.html", "vaadin_grid_empty.html"):
            body = await _preview(client, _load(fixture))
            assert body["data"]["summary"]["rowsFound"] == 0
            assert body["data"]["rows"] == []
