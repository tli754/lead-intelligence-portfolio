"""Pure parsing functions for the `companies` import feature.

Nothing in this module performs I/O (no MongoDB, no HTTP). Every
function is a deterministic transformation of an input string into
structured data, which keeps it trivially unit-testable.

`platform_version` (the "pv" column in storelead.app's export) is
intentionally never extracted here — see ADR 0002 in docs/decisions/ and
Task 8 of the feature contract. The row-segmentation algorithm below
naturally never selects it: version-like strings (e.g. "2.4") do not
match the hostname pattern used to anchor rows, and they contain no
`mailto:`/`tel:`/`href="https`-style content, so they cannot bleed into
another row's extracted fields either.
"""

import re
from datetime import date, datetime
from typing import Literal, NamedTuple

from app.domains.companies.models import SkippedInvalidEntry

DetectedFormat = Literal["domain_list", "storeleads_html"]

_HOSTNAME_PATTERN = re.compile(
    r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$"
)

_STORELEADS_HTML_MARKER = "<vaadin-grid-cell-content"

_ROW_ANCHOR_PATTERN = re.compile(
    r'<div class="default">(?:<!--.*?-->)*\s*([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\s*</div>'
)
_SALES_PATTERN = re.compile(r"USD \$([0-9,]+\.[0-9]{2})/year")
_CREATED_PATTERN = re.compile(r"\b(\d{1,2} [A-Z][a-z]{2} \d{4})\b")
_EMAIL_PATTERN = re.compile(r'href="mailto:([^"]*)"')
_PHONE_PATTERN = re.compile(r'href="tel:([^"]*)"')
_URL_PATTERN = re.compile(r'<a class="tdu pc cpoint"[^>]*href="(https?://[^"]+)"')

_CREATED_DATE_FORMAT = "%d %b %Y"


class ParsedRow(NamedTuple):
    """A single successfully-parsed row prior to persistence."""

    domain: str
    url: str | None
    estimated_sales_yearly_usd: float | None
    source_created_at: date | None
    emails: list[str]
    phones: list[str]


class ParsedRows(NamedTuple):
    """The output of parsing a paste: successful rows plus skip reasons."""

    rows: list[ParsedRow]
    skipped_duplicate_in_paste: list[str]
    skipped_invalid: list[SkippedInvalidEntry]


def normalize_domain(raw: str) -> str | None:
    """Normalize a raw domain-ish string, or return None if invalid.

    Trims whitespace, strips a leading `http(s)://` scheme, strips
    everything from the first `/` onward, strips a trailing dot, and
    lowercases. Does NOT strip a leading `www.` — kept as a distinguishing
    part of the hostname so `www.example.com` and `example.com` are never
    silently merged into one domain.
    """
    value = raw.strip()
    value = re.sub(r"^https?://", "", value, flags=re.IGNORECASE)
    value = value.split("/", 1)[0]
    value = value.rstrip(".")
    value = value.lower()

    if not _HOSTNAME_PATTERN.match(value):
        return None
    return value


def detect_format(raw_text: str) -> DetectedFormat:
    """Classify a paste as either a plain domain list or storeleads HTML.

    If HTML is detected, the entire input is parsed only as HTML — any
    stray non-grid text in the same paste is not separately parsed as
    domain-list lines (avoids ambiguous double-parsing of pathological
    mixed input).
    """
    if _STORELEADS_HTML_MARKER in raw_text:
        return "storeleads_html"
    return "domain_list"


def parse_domain_list(raw_text: str) -> ParsedRows:
    """Parse a newline-separated list of raw domain strings."""
    rows: list[ParsedRow] = []
    skipped_duplicate_in_paste: list[str] = []
    skipped_invalid: list[SkippedInvalidEntry] = []
    seen_domains: set[str] = set()

    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue

        domain = normalize_domain(line)
        if domain is None:
            skipped_invalid.append(
                SkippedInvalidEntry(raw_value=line, reason="not a valid domain")
            )
            continue

        if domain in seen_domains:
            skipped_duplicate_in_paste.append(domain)
            continue

        seen_domains.add(domain)
        rows.append(
            ParsedRow(
                domain=domain,
                url=None,
                estimated_sales_yearly_usd=None,
                source_created_at=None,
                emails=[],
                phones=[],
            )
        )

    return ParsedRows(
        rows=rows,
        skipped_duplicate_in_paste=skipped_duplicate_in_paste,
        skipped_invalid=skipped_invalid,
    )


def _parse_sales(chunk: str) -> float | None:
    match = _SALES_PATTERN.search(chunk)
    if match is None:
        return None
    return float(match.group(1).replace(",", ""))


def _parse_created_date(chunk: str) -> date | None:
    match = _CREATED_PATTERN.search(chunk)
    if match is None:
        return None
    return datetime.strptime(match.group(1), _CREATED_DATE_FORMAT).date()


def parse_storeleads_html(raw_text: str) -> ParsedRows:
    """Parse raw HTML copied from storelead.app's lead grid.

    Regex/anchor based, not DOM-tree-position based: domain matches in
    `<div class="default">...</div>` cells are used as row-boundary
    anchors, and everything between one anchor and the next is treated as
    that row's HTML chunk. This is resilient to storelead.app's grid
    rendering only a window of DOM nodes into the paste, which breaks
    naive DOM-tree parsing.
    """
    rows: list[ParsedRow] = []
    skipped_duplicate_in_paste: list[str] = []
    skipped_invalid: list[SkippedInvalidEntry] = []
    seen_domains: set[str] = set()

    anchors = list(_ROW_ANCHOR_PATTERN.finditer(raw_text))

    for index, anchor in enumerate(anchors):
        chunk_start = anchor.start()
        chunk_end = anchors[index + 1].start() if index + 1 < len(anchors) else len(raw_text)
        chunk = raw_text[chunk_start:chunk_end]

        raw_domain = anchor.group(1)
        domain = normalize_domain(raw_domain)
        if domain is None:
            skipped_invalid.append(
                SkippedInvalidEntry(raw_value=raw_domain, reason="not a valid domain")
            )
            continue

        if domain in seen_domains:
            skipped_duplicate_in_paste.append(domain)
            continue
        seen_domains.add(domain)

        url_match = _URL_PATTERN.search(chunk)
        emails = [email for email in _EMAIL_PATTERN.findall(chunk) if email]
        phones = [phone for phone in _PHONE_PATTERN.findall(chunk) if phone]

        rows.append(
            ParsedRow(
                domain=domain,
                url=url_match.group(1) if url_match else None,
                estimated_sales_yearly_usd=_parse_sales(chunk),
                source_created_at=_parse_created_date(chunk),
                emails=emails,
                phones=phones,
            )
        )

    return ParsedRows(
        rows=rows,
        skipped_duplicate_in_paste=skipped_duplicate_in_paste,
        skipped_invalid=skipped_invalid,
    )
