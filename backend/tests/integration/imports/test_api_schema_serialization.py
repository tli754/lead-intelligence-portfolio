from pathlib import Path

from httpx import AsyncClient

FIXTURES_DIR = Path(__file__).resolve().parents[4] / "fixtures" / "storeleads"


def _load(name: str) -> str:
    return (FIXTURES_DIR / name).read_text()


class TestPreviewResponseIsCamelCase:
    async def test_preview_response_shape(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/imports/storeleads/preview", json={"html": _load("standard_table.html")}
        )

        assert response.status_code == 200
        body = response.json()
        assert set(body.keys()) == {"data"}
        assert set(body["data"].keys()) == {"summary", "rows"}
        assert set(body["data"]["summary"].keys()) == {
            "rowsFound",
            "validRows",
            "invalidRows",
            "existingCompanies",
            "duplicateRowsInFile",
            "importableRows",
        }
        row = body["data"]["rows"][0]
        assert set(row.keys()) == {
            "rowNumber",
            "website",
            "normalizedDomain",
            "platform",
            "country",
            "city",
            "validationStatus",
            "errors",
            "duplicateStatus",
            "outcome",
        }
        assert row["outcome"] is None  # nothing has been imported yet

    async def test_rejects_empty_html_body(self, client: AsyncClient) -> None:
        response = await client.post("/api/imports/storeleads/preview", json={"html": ""})
        assert response.status_code == 422

    async def test_vaadin_grid_sourced_preview_response_matches_the_same_shape(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/api/imports/storeleads/preview", json={"html": _load("vaadin_grid_standard.html")}
        )

        assert response.status_code == 200
        body = response.json()
        assert set(body.keys()) == {"data"}
        assert set(body["data"].keys()) == {"summary", "rows"}
        assert set(body["data"]["summary"].keys()) == {
            "rowsFound",
            "validRows",
            "invalidRows",
            "existingCompanies",
            "duplicateRowsInFile",
            "importableRows",
        }
        row = body["data"]["rows"][0]
        assert set(row.keys()) == {
            "rowNumber",
            "website",
            "normalizedDomain",
            "platform",
            "country",
            "city",
            "validationStatus",
            "errors",
            "duplicateStatus",
            "outcome",
        }
        assert row["outcome"] is None
        # No "source" field leaks onto the wire — internal provenance only.
        assert "source" not in body["data"]


class TestImportResponseIsCamelCase:
    async def test_import_response_shape(self, client: AsyncClient) -> None:
        response = await client.post(
            "/api/imports/storeleads", json={"html": _load("standard_table.html")}
        )

        assert response.status_code == 200
        body = response.json()
        assert set(body.keys()) == {"data"}
        assert set(body["data"].keys()) == {
            "created",
            "skippedExisting",
            "skippedInvalid",
            "failed",
            "rows",
        }
        assert body["data"]["rows"][0]["outcome"] in {
            "created",
            "skipped_existing",
            "skipped_invalid",
            "failed",
        }
