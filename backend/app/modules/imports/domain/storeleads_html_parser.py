"""Parses an HTML `<table>` copied from StoreLeads into raw row data.

Pure, I/O-free, and stdlib-only (`html.parser.HTMLParser`) — no new
dependency was added for this, and no FastAPI/MongoDB import. Handles
ordinary HTML table markup (`<table>`/`<thead>`/`<tbody>`/`<tr>`/`<td>`),
not the Vaadin custom-grid markup — StoreLeads' other export shape,
handled by the sibling `vaadin_grid_parser.py` in this same module and
dispatched to by `format_detector.py` — since StoreLeads table copies
are plain HTML tables, not a virtualized custom-element grid.
"""

import re
from html.parser import HTMLParser
from typing import NamedTuple

_CELL_TAGS = {"td", "th"}

_HEADER_ALIASES: dict[str, frozenset[str]] = {
    "website": frozenset({"website", "domain", "url", "site"}),
    "platform": frozenset({"platform"}),
    "country": frozenset({"country"}),
    "city": frozenset({"city"}),
}

_WHITESPACE_PATTERN = re.compile(r"\s+")


def _collapse_whitespace(text: str) -> str:
    return _WHITESPACE_PATTERN.sub(" ", text).strip()


class RawStoreLeadsRow(NamedTuple):
    """One data row, columns already mapped to their field by header text.

    `row_number` is 1-based among data rows only (the header row, and any
    fully-empty rows, are not counted).
    """

    row_number: int
    website: str | None
    platform: str | None
    country: str | None
    city: str | None


class _TableCellParser(HTMLParser):
    """Extracts every `<tr>` as a list of cell texts, tolerant of nesting.

    A cell's text is the concatenation of all text nodes inside it,
    regardless of how deeply nested (`<a>`, `<span>`, etc.) — nested tags
    never stop text accumulation, only `<td>`/`<th>` boundaries do.
    Missing closing tags are tolerated by flushing whatever is open when
    the next `<tr>`/`<td>`/`<th>` starts.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._current_row: list[str] | None = None
        self._in_cell = False
        self._cell_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._flush_row()
            self._current_row = []
        elif tag in _CELL_TAGS:
            self._flush_cell()
            self._in_cell = True
            self._cell_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag in _CELL_TAGS:
            self._flush_cell()
        elif tag == "tr":
            self._flush_row()

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_parts.append(data)

    def _flush_cell(self) -> None:
        if self._in_cell and self._current_row is not None:
            self._current_row.append(_collapse_whitespace("".join(self._cell_parts)))
        self._in_cell = False
        self._cell_parts = []

    def _flush_row(self) -> None:
        self._flush_cell()
        if self._current_row is not None:
            self.rows.append(self._current_row)
        self._current_row = None

    def close(self) -> None:
        self._flush_row()
        super().close()


def _match_header_field(header_text: str) -> str | None:
    normalized = header_text.strip().lower()
    for field, aliases in _HEADER_ALIASES.items():
        if normalized in aliases:
            return field
    return None


def parse_storeleads_table(html: str) -> list[RawStoreLeadsRow]:
    """Parses raw StoreLeads HTML into rows mapped to website/platform/country/city.

    The first `<tr>` found is treated as the header row (case-insensitive,
    order-independent column matching); unrecognized header columns are
    ignored. Fully-empty rows (every cell blank) are skipped and do not
    consume a row number. A row missing a website value is still returned
    (with `website=None`) rather than dropped — `row_builder.py` is
    responsible for turning that into a structured validation error.
    """
    parser = _TableCellParser()
    parser.feed(html)
    parser.close()

    non_empty_rows = [row for row in parser.rows if any(cell for cell in row)]
    if not non_empty_rows:
        return []

    header, *data_rows = non_empty_rows
    column_fields = [_match_header_field(cell) for cell in header]

    parsed_rows: list[RawStoreLeadsRow] = []
    for row_number, cells in enumerate(data_rows, start=1):
        values: dict[str, str] = {}
        for index, field in enumerate(column_fields):
            if field is None or index >= len(cells):
                continue
            value = cells[index]
            if value:
                values[field] = value

        parsed_rows.append(
            RawStoreLeadsRow(
                row_number=row_number,
                website=values.get("website"),
                platform=values.get("platform"),
                country=values.get("country"),
                city=values.get("city"),
            )
        )

    return parsed_rows
