"""Classifies raw StoreLeads HTML as `<table>` or Vaadin-grid markup.

Pure, marker-based, no FastAPI/MongoDB import — mirrors
`app/domains/companies/parsing.py`'s `detect_format`, reusing the same
marker constant (`"<vaadin-grid-cell-content"`) that file already uses to
distinguish its own two input shapes.
"""

from typing import Literal

DetectedImportFormat = Literal["table", "vaadin_grid"]

_VAADIN_GRID_MARKER = "<vaadin-grid-cell-content"


def detect_storeleads_format(html: str) -> DetectedImportFormat:
    """Classifies a StoreLeads paste as `"table"` or `"vaadin_grid"`.

    Presence of the `<vaadin-grid-cell-content` marker substring classifies
    as `"vaadin_grid"`; anything else — including empty/garbage input,
    plain `<table>` markup, or pathological input containing both an actual
    `<table>` and the marker substring (marker takes priority) — falls back
    to `"table"`, preserving `parse_storeleads_table`'s existing behavior
    for everything not positively identified as the grid format.
    """
    if _VAADIN_GRID_MARKER in html:
        return "vaadin_grid"
    return "table"
