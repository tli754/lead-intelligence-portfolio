from app.modules.imports.domain.enums import DuplicateStatus, ValidationStatus
from app.modules.imports.domain.row_builder import build_import_row
from app.modules.imports.domain.storeleads_html_parser import RawStoreLeadsRow


class TestBuildImportRow:
    def test_valid_row(self) -> None:
        raw = RawStoreLeadsRow(
            row_number=1,
            website="https://www.example.com",
            platform="Shopify",
            country="United States",
            city="Denver",
        )

        row = build_import_row(1, raw)

        assert row.validation_status == ValidationStatus.VALID
        assert row.errors == []
        assert row.normalized_domain == "example.com"
        assert row.website == "https://www.example.com"  # original value preserved
        assert row.platform == "shopify"
        assert row.country == "United States"
        assert row.city == "Denver"
        assert row.duplicate_status == DuplicateStatus.UNKNOWN

    def test_missing_website_returns_a_structured_error_not_an_exception(self) -> None:
        raw = RawStoreLeadsRow(row_number=2, website=None, platform=None, country=None, city=None)

        row = build_import_row(2, raw)

        assert row.validation_status == ValidationStatus.INVALID
        assert row.normalized_domain is None
        assert len(row.errors) == 1
        assert row.errors[0].field == "website"
        assert "website" in row.errors[0].message

    def test_blank_website_is_treated_as_missing(self) -> None:
        raw = RawStoreLeadsRow(row_number=3, website="   ", platform=None, country=None, city=None)

        row = build_import_row(3, raw)

        assert row.validation_status == ValidationStatus.INVALID
        assert row.errors[0].field == "website"

    def test_malformed_website_returns_a_structured_error(self) -> None:
        raw = RawStoreLeadsRow(
            row_number=4, website="http://localhost", platform=None, country=None, city=None
        )

        row = build_import_row(4, raw)

        assert row.validation_status == ValidationStatus.INVALID
        assert row.normalized_domain is None
        assert row.errors[0].field == "website"

    def test_blank_country_and_city_become_none(self) -> None:
        raw = RawStoreLeadsRow(
            row_number=5, website="example.com", platform=None, country="  ", city=""
        )

        row = build_import_row(5, raw)

        assert row.country is None
        assert row.city is None

    def test_row_number_is_preserved(self) -> None:
        raw = RawStoreLeadsRow(
            row_number=7, website="example.com", platform=None, country=None, city=None
        )
        assert build_import_row(7, raw).row_number == 7
