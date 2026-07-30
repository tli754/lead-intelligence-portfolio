"""Parses one sitemap document (XML urlset, XML sitemap index, or a
plain-text URL list), optionally gzip-compressed.

Pure, stdlib-only (`xml.etree.ElementTree`, `gzip`) — no new dependency
(`defusedxml` isn't available without a `pyproject.toml` edit, out of
scope here). Only parses sitemap *documents* — never fetches or stores
the pages they list. Recursion across a `<sitemapindex>`'s nested
sitemaps (loop prevention, depth/file-count limits) is an orchestration
concern handled by the caller (`application/website_discovery_service.py`),
not this per-document parser.
"""

import gzip
import xml.etree.ElementTree as ET
from io import BytesIO

from pydantic import BaseModel

from app.modules.discovery.domain.config import DiscoveryConfig
from app.modules.discovery.domain.domain_relationships import is_same_registrable_domain
from app.modules.discovery.domain.url_normalizer import extract_hostname, normalize_discovered_url

_GZIP_MAGIC = b"\x1f\x8b"
_PRODUCT_PATH_MARKERS = ("/product/", "/products/")


class SitemapUrlEntry(BaseModel):
    loc: str
    normalized_url: str
    lastmod: str | None = None


class SitemapParseResult(BaseModel):
    is_index: bool
    url_entries: list[SitemapUrlEntry]
    nested_sitemap_urls: list[str]
    total_url_count: int
    product_sitemap_detected: bool
    warnings: list[str]
    format: str  # "xml" | "xml_index" | "plain_text" | "unknown"


class _ElementLimitExceeded(Exception):
    pass


class _XmlParseOutcome:
    def __init__(self) -> None:
        self.malformed_reason: str | None = None
        self.element_limit_exceeded = False
        self.root_tag: str | None = None
        self.url_entries: list[tuple[str, str | None]] = []
        self.sitemap_entries: list[str] = []


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _find_child_text(elem: ET.Element, local_name: str) -> str | None:
    for child in elem:
        if _local_name(child.tag) == local_name:
            return (child.text or "").strip() or None
    return None


def _decompress_capped(raw: bytes, max_size: int) -> bytes | None:
    """Decompresses a gzip payload, aborting (returns `None`) past `max_size`
    decompressed bytes — defense against a "zip bomb" style small-compressed,
    huge-decompressed payload."""
    try:
        with gzip.GzipFile(fileobj=BytesIO(raw)) as gz:
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = gz.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_size:
                    return None
                chunks.append(chunk)
            return b"".join(chunks)
    except OSError:
        return None


def _maybe_decompress(
    raw: bytes, *, content_type: str | None, source_url: str, max_size: int
) -> bytes | None:
    looks_gzip = (
        raw.startswith(_GZIP_MAGIC)
        or (content_type is not None and "gzip" in content_type.lower())
        or source_url.lower().endswith(".gz")
    )
    if not looks_gzip:
        return raw
    return _decompress_capped(raw, max_size)


def _parse_xml(data: bytes, *, max_elements: int) -> _XmlParseOutcome:
    outcome = _XmlParseOutcome()
    element_count = 0
    try:
        for event, elem in ET.iterparse(BytesIO(data), events=("start", "end")):
            local = _local_name(elem.tag)
            if event == "start":
                if outcome.root_tag is None:
                    outcome.root_tag = local
                continue

            element_count += 1
            if element_count > max_elements:
                outcome.element_limit_exceeded = True
                break

            if local == "url":
                loc = _find_child_text(elem, "loc")
                if loc:
                    outcome.url_entries.append((loc, _find_child_text(elem, "lastmod")))
                elem.clear()
            elif local == "sitemap":
                loc = _find_child_text(elem, "loc")
                if loc:
                    outcome.sitemap_entries.append(loc)
                elem.clear()
    except ET.ParseError as error:
        outcome.malformed_reason = str(error)
    return outcome


def _looks_like_product_url(normalized_url: str) -> bool:
    lowered = normalized_url.lower()
    return any(marker in lowered for marker in _PRODUCT_PATH_MARKERS)


