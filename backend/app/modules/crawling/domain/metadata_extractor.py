"""Deterministic page-metadata and technology-signal extraction.

Operates on already-*cleaned* HTML (never raw) — `domain/html_cleaner.py`
deliberately keeps every `<script src="...">`'s tag/attribute intact
(only its body is stripped) precisely so this file can still see script
source hosts as technology signals. Stdlib-only (`html.parser.HTMLParser`).

Every signal collected here goes only into `PageMetadata.technology_signals`
— this function never writes to any company-facing model (section 9's
explicit "do not update the company technology profile in this task").
"""

import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

from app.modules.crawling.domain.html_cleaner import CLEANING_RULES_VERSION
from app.modules.crawling.domain.models import PageMetadata
from app.modules.crawling.domain.text_extractor import TEXT_EXTRACTION_RULES_VERSION

_WHITESPACE_RUN = re.compile(r"\s+")

# attribute name -> framework label, checked against every tag's attributes.
_FRAMEWORK_ATTR_MARKERS: dict[str, str] = {
    "data-reactroot": "react",
    "v-cloak": "vue",
    "ng-app": "angular",
}

# element/script `id` value -> framework label.
_FRAMEWORK_ID_MARKERS: dict[str, str] = {
    "__next": "nextjs",
    "__next_data__": "nextjs",
    "___gatsby": "gatsby",
}

# substring of a script `src` -> commerce-platform label.
_COMMERCE_HOST_MARKERS: dict[str, str] = {
    "cdn.shopify.com": "shopify",
    "shopifycdn.com": "shopify",
}

# substring of the `generator` meta tag's value (lowercased) -> commerce-platform label.
_COMMERCE_GENERATOR_MARKERS: dict[str, str] = {
    "shopify": "shopify",
    "woocommerce": "woocommerce",
    "wordpress": "wordpress",
    "magento": "magento",
    "bigcommerce": "bigcommerce",
}

# substring of a script `src` -> analytics-tool label.
_ANALYTICS_HOST_MARKERS: dict[str, str] = {
    "google-analytics.com": "google-analytics",
    "googletagmanager.com": "google-tag-manager",
    "doubleclick.net": "doubleclick",
    "connect.facebook.net": "facebook-pixel",
    "hotjar.com": "hotjar",
    "segment.com": "segment",
    "mixpanel.com": "mixpanel",
}

# substring of a script `src` -> support-widget label.
_SUPPORT_WIDGET_HOST_MARKERS: dict[str, str] = {
    "intercom.io": "intercom",
    "zendesk.com": "zendesk",
    "drift.com": "drift",
    "tawk.to": "tawk-to",
    "crisp.chat": "crisp",
}


class _MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: str | None = None
        self.meta_description: str | None = None
        self.canonical_url: str | None = None
        self.language: str | None = None
        self.robots_meta: str | None = None
        self.og_site_name: str | None = None
        self.og_title: str | None = None
        self.generator: str | None = None
        self.link_count = 0
        self.script_count = 0
        self.stylesheet_count = 0
        self.script_source_hosts: list[str] = []
        self.framework_markers: set[str] = set()
        self.commerce_platform_markers: set[str] = set()
        self.analytics_markers: set[str] = set()
        self.support_widget_markers: set[str] = set()

        self._in_title = False
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        self._record_framework_markers(attrs_dict)

        if tag == "html":
            lang = attrs_dict.get("lang")
            if lang:
                self.language = lang
        elif tag == "meta":
            self._record_meta_tag(attrs_dict)
        elif tag == "link":
            self._record_link_tag(attrs_dict)
        elif tag == "a":
            if attrs_dict.get("href"):
                self.link_count += 1
        elif tag == "script":
            self._record_script_tag(attrs_dict)
        elif tag == "title":
            self._in_title = True
            self._title_parts = []

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
            collapsed = _WHITESPACE_RUN.sub(" ", "".join(self._title_parts)).strip()
            self.title = collapsed or None

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)

    def _record_framework_markers(self, attrs: dict[str, str | None]) -> None:
        for attr_name, label in _FRAMEWORK_ATTR_MARKERS.items():
            if attr_name in attrs:
                self.framework_markers.add(label)
        element_id = (attrs.get("id") or "").lower()
        if element_id in _FRAMEWORK_ID_MARKERS:
            self.framework_markers.add(_FRAMEWORK_ID_MARKERS[element_id])

    def _record_meta_tag(self, attrs: dict[str, str | None]) -> None:
        name = (attrs.get("name") or "").lower()
        prop = (attrs.get("property") or "").lower()
        content = attrs.get("content")

        if name == "description":
            self.meta_description = content
        elif name == "robots":
            self.robots_meta = content
        elif name == "generator":
            self.generator = content
        elif prop == "og:site_name":
            self.og_site_name = content
        elif prop == "og:title":
            self.og_title = content

    def _record_link_tag(self, attrs: dict[str, str | None]) -> None:
        rel = (attrs.get("rel") or "").lower()
        href = attrs.get("href")
        if rel == "canonical" and href:
            self.canonical_url = href
        elif rel == "stylesheet":
            self.stylesheet_count += 1

    def _record_script_tag(self, attrs: dict[str, str | None]) -> None:
        self.script_count += 1
        src = attrs.get("src")
        if not src:
            return

        host = urlsplit(src).hostname
        if host:
            self.script_source_hosts.append(host)

        for marker, label in _COMMERCE_HOST_MARKERS.items():
            if marker in src:
                self.commerce_platform_markers.add(label)
        for marker, label in _ANALYTICS_HOST_MARKERS.items():
            if marker in src:
                self.analytics_markers.add(label)
        for marker, label in _SUPPORT_WIDGET_HOST_MARKERS.items():
            if marker in src:
                self.support_widget_markers.add(label)


def extract_page_metadata(
    cleaned_html: str,
    *,
    raw_html_size: int,
    cleaned_html_size: int,
    extracted_text_length: int,
) -> PageMetadata:
    """Extracts deterministic page metadata and technology signals from
    already-cleaned HTML. Never touches any company-facing model."""
    parser = _MetadataParser()
    parser.feed(cleaned_html)
    parser.close()

    commerce_markers = set(parser.commerce_platform_markers)
    if parser.generator:
        lowered_generator = parser.generator.lower()
        for marker, label in _COMMERCE_GENERATOR_MARKERS.items():
            if marker in lowered_generator:
                commerce_markers.add(label)

    technology_signals = {
        "script_source_hosts": sorted(set(parser.script_source_hosts)),
        "generator": parser.generator,
        "framework_markers": sorted(parser.framework_markers),
        "commerce_platform_markers": sorted(commerce_markers),
        "analytics_markers": sorted(parser.analytics_markers),
        "support_widget_markers": sorted(parser.support_widget_markers),
    }

    return PageMetadata(
        title=parser.title,
        meta_description=parser.meta_description,
        canonical_url=parser.canonical_url,
        language=parser.language,
        robots_meta=parser.robots_meta,
        og_site_name=parser.og_site_name,
        og_title=parser.og_title,
        generator=parser.generator,
        html_size_bytes=raw_html_size,
        cleaned_html_size_bytes=cleaned_html_size,
        extracted_text_length=extracted_text_length,
        link_count=parser.link_count,
        script_count=parser.script_count,
        stylesheet_count=parser.stylesheet_count,
        technology_signals=technology_signals,
        cleaning_rules_version=CLEANING_RULES_VERSION,
        text_extraction_rules_version=TEXT_EXTRACTION_RULES_VERSION,
    )
