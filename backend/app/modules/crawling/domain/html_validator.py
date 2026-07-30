"""Validates and safely decodes a fetched HTTP response body before any
HTML parsing is attempted.

All external content is untrusted: this file rejects obvious non-page
content (binary signatures, image/PDF/ZIP/executable content types)
before ever attempting to decode it as text, and tolerates malformed
encoding rather than crashing on it.
"""

import re
from typing import Literal

from pydantic import BaseModel

from app.modules.crawling.domain.config import CrawlConfig
from app.modules.crawling.domain.exceptions import EmptyResponseError, NonHtmlResponseError

# (signature bytes, human-readable label) — checked against the start of
# the raw body before any text decoding is attempted.
_BINARY_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "PNG image"),
    (b"\xff\xd8\xff", "JPEG image"),
    (b"GIF87a", "GIF image"),
    (b"GIF89a", "GIF image"),
    (b"%PDF-", "PDF document"),
    (b"PK\x03\x04", "ZIP archive"),
    (b"PK\x05\x06", "ZIP archive (empty)"),
    (b"MZ", "Windows executable"),
    (b"\x7fELF", "Linux executable"),
)

_REJECTED_CONTENT_TYPE_MARKERS: tuple[str, ...] = (
    "image/",
    "video/",
    "audio/",
    "application/pdf",
    "application/zip",
    "application/x-msdownload",
    "application/octet-stream",
    "application/gzip",
)

_CHARSET_PATTERN = re.compile(r"charset=([\w-]+)", re.IGNORECASE)


class DecodedHtmlResult(BaseModel):
    html: str
    encoding: str
    decode_warnings: list[str] = []
    truncated: bool = False


def _detect_encoding(content_type_header: str | None, raw_bytes: bytes) -> str:
    if content_type_header:
        match = _CHARSET_PATTERN.search(content_type_header)
        if match:
            return match.group(1)
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    if raw_bytes.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "utf-16"
    return "utf-8"


def _reject_binary_signatures(raw_bytes: bytes, *, url: str) -> None:
    for signature, label in _BINARY_SIGNATURES:
        if raw_bytes.startswith(signature):
            raise NonHtmlResponseError(url, reason=f"binary signature detected: {label}")


def _reject_non_page_content_type(content_type_header: str | None, *, url: str) -> None:
    if not content_type_header:
        return
    lowered = content_type_header.lower()
    if "html" in lowered or "text/" in lowered or "xml" in lowered:
        return
    for marker in _REJECTED_CONTENT_TYPE_MARKERS:
        if marker in lowered:
            raise NonHtmlResponseError(
                url, reason=f"unsupported content type: {content_type_header}"
            )


def validate_and_decode(
    raw_bytes: bytes,
    content_type_header: str | None,
    config: CrawlConfig,
    *,
    url: str = "",
) -> DecodedHtmlResult:
    """Validates a fetched body and decodes it into text.

    Raises `EmptyResponseError` for an empty body, `NonHtmlResponseError`
    for a binary-signature match or an obviously non-page content type.
    Never raises for malformed *encoding* — a decode failure is recorded
    as a warning and decoded again with `errors="replace"` instead.
    """
    if not raw_bytes:
        raise EmptyResponseError(url, reason="empty response body")

    _reject_binary_signatures(raw_bytes, url=url)
    _reject_non_page_content_type(content_type_header, url=url)

    encoding = _detect_encoding(content_type_header, raw_bytes)
    decode_warnings: list[str] = []
    truncated = False

    try:
        text = raw_bytes.decode(encoding, errors="strict")
    except (UnicodeDecodeError, LookupError) as error:
        decode_warnings.append(f"failed to decode as {encoding!r}: {error}")
        if isinstance(error, UnicodeDecodeError) and error.start >= len(raw_bytes) - 8:
            # The invalid byte sequence sits right at the end of the
            # buffer — consistent with the response being cut off
            # mid-character rather than containing genuinely malformed
            # text throughout.
            truncated = True
        text = raw_bytes.decode(
            encoding if _is_known_encoding(encoding) else "utf-8", errors="replace"
        )

    if len(text) > config.max_response_size_bytes:
        text = text[: config.max_response_size_bytes]
        truncated = True
        decode_warnings.append("decoded content exceeded the configured size cap; truncated")

    return DecodedHtmlResult(
        html=text, encoding=encoding, decode_warnings=decode_warnings, truncated=truncated
    )


def _is_known_encoding(encoding: str) -> bool:
    try:
        "".encode(encoding)
    except LookupError:
        return False
    return True


ChallengeClassification = Literal[
    "cloudflare_challenge",
    "captcha",
    "access_denied",
    "password_protected_storefront",
    "maintenance_page",
    "bot_challenge",
]


class BlockedPageClassification(BaseModel):
    classification: ChallengeClassification
    rule_id: str
    matched_text: str


# Checked in this fixed order — deterministic even if multiple detectors
# would otherwise match the same page (none of this task's fixtures do).
_CLASSIFIERS: tuple[tuple[ChallengeClassification, str, tuple[str, ...]], ...] = (
    (
        "cloudflare_challenge",
        "challenge:cloudflare",
        ("checking your browser", "cf-browser-verification", "cf-chl-bypass", "just a moment"),
    ),
    (
        "captcha",
        "challenge:captcha",
        ("captcha", "recaptcha", "hcaptcha", "verify you are human"),
    ),
    (
        "access_denied",
        "challenge:access-denied",
        ("access denied", "you don't have permission to access", "403 forbidden"),
    ),
    (
        "password_protected_storefront",
        "challenge:password-storefront",
        (
            "password protected",
            "enter store using password",
            "this store is password protected",
        ),
    ),
    (
        "maintenance_page",
        "challenge:maintenance",
        ("site is under maintenance", "scheduled maintenance", "maintenance mode"),
    ),
    (
        "bot_challenge",
        "challenge:bot-detection",
        ("unusual traffic", "automated queries", "bot detection", "are you a robot"),
    ),
)


def classify_blocked_or_challenge(html: str) -> BlockedPageClassification | None:
    """Deterministically classifies a common blocked/challenge response.

    Returns `None` for an ordinary page. Detection is a plain, versioned
    substring match against known phrases — no ML, no heuristics beyond
    literal text matching, so results are fully reproducible.
    """
    lowered = html.lower()
    for classification, rule_id, phrases in _CLASSIFIERS:
        for phrase in phrases:
            if phrase in lowered:
                return BlockedPageClassification(
                    classification=classification, rule_id=rule_id, matched_text=phrase
                )
    return None
