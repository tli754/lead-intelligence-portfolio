"""Website/URL normalization for imported rows.

Pure, stdlib-only (`urllib.parse`, `ipaddress`) — no new dependency, no
FastAPI/MongoDB import. Deliberately stricter than
`app/modules/companies/domain/normalization.py`'s `normalize_domain`
(which only strips scheme/www/path and lowercases): this one also
rejects localhost, IP literals, malformed hosts, and private/internal
hostnames, and IDNA-encodes non-ASCII labels — requirements specific to
validating third-party import data, not the paste-in importer's own
already-curated input.
"""

import ipaddress
import re
from urllib.parse import urlsplit

_RESERVED_SUFFIXES = frozenset(
    {
        "local",
        "internal",
        "localdomain",
        "lan",
        "home",
        # IANA special-use / reserved TLDs (RFC 2606), unlikely to be a
        # real public storefront but plausible test/placeholder data.
        "test",
        "invalid",
        "example",
    }
)

_LABEL_PATTERN = re.compile(r"^(?!-)[a-zA-Z0-9-]{1,63}(?<!-)$")
_MAX_HOSTNAME_LENGTH = 253


class WebsiteNormalizationError(Exception):
    """Raised when a raw website value doesn't resolve to a usable public hostname."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def normalize_website(raw: str) -> str:
    """Normalizes a raw website/domain value into a bare lowercase hostname.

    Accepts full URLs (with or without scheme), bare domains, and
    domains with a path/query/fragment/port. Raises
    `WebsiteNormalizationError` if the value doesn't resolve to a usable,
    public hostname.
    """
    value = raw.strip()
    if not value:
        raise WebsiteNormalizationError("empty website value")

    if "://" not in value:
        value = f"http://{value}"

    hostname = urlsplit(value).hostname  # lowercased and port-stripped by urlsplit
    if not hostname:
        raise WebsiteNormalizationError("malformed host")

    hostname = hostname.rstrip(".")
    if not hostname:
        raise WebsiteNormalizationError("malformed host")

    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise WebsiteNormalizationError("localhost is not allowed")

    if _is_ip_address(hostname):
        raise WebsiteNormalizationError("IP addresses are not allowed")

    if len(hostname) > _MAX_HOSTNAME_LENGTH:
        raise WebsiteNormalizationError("malformed host")

    labels = hostname.split(".")
    if len(labels) < 2 or labels[-1] in _RESERVED_SUFFIXES:
        raise WebsiteNormalizationError("private/internal hostnames are not allowed")

    encoded_labels = [_normalize_label(label) for label in labels]

    if encoded_labels[0] == "www":
        encoded_labels = encoded_labels[1:]
        if not encoded_labels:
            raise WebsiteNormalizationError("malformed host")

    return ".".join(encoded_labels)


def _is_ip_address(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return True


def _normalize_label(label: str) -> str:
    """Validates one hostname label, IDNA-encoding it only if it's non-ASCII."""
    if label.isascii():
        if not _LABEL_PATTERN.match(label):
            raise WebsiteNormalizationError("malformed host")
        return label

    try:
        encoded = label.encode("idna").decode("ascii")
    except UnicodeError as error:
        raise WebsiteNormalizationError("malformed host") from error
    if not _LABEL_PATTERN.match(encoded):
        raise WebsiteNormalizationError("malformed host")
    return encoded
