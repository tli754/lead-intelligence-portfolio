"""Small, shared, stdlib-only HTML/text helpers used by every extractor family.

Operates only on already-cleaned HTML (`PageContext.cleaned_html`, produced
by `modules/crawling/domain/html_cleaner.py`) or already-extracted plain
text (`PageContext.extracted_text`) — never fetches anything, never
executes/evaluates page content. `application/ld+json` script bodies are
preserved by crawling's cleaner specifically so JSON-LD extraction here
still works without needing raw HTML.
"""

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any

_WHITESPACE_RUN = re.compile(r"\s+")


def collapse_whitespace(text: str) -> str:
    return _WHITESPACE_RUN.sub(" ", text).strip()


class _PageStructureParser(HTMLParser):
    """A single pass collecting everything the identity/business/etc.
    extractors commonly need: JSON-LD blocks, meta tags, title, html lang,
    anchors, and image alt text — one HTML parse per page, not one per
    extractor."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.json_ld_blocks: list[Any] = []
        self.meta_tags: dict[str, str] = {}
        self.title: str | None = None
        self.html_lang: str | None = None
        self.anchors: list[dict[str, str]] = []
        self.images: list[dict[str, str]] = []

        self._in_json_ld = False
        self._json_ld_buffer: list[str] = []
        self._in_title = False
        self._title_parts: list[str] = []
        self._current_anchor_href: str | None = None
        self._current_anchor_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "html":
            lang = attrs_dict.get("lang")
            if lang:
                self.html_lang = lang
        elif tag == "meta":
            name = (attrs_dict.get("name") or attrs_dict.get("property") or "").lower()
            content = attrs_dict.get("content")
            if name and content is not None:
                self.meta_tags[name] = content
        elif tag == "title":
            self._in_title = True
            self._title_parts = []
        elif tag == "script" and (attrs_dict.get("type") or "").lower() == "application/ld+json":
            self._in_json_ld = True
            self._json_ld_buffer = []
        elif tag == "a":
            self._current_anchor_href = attrs_dict.get("href")
            self._current_anchor_text = []
        elif tag == "img":
            self.images.append(
                {
                    "src": attrs_dict.get("src") or "",
                    "alt": attrs_dict.get("alt") or "",
                    "class": attrs_dict.get("class") or "",
                    "id": attrs_dict.get("id") or "",
                }
            )

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
            self.title = collapse_whitespace("".join(self._title_parts)) or None
        elif tag == "script" and self._in_json_ld:
            self._in_json_ld = False
            raw = "".join(self._json_ld_buffer).strip()
            if raw:
                try:
                    parsed = json.loads(raw)
                except (json.JSONDecodeError, ValueError):
                    parsed = None
                if parsed is not None:
                    self.json_ld_blocks.append(parsed)
        elif tag == "a":
            if self._current_anchor_href is not None:
                self.anchors.append(
                    {
                        "href": self._current_anchor_href,
                        "text": collapse_whitespace("".join(self._current_anchor_text)),
                    }
                )
            self._current_anchor_href = None
            self._current_anchor_text = []

    def handle_data(self, data: str) -> None:
        if self._in_json_ld:
            self._json_ld_buffer.append(data)
        if self._in_title:
            self._title_parts.append(data)
        if self._current_anchor_href is not None:
            self._current_anchor_text.append(data)


@dataclass(frozen=True)
class PageStructure:
    json_ld_blocks: list[Any]
    meta_tags: dict[str, str]
    title: str | None
    html_lang: str | None
    anchors: list[dict[str, str]]
    images: list[dict[str, str]]


def parse_page_structure(cleaned_html: str) -> PageStructure:
    parser = _PageStructureParser()
    parser.feed(cleaned_html)
    parser.close()
    return PageStructure(
        json_ld_blocks=parser.json_ld_blocks,
        meta_tags=parser.meta_tags,
        title=parser.title,
        html_lang=parser.html_lang,
        anchors=parser.anchors,
        images=parser.images,
    )


def flatten_json_ld_entities(blocks: list[Any]) -> list[dict[str, Any]]:
    """Flattens JSON-LD blocks (which may be a single object, a list of
    objects, or a `{"@graph": [...]}` wrapper) into a flat list of dict
    entities — malformed/non-dict entries are silently skipped, never
    raised (structured-data-malformed.html fixture coverage)."""
    entities: list[dict[str, Any]] = []
    for block in blocks:
        candidates: list[Any]
        if isinstance(block, list):
            candidates = block
        elif isinstance(block, dict) and isinstance(block.get("@graph"), list):
            candidates = block["@graph"]
        else:
            candidates = [block]
        for candidate in candidates:
            if isinstance(candidate, dict):
                entities.append(candidate)
    return entities


def json_ld_entities_of_type(
    entities: list[dict[str, Any]], *type_names: str
) -> list[dict[str, Any]]:
    wanted = {name.lower() for name in type_names}
    matches = []
    for entity in entities:
        entity_type = entity.get("@type")
        type_values = entity_type if isinstance(entity_type, list) else [entity_type]
        if any(isinstance(t, str) and t.lower() in wanted for t in type_values):
            matches.append(entity)
    return matches


def context_window(
    text: str, start: int, end: int, *, prefix_chars: int = 150, suffix_chars: int = 150
):
    prefix = text[max(0, start - prefix_chars) : start]
    suffix = text[end : end + suffix_chars]
    return prefix, suffix


def find_matches_with_context(
    text: str, pattern: re.Pattern[str], *, prefix_chars: int = 150, suffix_chars: int = 150
) -> list[tuple[re.Match[str], str, str]]:
    """Every regex match in `text`, paired with its prefix/suffix context
    window — used to build evidence excerpts and to evaluate a pattern's
    `context_requirements`."""
    results = []
    for match in pattern.finditer(text):
        prefix, suffix = context_window(
            text, match.start(), match.end(), prefix_chars=prefix_chars, suffix_chars=suffix_chars
        )
        results.append((match, prefix, suffix))
    return results
