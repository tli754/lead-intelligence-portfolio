"""Deterministic HTML cleaning.

Stdlib-only (`html.parser.HTMLParser`, matching the existing discovery
module's own choice — no new `lxml`/`bs4` dependency). Never executes or
evaluates JavaScript; only ever parses text.

`HTMLParser` treats `<script>`/`<style>` bodies as raw CDATA (a single
`handle_data` call, never re-entering tag parsing inside them) — this is
relied on directly rather than reimplemented. `<noscript>`/`<svg>` do not
get that special treatment from the parser, so their *entire* subtree
(including any nested tags) is suppressed via an explicit stack.

**Known analytics scripts keep their tag/`src` attribute, not just an
emptied body.** Every non-`application/ld+json` `<script>`'s *body* is
always stripped (satisfying "no script bodies" uniformly), but the
`<script src="...">` markers themselves are retained rather than deleted
outright — `domain/metadata_extractor.py` (T16) needs those `src` hosts
still present in cleaned HTML to detect known analytics/framework/
commerce-platform technology signals, and it only ever sees cleaned HTML,
never raw. Deleting the tag here would make that detection impossible.
"""

import re
from html.parser import HTMLParser

from pydantic import BaseModel

CLEANING_RULES_VERSION = "v1"

_STRIPPED_ATTRIBUTE_NAMES = frozenset({"nonce", "integrity"})
_SUPPRESSED_SUBTREE_TAGS = frozenset({"noscript", "svg"})

_TRACKING_PIXEL_SRC_MARKERS: tuple[str, ...] = (
    "tracker.",
    "doubleclick.net",
    "scorecardresearch.com",
    "facebook.com/tr",
)

_WHITESPACE_RUN = re.compile(r"\s+")
_REPEATED_SPACES = re.compile(r" {2,}")


class CleanedHtmlResult(BaseModel):
    html: str
    structured_data: list[str] = []
    rules_version: str = CLEANING_RULES_VERSION


def _is_event_handler_attribute(name: str) -> bool:
    return name.lower().startswith("on")


def _is_stripped_attribute(name: str) -> bool:
    return name.lower() in _STRIPPED_ATTRIBUTE_NAMES or _is_event_handler_attribute(name)


def _filtered_attrs(attrs: list[tuple[str, str | None]]) -> list[tuple[str, str | None]]:
    return [(name, value) for name, value in attrs if not _is_stripped_attribute(name)]


def _serialize_starttag(tag: str, attrs: list[tuple[str, str | None]]) -> str:
    parts = [f"<{tag}"]
    for name, value in attrs:
        if value is None:
            parts.append(f" {name}")
        else:
            escaped = value.replace("&", "&amp;").replace('"', "&quot;")
            parts.append(f' {name}="{escaped}"')
    parts.append(">")
    return "".join(parts)


def _is_tracking_pixel(attrs: dict[str, str | None]) -> bool:
    width = (attrs.get("width") or "").strip()
    height = (attrs.get("height") or "").strip()
    if width == "1" and height == "1":
        return True
    src = attrs.get("src") or ""
    return any(marker in src for marker in _TRACKING_PIXEL_SRC_MARKERS)


class _Cleaner(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._output: list[str] = []
        self.structured_data: list[str] = []

        self._suppress_stack: list[str] = []
        self._current_cdata_tag: str | None = None
        self._current_script_mode: str | None = None  # "keep" | "strip_body"

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SUPPRESSED_SUBTREE_TAGS:
            self._suppress_stack.append(tag)
            return
        if self._suppress_stack:
            return

        attrs_dict = dict(attrs)

        if tag == "img" and _is_tracking_pixel(attrs_dict):
            return

        if tag == "script":
            self._current_cdata_tag = "script"
            script_type = (attrs_dict.get("type") or "").lower()
            self._current_script_mode = (
                "keep" if script_type == "application/ld+json" else "strip_body"
            )
            self._output.append(_serialize_starttag(tag, _filtered_attrs(attrs)))
            return

        if tag == "style":
            self._current_cdata_tag = "style"
            self._output.append(_serialize_starttag(tag, _filtered_attrs(attrs)))
            return

        self._output.append(_serialize_starttag(tag, _filtered_attrs(attrs)))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag in _SUPPRESSED_SUBTREE_TAGS or tag in ("script", "style"):
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in _SUPPRESSED_SUBTREE_TAGS:
            for index in range(len(self._suppress_stack) - 1, -1, -1):
                if self._suppress_stack[index] == tag:
                    del self._suppress_stack[index]
                    break
            return
        if self._suppress_stack:
            return

        if tag == "script":
            self._output.append("</script>")
            self._current_cdata_tag = None
            self._current_script_mode = None
            return

        if tag == "style":
            self._output.append("</style>")
            self._current_cdata_tag = None
            return

        self._output.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self._suppress_stack:
            return
        if self._current_cdata_tag == "style":
            return
        if self._current_cdata_tag == "script":
            if self._current_script_mode == "keep":
                self.structured_data.append(data)
                self._output.append(data)
            return

        collapsed = _WHITESPACE_RUN.sub(" ", data)
        self._output.append(" " if collapsed.strip() == "" else collapsed)

    def result_html(self) -> str:
        joined = "".join(self._output)
        return _REPEATED_SPACES.sub(" ", joined)


def clean_html(raw_html: str) -> CleanedHtmlResult:
    """Cleans `raw_html` deterministically — running this twice on the
    same input always produces byte-identical output (no timestamps, no
    randomness, no non-deterministic ordering)."""
    parser = _Cleaner()
    parser.feed(raw_html)
    parser.close()

    return CleanedHtmlResult(
        html=parser.result_html(),
        structured_data=list(parser.structured_data),
        rules_version=CLEANING_RULES_VERSION,
    )
