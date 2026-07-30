"""Content hashing and change-detection.

`structural_hash` is deliberately derived from the already-*extracted*
text plus a coarse structural skeleton (tag names only, no attributes) —
never from raw bytes or even cleaned HTML directly. Since text extraction
(`domain/text_extractor.py`) already discards every attribute, script
body, and style body, hashing its output naturally ignores whitespace,
dynamic timestamps, random element IDs, tracking attributes, and script
order "for free," without a second bespoke normalization pass that could
drift out of sync with what extraction already does. A genuine text
change is never hidden by this, because it always changes the very text
being hashed.
"""

import hashlib
import re
from html.parser import HTMLParser

from app.modules.crawling.domain.models import ContentHashes

_STRUCTURAL_TAGS = frozenset(
    {
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "p",
        "ul",
        "ol",
        "li",
        "table",
        "tr",
        "td",
        "th",
        "form",
        "label",
        "button",
        "a",
        "img",
    }
)

_WHITESPACE_RUN = re.compile(r"\s+")


class _SkeletonParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _STRUCTURAL_TAGS:
            self.tags.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)


def _tag_skeleton(cleaned_html: str) -> str:
    parser = _SkeletonParser()
    parser.feed(cleaned_html)
    parser.close()
    return ",".join(parser.tags)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def compute_content_hashes(
    raw_bytes: bytes, cleaned_html: str, extracted_text: str
) -> ContentHashes:
    """Computes every content hash for one fetched page."""
    normalized_text = _WHITESPACE_RUN.sub(" ", extracted_text).strip()
    skeleton = _tag_skeleton(cleaned_html)
    structural_fingerprint = f"{skeleton}\x00{normalized_text}".encode()

    return ContentHashes(
        raw_content_sha256=_sha256(raw_bytes),
        cleaned_html_sha256=_sha256(cleaned_html.encode("utf-8")),
        extracted_text_sha256=_sha256(extracted_text.encode("utf-8")),
        structural_hash=_sha256(structural_fingerprint),
    )


def is_materially_unchanged(previous: ContentHashes, current: ContentHashes) -> bool:
    """Content is "materially identical" when the raw bytes match exactly,
    **or** the structural hash matches even if the raw bytes differ
    (covers pure noise like a changed timestamp/nonce/element id). Any
    other case is a real change."""
    if (
        previous.raw_content_sha256 is not None
        and previous.raw_content_sha256 == current.raw_content_sha256
    ):
        return True
    return (
        previous.structural_hash is not None and previous.structural_hash == current.structural_hash
    )