def _build_url_entries(
    raw_locs: list[str],
    lastmods: list[str | None],
    *,
    root_domain: str,
    config: DiscoveryConfig,
) -> tuple[list[SitemapUrlEntry], int, bool, list[str]]:
    warnings: list[str] = []
    valid: list[SitemapUrlEntry] = []
    product_like_count = 0

    for loc, lastmod in zip(raw_locs, lastmods, strict=True):
        result = normalize_discovered_url(loc, retain_query=True)
        if not result.is_valid or result.normalized_url is None:
            continue
        host = extract_hostname(result.normalized_url)
        if not is_same_registrable_domain(host, root_domain):
            continue
        valid.append(
            SitemapUrlEntry(loc=loc, normalized_url=result.normalized_url, lastmod=lastmod)
        )
        if _looks_like_product_url(result.normalized_url):
            product_like_count += 1

    total = len(valid)
    is_product_sitemap = total > 0 and (product_like_count / total) >= 0.5

    if total > config.large_sitemap_threshold:
        sample_size = (
            config.sitemap_sample_size if is_product_sitemap else config.large_sitemap_threshold
        )
        sampled = valid[:sample_size]
        if is_product_sitemap:
            warnings.append(f"product sitemap detected with {total} URLs; sampled {len(sampled)}")
        else:
            warnings.append(f"large sitemap with {total} URLs; truncated to {len(sampled)}")
        return sampled, total, is_product_sitemap, warnings

    return valid, total, is_product_sitemap, warnings


def parse_sitemap_document(
    raw: bytes,
    *,
    content_type: str | None,
    source_sitemap_url: str,
    root_domain: str,
    config: DiscoveryConfig,
) -> SitemapParseResult:
    """Parses one already-fetched sitemap document's raw bytes."""
    data = _maybe_decompress(
        raw,
        content_type=content_type,
        source_url=source_sitemap_url,
        max_size=config.max_response_size_bytes,
    )
    if data is None:
        return SitemapParseResult(
            is_index=False,
            url_entries=[],
            nested_sitemap_urls=[],
            total_url_count=0,
            product_sitemap_detected=False,
            warnings=[
                "failed to decompress gzip sitemap, or decompressed payload exceeded the size limit"
            ],
            format="unknown",
        )

    stripped = data.lstrip()
    looks_xml = stripped.startswith(b"<") or (
        content_type is not None and "xml" in content_type.lower()
    )

    if not looks_xml:
        text = data.decode("utf-8", errors="replace")
        raw_locs = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        url_entries, total, product_flag, warnings = _build_url_entries(
            raw_locs, [None] * len(raw_locs), root_domain=root_domain, config=config
        )
        return SitemapParseResult(
            is_index=False,
            url_entries=url_entries,
            nested_sitemap_urls=[],
            total_url_count=total,
            product_sitemap_detected=product_flag,
            warnings=warnings,
            format="plain_text",
        )

    outcome = _parse_xml(data, max_elements=config.max_xml_elements_per_document)
    if outcome.malformed_reason is not None:
        return SitemapParseResult(
            is_index=False,
            url_entries=[],
            nested_sitemap_urls=[],
            total_url_count=0,
            product_sitemap_detected=False,
            warnings=[f"malformed XML sitemap: {outcome.malformed_reason}"],
            format="unknown",
        )

    warnings: list[str] = []
    if outcome.element_limit_exceeded:
        warnings.append(
            f"sitemap exceeded the maximum element count "
            f"({config.max_xml_elements_per_document}); partial results only"
        )

    if outcome.sitemap_entries and outcome.url_entries:
        warnings.append(
            "sitemap document contains both <sitemap> and <url> entries; treating as an index"
        )
        is_index = True
    elif outcome.sitemap_entries:
        is_index = True
    elif outcome.url_entries:
        is_index = False
    else:
        is_index = "index" in (outcome.root_tag or "").lower()
        if not is_index:
            warnings.append("sitemap document had no recognizable <url> or <sitemap> entries")

    if is_index:
        nested: list[str] = []
        for loc in outcome.sitemap_entries:
            result = normalize_discovered_url(loc, retain_query=True)
            if not result.is_valid or result.normalized_url is None:
                warnings.append(f"skipped invalid nested sitemap URL: {loc!r}")
                continue
            host = extract_hostname(result.normalized_url)
            if not is_same_registrable_domain(host, root_domain):
                warnings.append(f"skipped off-domain nested sitemap: {loc!r}")
                continue
            nested.append(result.normalized_url)
        return SitemapParseResult(
            is_index=True,
            url_entries=[],
            nested_sitemap_urls=nested,
            total_url_count=0,
            product_sitemap_detected=False,
            warnings=warnings,
            format="xml_index",
        )

    raw_locs = [loc for loc, _lastmod in outcome.url_entries]
    lastmods = [lastmod for _loc, lastmod in outcome.url_entries]
    url_entries, total, product_flag, sample_warnings = _build_url_entries(
        raw_locs, lastmods, root_domain=root_domain, config=config
    )
    warnings.extend(sample_warnings)
    return SitemapParseResult(
        is_index=False,
        url_entries=url_entries,
        nested_sitemap_urls=[],
        total_url_count=total,
        product_sitemap_detected=product_flag,
        warnings=warnings,
        format="xml",
    )
