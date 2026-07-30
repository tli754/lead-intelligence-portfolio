"""Deterministic visible-text extraction from already-cleaned HTML.

Stdlib-only (`html.parser.HTMLParser`). Never summarizes or paraphrases —
this is extraction, not interpretation. Operates on `clean_html`'s output,
so script/style bodies are already empty; the skip-stack here is
defensive, not load-bearing.
"""

import re
from html.parser import HTMLParser

from pydantic import BaseModel

TEXT_EXTRACTION_RULES_VERSION = "v1"

_BLOCK_TAGS = frozenset(
    {
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "p",
        "li",
        "td",
        "th",
        "blockquote",
        "dt",
        "dd",
        "figcaption",
    }
)

# A block of text repeated more than this many times (e.g. a nav/footer
# link list repeated on every "page" of a listing) is reduced rather than
# repeated verbatim for every occurrence.
_MAX_REPEATED_BLOCK_OCCURRENCES = 2

_WHITESPACE_RUN = re.compile(r"\s+")
_MIN_MEANINGFUL_ALT_LENGTH = 3


class ExtractedTextResult(BaseModel):
    text: str
    truncated: bool = False
    rules_version: str = TEXT_EXTRACTION_RULES_VERSION


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self._skip_stack: list[str] = []
        self._capturing = False
        self._current_tag: str | None = None
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self._skip_stack.append(tag)
            return
        if self._skip_stack:
            return

        if tag == "img":
            attrs_dict = dict(attrs)
            alt = (attrs_dict.get("alt") or "").strip()
            if len(alt) > _MIN_MEANINGFUL_ALT_LENGTH:
                if self._capturing:
                    self._buffer.append(alt)
                else:
                    self._emit_block(alt)
            return

        if tag in _BLOCK_TAGS and not self._capturing:
            self._capturing = True
            self._current_tag = tag
            self._buffer = []

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag in ("script", "style"):
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            if self._skip_stack and self._skip_stack[-1] == tag:
                self._skip_stack.pop()
            return
        if self._skip_stack:
            return
        if self._capturing and tag == self._current_tag:
            self._emit_block("".join(self._buffer))
            self._capturing = False
            self._current_tag = None
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._skip_stack:
            return
        if self._capturing:
            self._buffer.append(data)

    def _emit_block(self, raw_text: str) -> None:
        collapsed = _WHITESPACE_RUN.sub(" ", raw_text).strip()
        if collapsed:
            self.blocks.append(collapsed)


def extract_text(cleaned_html: str, *, max_length: int = 250_000) -> ExtractedTextResult:
    """Extracts visible text in document order, deterministically.

    Repeated identical blocks (boilerplate nav/footer content) are kept
    at most `_MAX_REPEATED_BLOCK_OCCURRENCES` times rather than repeated
    verbatim for every occurrence. The result is capped at `max_length`
    characters, with truncation recorded — never silently dropped.
    """
    extractor = _Extractor()
    extractor.feed(cleaned_html)
    extractor.close()

    seen_counts: dict[str, int] = {}
    reduced_blocks: list[str] = []
    for block in extractor.blocks:
        count = seen_counts.get(block, 0)
        if count < _MAX_REPEATED_BLOCK_OCCURRENCES:
            reduced_blocks.append(block)
        seen_counts[block] = count + 1

    text = "\n".join(reduced_blocks)
    truncated = False
    if len(text) > max_length:
        text = text[:max_length]
        truncated = True

    return ExtractedTextResult(text=text, truncated=truncated)
