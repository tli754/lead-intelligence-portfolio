from pathlib import Path

from app.modules.imports.domain.storeleads_html_parser import parse_storeleads_table

FIXTURES_DIR = Path(__file__).resolve().parents[4] / "fixtures" / "storeleads"


def _load(name: str) -> str:
    return (FIXTURES_DIR / name).read_text()


class TestParseStoreleadsTable:
    def test_parses_a_normal_table(self) -> None:
        rows = parse_storeleads_table(_load("standard_table.html"))

        assert len(rows) == 3
        assert rows[0].row_number == 1
        assert rows[0].website == "https://www.summitoutfitters.com"
        assert rows[0].platform == "Shopify"
        assert rows[0].country == "United States"
        assert rows[0].city == "Denver"

    def test_handles_blank_cells(self) -> None:
        rows = parse_storeleads_table(_load("standard_table.html"))

        # Row 2's City cell is whitespace-only; row 3's is fully empty.
        assert rows[1].city is None
        assert rows[2].city is None

    def test_handles_nested_anchor_elements(self) -> None:
        rows = parse_storeleads_table(_load("standard_table.html"))

        # The website cell wraps its text in <a href="...">...</a>.
        assert rows[0].website == "https://www.summitoutfitters.com"
        assert rows[1].website == "quickcartbargains.com"

    def test_handles_reordered_columns(self) -> None:
        rows = parse_storeleads_table(_load("reordered_columns.html"))

        assert len(rows) == 2
        assert rows[0].website == "https://palisadeoutdoor.com"
        assert rows[0].city == "Boise"
        assert rows[0].country == "United States"
        assert rows[0].platform == "Shopify"

    def test_ignores_unrelated_columns(self) -> None:
        rows = parse_storeleads_table(_load("extra_columns.html"))

        assert len(rows) == 2
        assert rows[0].website == "meridiantrailhead.com"
        assert rows[0].platform == "Shopify"
        assert rows[0].country == "United States"
        assert rows[0].city == "Bend"

    def test_preserves_row_numbers_and_skips_fully_empty_rows(self) -> None:
        rows = parse_storeleads_table(_load("empty_table.html"))

        assert rows == []

    def test_row_numbers_are_one_based_and_exclude_the_header(self) -> None:
        rows = parse_storeleads_table(_load("duplicate_websites.html"))

        assert [row.row_number for row in rows] == [1, 2, 3, 4]

    def test_no_rows_at_all_returns_empty_list(self) -> None:
        assert parse_storeleads_table("<table></table>") == []

    def test_case_insensitive_header_matching(self) -> None:
        html = """
        <table>
          <tr><th>WEBSITE</th><th>PLATFORM</th></tr>
          <tr><td>example.com</td><td>Shopify</td></tr>
        </table>
        """
        rows = parse_storeleads_table(html)
        assert rows[0].website == "example.com"
        assert rows[0].platform == "Shopify"

    def test_tolerates_deeply_nested_whitespace(self) -> None:
        html = """
        <table>
          <tr><th>Website</th></tr>
          <tr><td>
            <span>  example.com  </span>
          </td></tr>
        </table>
        """
        rows = parse_storeleads_table(html)
        assert rows[0].website == "example.com"
