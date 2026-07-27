"""Repository tests against a real (test) MongoDB instance."""

from datetime import UTC, date, datetime

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.domains.companies.models import Company, CompanySource
from app.domains.companies.repository import CompanyRepository


def make_company(domain: str, source: CompanySource = "paste_domain_list") -> Company:
    return Company(
        domain=domain,
        source=source,
        url=None,
        estimated_sales_yearly_usd=None,
        source_created_at=None,
        emails=[],
        phones=[],
        imported_at=datetime.now(UTC),
    )


async def test_ensure_indexes_creates_unique_index_on_domain(
    test_database: AsyncIOMotorDatabase,
) -> None:
    repository = CompanyRepository(test_database)

    await repository.ensure_indexes()

    index_info = await test_database["companies"].index_information()
    domain_indexes = [spec for spec in index_info.values() if spec["key"] == [("domain", 1)]]
    assert len(domain_indexes) == 1
    assert domain_indexes[0]["unique"] is True


async def test_get_existing_domains_returns_only_matching_domains(
    test_database: AsyncIOMotorDatabase,
) -> None:
    repository = CompanyRepository(test_database)
    await repository.insert_many([make_company("example.com"), make_company("other.com")])

    existing = await repository.get_existing_domains(
        ["example.com", "not-in-db.com", "other.com"]
    )

    assert existing == {"example.com", "other.com"}


async def test_get_existing_domains_empty_input_returns_empty_set(
    test_database: AsyncIOMotorDatabase,
) -> None:
    repository = CompanyRepository(test_database)

    assert await repository.get_existing_domains([]) == set()


async def test_insert_many_persists_documents(test_database: AsyncIOMotorDatabase) -> None:
    repository = CompanyRepository(test_database)
    company = Company(
        domain="example.com",
        source="paste_storeleads_html",
        url="https://example.com",
        estimated_sales_yearly_usd=1234.56,
        source_created_at=date(2020, 1, 1),
        emails=["a@example.com"],
        phones=["+1 555-0100"],
        imported_at=datetime.now(UTC),
    )

    inserted = await repository.insert_many([company])

    assert inserted == [company]
    stored = await test_database["companies"].find_one({"domain": "example.com"})
    assert stored is not None
    assert stored["url"] == "https://example.com"
    assert stored["estimated_sales_yearly_usd"] == 1234.56
    assert stored["emails"] == ["a@example.com"]


async def test_duplicate_key_race_handled(test_database: AsyncIOMotorDatabase) -> None:
    """AC-11: a duplicate-key conflict is caught, not raised as a 500."""
    repository = CompanyRepository(test_database)
    await repository.ensure_indexes()
    company = make_company("race.example.com")

    first_attempt = await repository.insert_many([company])
    second_attempt = await repository.insert_many([company])

    assert len(first_attempt) == 1
    assert second_attempt == []
    documents = await test_database["companies"].find({"domain": "race.example.com"}).to_list(
        length=None
    )
    assert len(documents) == 1
