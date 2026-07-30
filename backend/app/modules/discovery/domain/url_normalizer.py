"""Deterministic URL normalization for discovered links.

Pure, stdlib-only (`urllib.parse`, `ipaddress`) — no new dependency, no
FastAPI/MongoDB import, no DNS lookups (SSRF/DNS-rebinding validation at
request time belongs in `infrastructure/httpx_discovery_client.py`, not
here). A separate, self-contained implementation from
`modules/imports/domain/website_normalizer.py` — different requirements
(relative-URL resolution, query-string handling, port-default stripping,
path-slash collapsing). Notably, unlike the imports normalizer, this one
does **not** strip a leading `www.` — the task asks discovery to
"preserve meaningful subdomains" without singling out `www`, and
homepage resolution already tries the `www`/non-`www` candidates as
distinct URLs.
"""

import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit

from app.modules.discovery.domain.models import UrlValidationResult

_ALLOWED_SCHEMES = frozenset({"http", "https"})
_DISALLOWED_SCHEME_PREFIXES = (
    "javascript:",
    "mailto:",
    "tel:",
    "data:",
    "file:",
    "ftp:",
)

_TRACKING_PARAMS = frozenset(
    {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid"}
)

_DEFAULT_PORTS = {"http": 80, "https": 443}

_RESERVED_SUFFIXES = frozenset(
    {"local", "internal", "localdomain", "lan", "home", "test", "invalid", "example"}
)

_LABEL_PATTERN = re.compile(r"^(?!-)[a-zA-Z0-9-]{1,63}(?<!-)$")
_MAX_HOSTNAME_LENGTH = 253
_REPEATED_SLASHES = re.compile(r"/{2,}")


def _reject(reason: str) -> UrlValidationResult:
    return UrlValidationResult(is_valid=False, rejection_reason=reason)


def _is_ip_address(hostname: str) -> bool:
    import ipaddress

    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return True


def _is_private_or_reserved_ip(hostname: str) -> bool:
    import ipaddress

    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def _normalize_label(label: str) -> str | None:
    if label.isascii():
        return label if _LABEL_PATTERN.match(label) else None
    try:
        encoded = label.encode("idna").decode("ascii")
    except UnicodeError:
        return None
    return encoded if _LABEL_PATTERN.match(encoded) else None


def extract_hostname(normalized_url: str) -> str | None:
    """Returns the lowercase hostname of an already-normalized URL, or `None`."""
    return urlsplit(normalized_url).hostname


def normalize_discovered_url(
    raw: str,
    *,
    source_page_url: str | None = None,
    retain_query: bool = False,
) -> UrlValidationResult:
    """Normalizes a raw href into a canonical absolute URL.

    `source_page_url`, when given, resolves a relative `raw` href against
    it (`urljoin`). `retain_query=True` keeps a sorted, tracking-
    parameter-stripped query string — callers pass this for sitemap URLs,
    where query variants are sometimes meaningful; homepage/navigation
    links normalize with the query dropped entirely by default, per the
    task's "preserve query strings only when explicitly allowed."
    """
    value = raw.strip()
    if not value:
        return _reject("empty URL")

    lowered = value.lower()
    for prefix in _DISALLOWED_SCHEME_PREFIXES:
        if lowered.startswith(prefix):
            return _reject(f"disallowed scheme: {prefix.rstrip(':')}")

    resolved = urljoin(source_page_url, value) if source_page_url else value

    try:
        parts = urlsplit(resolved)
    except ValueError:
        return _reject("malformed URL")

    scheme = parts.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        return _reject(f"unsupported scheme: {scheme or '(none)'}")

    if parts.username is not None or parts.password is not None:
        return _reject("credentials in URL are not allowed")

    hostname = parts.hostname
    if not hostname:
        return _reject("malformed URL: missing host")
    hostname = hostname.rstrip(".")
    if not hostname:
        return _reject("malformed URL: missing host")

    if hostname == "localhost" or hostname.endswith(".localhost"):
        return _reject("localhost is not allowed")

    if _is_ip_address(hostname):
        if _is_private_or_reserved_ip(hostname):
            return _reject("private/internal IP addresses are not allowed")
        return _reject("IP address literals are not allowed")

    if len(hostname) > _MAX_HOSTNAME_LENGTH:
        return _reject("malformed URL: host too long")

    labels = hostname.split(".")
    if len(labels) < 2:
        return _reject("malformed URL: host has no domain suffix")
    if labels[-1] in _RESERVED_SUFFIXES:
        return _reject("private/internal hostnames are not allowed")

    encoded_labels: list[str] = []
    for label in labels:
        encoded = _normalize_label(label)
        if encoded is None:
            return _reject("malformed URL: invalid host label")
        encoded_labels.append(encoded)
    hostname = ".".join(encoded_labels)

    port = parts.port  # urlsplit raises ValueError on a malformed port, caught above
    default_port = _DEFAULT_PORTS.get(scheme)
    include_port = port is not None and port != default_port
    authority = f"{hostname}:{port}" if include_port else hostname

    path = _REPEATED_SLASHES.sub("/", parts.path) or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/") or "/"

    query = ""
    if retain_query and parts.query:
        pairs = [
            (key, val)
            for key, val in parse_qsl(parts.query, keep_blank_values=True)
            if key.lower() not in _TRACKING_PARAMS
        ]
        pairs.sort(key=lambda pair: (pair[0], pair[1]))
        query = urlencode(pairs)

    normalized = f"{scheme}://{authority}{path}"
    if query:
        normalized += f"?{query}"

    return UrlValidationResult(is_valid=True, normalized_url=normalized)
