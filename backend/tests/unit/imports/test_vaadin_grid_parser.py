from pathlib import Path

from app.modules.imports.domain.vaadin_grid_parser import parse_storeleads_vaadin_grid

FIXTURES_DIR = Path(__file__).resolve().parents[4] / "fixtures" / "storeleads"


def _load(name: str) -> str:
    return (FIXTURES_DIR / name).read_text()


class TestParseStoreleadsVaadinGrid:
    def test_parses_a_normal_grid_with_row_numbers(self) -> None:
        rows = parse_storeleads_vaadin_grid(_load("vaadin_grid_standard.html"))

        assert len(rows) == 4
        assert [row.row_number for row in rows] == [1, 2, 3, 4]
        assert rows[0].website == "www.northfieldsupply.com"
        assert rows[0].platform == "Shopify"
        assert rows[0].country == "US"
        assert rows[0].city == "Austin"

    def test_extra_unmapped_columns_never_leak_into_extracted_fields(self) -> None:
        rows = parse_storeleads_vaadin_grid(_load("vaadin_grid_standard.html"))

        for row in rows:
            for field in (row.website, row.platform, row.country, row.city):
                assert field not in {
                    "USD $120,000.00/year",
                    "1 Jan 2021",
                    "https://example-source.test/store",
                    "1.0",
                    "5",
                    "Active",
                    "Retail",
                }

    def test_reordered_columns(self) -> None:
        rows = parse_storeleads_vaadin_grid(_load("vaadin_grid_reordered_columns.html"))

        assert len(rows) == 2
        assert rows[0].website == "www.northfieldsupply.com"
        assert rows[0].platform == "Shopify"
        assert rows[0].country == "US"
        assert rows[0].city == "Austin"
        assert rows[1].website == "brightlanemarket.com"
        assert rows[1].platform == "WooCommerce"

    def test_unknown_platform_value_passes_through_unchanged(self) -> None:
        rows = parse_storeleads_vaadin_grid(_load("vaadin_grid_missing_optional_fields.html"))

        prestashop_row = next(row for row in rows if row.website == "unknownplatformstore.com")
        # Normalization (unknown platform -> null) is row_builder's job, not this parser's.
        assert prestashop_row.platform == "PrestaShop"

    def test_blank_platform_country_city_become_none(self) -> None:
        rows = parse_storeleads_vaadin_grid(_load("vaadin_grid_missing_optional_fields.html"))

        blank_row = next(row for row in rows if row.website == "www.blankfieldsstore.com")
        assert blank_row.platform is None
        assert blank_row.country is None
        assert blank_row.city is None

    def test_malformed_domain_cell_still_emits_the_row(self) -> None:
        rows = parse_storeleads_vaadin_grid(
            _load("vaadin_grid_invalid_and_duplicate_domains.html")
        )

        assert len(rows) == 3
        assert rows[0].website is None  # empty domain cell; row_builder turns this into an error

    def test_duplicate_domains_are_both_emitted_unchanged(self) -> None:
        rows = parse_storeleads_vaadin_grid(
            _load("vaadin_grid_invalid_and_duplicate_domains.html")
        )

        websites = [row.website for row in rows]
        assert websites.count("https://www.dupemarket.com") == 1
        assert websites.count("dupemarket.com") == 1
        # The parser does not dedupe by normalized domain — that is preview_service's job.

    def test_truncated_final_row_is_still_emitted_with_missing_fields_as_none(self) -> None:
        rows = parse_storeleads_vaadin_grid(_load("vaadin_grid_truncated_row.html"))

        assert len(rows) == 3
        truncated = rows[-1]
        assert truncated.website == "www.trailheadoutpost.com"
        assert truncated.platform is None
        assert truncated.country is None
        assert truncated.city is None

    def test_zero_column_declarations_returns_empty_list(self) -> None:
        assert parse_storeleads_vaadin_grid(_load("vaadin_grid_malformed.html")) == []

    def test_zero_select_row_boundaries_returns_empty_list(self) -> None:
        assert parse_storeleads_vaadin_grid(_load("vaadin_grid_empty.html")) == []

    def test_empty_string_input_returns_empty_list(self) -> None:
        assert parse_storeleads_vaadin_grid("") == []

    def test_columns_with_no_known_field_mapping_return_empty_list(self) -> None:
        html = """
        <vaadin-custom-grid>
          <vaadin-grid-selection-column></vaadin-grid-selection-column>
          <vaadin-grid-column name="estimated_sales_yearly"></vaadin-grid-column>
          <vaadin-grid-column name="emails"></vaadin-grid-column>
          <vaadin-grid-cell-content slot="vaadin-grid-cell-content-0">
            <vaadin-checkbox aria-label="Select All"></vaadin-checkbox>
          </vaadin-grid-cell-content>
          <vaadin-grid-cell-content slot="vaadin-grid-cell-content-1">
            <vaadin-checkbox aria-label="Select Row"></vaadin-checkbox>
          </vaadin-grid-cell-content>
          <vaadin-grid-cell-content slot="vaadin-grid-cell-content-2">
            USD $1.00/year
          </vaadin-grid-cell-content>
          <vaadin-grid-cell-content slot="vaadin-grid-cell-content-3">
            someone@example.com
          </vaadin-grid-cell-content>
        </vaadin-custom-grid>
        """
        assert parse_storeleads_vaadin_grid(html) == []

    def test_select_all_checkbox_is_never_treated_as_a_row_boundary(self) -> None:
        rows = parse_storeleads_vaadin_grid(_load("vaadin_grid_standard.html"))

        # 4 data rows in the fixture; if "Select All" were mis-tracked as a
        # row boundary, this would be 5 with a spurious header-derived row.
        assert len(rows) == 4
