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
