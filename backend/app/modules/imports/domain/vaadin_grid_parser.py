"""Parses a StoreLeads Vaadin virtualized-grid export into raw row data.

Pure, I/O-free, and stdlib-only (`html.parser.HTMLParser`) — no new
dependency was added for this, and no FastAPI/MongoDB import. Handles the
`<vaadin-custom-grid>`/`<vaadin-grid-column>`/`<vaadin-grid-cell-content>`
markup StoreLeads' other export shape uses, which has no `<table>`/`<tr>`
anywhere and so is invisible to `storeleads_html_parser.py`'s
`parse_storeleads_table`.

Unlike an ordinary HTML table, this markup carries no per-cell header
association: column identity comes from a separate, earlier list of
`<vaadin-grid-column name="...">` declarations, and row boundaries come
from `<vaadin-checkbox aria-label="Select Row">` markers rather than
`<tr>` tags. Extraction is therefore purely positional (declaration order
and cell order), not name-anchored per cell.
"""

import re
from html.parser import HTMLParser

from app.modules.imports.domain.storeleads_html_parser import RawStoreLeadsRow

_WHITESPACE_PATTERN = re.compile(r"\s+")

# Matches on a <vaadin-grid-column>'s `name` attribute, not header *text*
# (contrast with storeleads_html_parser.py's `_HEADER_ALIASES`, which
# matches a <table> header cell's text) — deliberately a separate, tiny
# constant rather than a shared cross-parser abstraction.
_COLUMN_NAME_ALIASES: dict[str, str] = {
    "domain": "website",
    "platform": "platform",
    "country": "country",
    "city": "city",
}


def _collapse_whitespace(text: str) -> str:
    return _WHITESPACE_PATTERN.sub(" ", text).strip()


def _match_column_field(name: str) -> str | None:
    return _COLUMN_NAME_ALIASES.get(name.strip().lower())


class _VaadinGridParser(HTMLParser):
    """Extracts column order, cell-content text, and row-boundary markers.

    `columns` records every `<vaadin-grid-column name="...">` declaration
    in document order (including columns with no destination field, so
    positional alignment against cell content stays correct). `cell_contents`
    records every `<vaadin-grid-cell-content>` element's flattened text, in
    document order, tolerant of nesting exactly like the table parser's
    `_flush_cell`. `select_row_indices` records the `cell_contents` index of
    each `<vaadin-checkbox aria-label="Select Row">` marker — a data-row
    boundary — deliberately excluding `aria-label="Select All"` (the
    header row's own boundary marker), which is what naturally keeps the
    header row from being emitted as a data row.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.columns: list[str] = []
        self.cell_contents: list[str] = []
        self.select_row_indices: list[int] = []
        self._in_cell_content = False
        self._cell_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "vaadin-grid-column":
            self.columns.append(attrs_dict.get("name") or "")
        elif tag == "vaadin-grid-cell-content":
            self._flush_cell_content()
            self._in_cell_content = True
            self._cell_parts = []
        elif tag == "vaadin-checkbox" and self._in_cell_content:
            if attrs_dict.get("aria-label") == "Select Row":
                self.select_row_indices.append(len(self.cell_contents))

    def handle_endtag(self, tag: str) -> None:
        if tag == "vaadin-grid-cell-content":
            self._flush_cell_content()

    def handle_data(self, data: str) -> None:
        if self._in_cell_content:
            self._cell_parts.append(data)

    def _flush_cell_content(self) -> None:
        if self._in_cell_content:
            self.cell_contents.append(_collapse_whitespace("".join(self._cell_parts)))
        self._in_cell_content = False
        self._cell_parts = []

    def close(self) -> None:
        self._flush_cell_content()
        super().close()


def parse_storeleads_vaadin_grid(html: str) -> list[RawStoreLeadsRow]:
    """Parses a StoreLeads Vaadin-grid export into website/platform/country/city rows.

    For each `<vaadin-checkbox aria-label="Select Row">` boundary at
    `cell_contents` index `i`, the row's data cells are
    `cell_contents[i+1 : i+1+len(columns)]`, mapped positionally against the
    tracked column-name declarations — never by matching cell text, since
    a Vaadin-grid cell carries no header association of its own.

    Never raises on malformed/empty input: no `<vaadin-grid-column>`
    declarations, or none of them mapping to a known field, or no
    `Select Row` boundaries, all return `[]` rather than fabricating
    all-`None` rows. A truncated final row (fewer trailing cells than the
    full column count — plausible since the grid is virtualized and a copy
    can end mid-row) is still emitted, with any field whose column index
    falls outside the available cells treated as `None`, mirroring
    `parse_storeleads_table`'s own out-of-range tolerance. Malformed
    `domain` cell content is not validated here — same division of
    responsibility as the table parser: `row_builder.build_import_row` is
    what turns a bad `website` value into a structured `ImportRowError`.
    """
    parser = _VaadinGridParser()
    parser.feed(html)
    parser.close()

    if not parser.columns or not parser.select_row_indices:
        return []

    column_fields = [_match_column_field(name) for name in parser.columns]
    if not any(field is not None for field in column_fields):
        return []

    cells = parser.cell_contents
    parsed_rows: list[RawStoreLeadsRow] = []
    for row_number, start_index in enumerate(parser.select_row_indices, start=1):
        row_cells = cells[start_index + 1 : start_index + 1 + len(column_fields)]

        values: dict[str, str] = {}
        for index, field in enumerate(column_fields):
            if field is None or index >= len(row_cells):
                continue
            value = row_cells[index]
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
