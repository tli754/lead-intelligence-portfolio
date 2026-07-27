"""Extracts links from a homepage's HTML.

Pure, stdlib-only (`html.parser.HTMLParser` — the same parser choice as
`modules/imports/domain/storeleads_html_parser.py`, "a parser already
approved by the project"; no browser dependency, no JavaScript
execution). Malformed HTML is tolerated: the stdlib parser recovers from
broken markup rather than raising.
"""

from html.parser import HTMLParser

from pydantic import BaseModel

from app.modules.discovery.domain.enums import DiscoverySource
from app.modules.discovery.domain.url_normalizer import normalize_discovered_url

_NAV_CONTEXT_TAGS = frozenset({"nav", "header"})
_FOOTER_CONTEXT_TAGS = frozenset({"footer"})
_CONTEXT_TAGS = _NAV_CONTEXT_TAGS | _FOOTER_CONTEXT_TAGS


class ExtractedLink(BaseModel):
    """One de-duplicated (by `resolved_url`) link found on the homepage."""

    href: str
    resolved_url: str
    anchor_texts: list[str]
    sources: list[DiscoverySource]
    source_url: str
    depth: int = 1


class ExtractionResult(BaseModel):
    links: list[ExtractedLink]
    canonical_url: str | None
    alternate_urls: list[str]


def _collapse_whitespace(text: str) -> str:
    return " ".join(text.split())


class _HomepageParser(HTMLParser):
    def __init__(self, source_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self._source_url = source_url
        self._context_stack: list[str] = []
        self._in_anchor = False
        self._anchor_href: str | None = None
        self._anchor_text_parts: list[str] = []

        # Raw findings, in encounter order — deduplication by resolved URL
        # happens in `extract_links` after parsing.
        self.raw_links: list[tuple[str, str, DiscoverySource]] = []
        self.canonical_href: str | None = None
        self.alternate_hrefs: list[str] = []

    def _current_source(self) -> DiscoverySource:
        for tag in reversed(self._context_stack):
            if tag in _NAV_CONTEXT_TAGS:
                return DiscoverySource.NAVIGATION
            if tag in _FOOTER_CONTEXT_TAGS:
                return DiscoverySource.FOOTER
        return DiscoverySource.BODY_LINK

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)

        if tag in _CONTEXT_TAGS:
            self._context_stack.append(tag)

        if tag == "a":
            # A still-open `<a>` (unclosed before this one starts) is
            # implicitly closed here, the same way a browser would treat
            # it — `<a>` cannot legally nest, so the next `<a>` always
            # ends the previous one.
            self._flush_anchor()
            href = attr_dict.get("href")
            self._in_anchor = True
            self._anchor_href = href.strip() if href else None
            self._anchor_text_parts = []
        elif tag == "link":
            rel = (attr_dict.get("rel") or "").strip().lower()
            href = attr_dict.get("href")
            if not href:
                return
            href = href.strip()
            if rel == "canonical" and self.canonical_href is None:
                self.canonical_href = href
            elif rel == "alternate":
                self.alternate_hrefs.append(href)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # Self-closed tags (e.g. `<link .../>`) never open a context or an anchor.
        self.handle_starttag(tag, attrs)
        if tag == "a":
            self._in_anchor = False
            self._anchor_href = None

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._flush_anchor()

        if tag in _CONTEXT_TAGS:
            for index in range(len(self._context_stack) - 1, -1, -1):
                if self._context_stack[index] == tag:
                    del self._context_stack[index]
                    break

    def handle_data(self, data: str) -> None:
        if self._in_anchor:
            self._anchor_text_parts.append(data)

    def _flush_anchor(self) -> None:
        if self._in_anchor and self._anchor_href:
            text = _collapse_whitespace("".join(self._anchor_text_parts))
            self.raw_links.append((self._anchor_href, text, self._current_source()))
        self._in_anchor = False
        self._anchor_href = None
        self._anchor_text_parts = []

    def close(self) -> None:
        self._flush_anchor()
        super().close()


def extract_links(html: str, *, source_url: str) -> ExtractionResult:
    """Parses `html` (as fetched from `source_url`) into deduplicated links.

    Links with an empty/missing href, or a non-web/malformed href, are
    silently dropped (not reported as errors) — invalid hrefs are common
    and expected in real-world markup.
    """
    parser = _HomepageParser(source_url)
    parser.feed(html)
    parser.close()

    merged: dict[str, ExtractedLink] = {}
    for href, anchor_text, source in parser.raw_links:
        result = normalize_discovered_url(href, source_page_url=source_url)
        if not result.is_valid or result.normalized_url is None:
            continue

        existing = merged.get(result.normalized_url)
        if existing is None:
            merged[result.normalized_url] = ExtractedLink(
                href=href,
                resolved_url=result.normalized_url,
                anchor_texts=[anchor_text] if anchor_text else [],
                sources=[source],
                source_url=source_url,
            )
            continue

        if anchor_text and anchor_text not in existing.anchor_texts:
            existing.anchor_texts.append(anchor_text)
        if source not in existing.sources:
            existing.sources.append(source)

    canonical_url: str | None = None
    if parser.canonical_href:
        result = normalize_discovered_url(parser.canonical_href, source_page_url=source_url)
        canonical_url = result.normalized_url if result.is_valid else None

    alternate_urls: list[str] = []
    for href in parser.alternate_hrefs:
        result = normalize_discovered_url(href, source_page_url=source_url)
        if result.is_valid and result.normalized_url is not None:
            alternate_urls.append(result.normalized_url)

    return ExtractionResult(
        links=list(merged.values()), canonical_url=canonical_url, alternate_urls=alternate_urls
    )
