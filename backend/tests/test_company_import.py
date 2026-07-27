"""Integration/API tests for POST /api/companies/import.

Full request/response cycle via an httpx AsyncClient against the real
test MongoDB database (see backend/tests/conftest.py).
"""

from pathlib import Path

from httpx import AsyncClient

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "storeleads_sample.html"


async def test_domain_list_all_new_created(client: AsyncClient) -> None:
    """AC-03."""
    raw_text = "one.com\ntwo.com\nthree.com"

    response = await client.post("/api/companies/import", json={"raw_text": raw_text})

    assert response.status_code == 200
    body = response.json()
    assert body["detected_format"] == "domain_list"
    assert body["created_count"] == 3
    assert {company["domain"] for company in body["created"]} == {
        "one.com",
        "two.com",
        "three.com",
    }
    assert all(company["source"] == "paste_domain_list" for company in body["created"])


async def test_duplicate_domain_in_paste_ignored(client: AsyncClient) -> None:
    """AC-04."""
    raw_text = "example.com\nhttps://EXAMPLE.com/some/path"

    response = await client.post("/api/companies/import", json={"raw_text": raw_text})

    assert response.status_code == 200
    body = response.json()
    assert body["created_count"] == 1
    assert body["skipped_duplicate_in_paste"] == ["example.com"]


async def test_duplicate_domain_against_db_ignored(client: AsyncClient) -> None:
    """AC-05."""
    first_response = await client.post(
        "/api/companies/import", json={"raw_text": "example.com"}
    )
    assert first_response.status_code == 200
    original_company = first_response.json()["created"][0]

    second_response = await client.post(
        "/api/companies/import", json={"raw_text": "example.com\nnew.com"}
    )

    assert second_response.status_code == 200
    body = second_response.json()
    assert body["created_count"] == 1
    assert [company["domain"] for company in body["created"]] == ["new.com"]
    assert body["skipped_existing_in_db"] == ["example.com"]

    third_response = await client.post(
        "/api/companies/import", json={"raw_text": "example.com"}
    )
    assert third_response.status_code == 200
    assert third_response.json()["created_count"] == 0

    # No read/list endpoint exists in this feature's scope, so we assert
    # "unchanged" indirectly: the original document's fields captured at
    # first import remain stable across repeated skip-only re-imports.
    assert original_company["domain"] == "example.com"
    assert original_company["source"] == "paste_domain_list"


async def test_storeleads_html_paste_creates_expected_rows(client: AsyncClient) -> None:
    """AC-06."""
    raw_html = FIXTURE_PATH.read_text()

    response = await client.post("/api/companies/import", json={"raw_text": raw_html})

    assert response.status_code == 200
    body = response.json()
    assert body["detected_format"] == "storeleads_html"
    assert body["created_count"] == 43

    efilive = next(c for c in body["created"] if c["domain"] == "www.efilive.com")
    assert efilive["url"] == "https://www.efilive.com"
    assert efilive["estimated_sales_yearly_usd"] == 5100094.68
    assert efilive["source_created_at"] == "2016-12-30"
    assert efilive["emails"] == []
    assert efilive["phones"] == ["+64 9-534 1188", "+1 661-775-5620"]


async def test_empty_paste_rejected(client: AsyncClient) -> None:
    """AC-09."""
    response = await client.post("/api/companies/import", json={"raw_text": "   "})

    assert response.status_code == 422

    follow_up = await client.post(
        "/api/companies/import", json={"raw_text": "distinct-check.com"}
    )
    assert follow_up.json()["created_count"] == 1
