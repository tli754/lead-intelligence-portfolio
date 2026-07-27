"""Pure domain-normalization logic, shared by validation and lookups.

No FastAPI or MongoDB imports — a deterministic string transformation
only, which keeps it trivially unit-testable.
"""

import re

_SCHEME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


def normalize_domain(raw_domain: str) -> str:
    """Normalize a raw domain or URL into a bare lowercase hostname.

    Strips a leading scheme (e.g. `https://`), any path/query/fragment,
    a leading `www.`, a trailing dot, and lowercases the result. Raises
    `ValueError` if nothing is left after normalization.
    """
    value = raw_domain.strip().lower()
    value = _SCHEME_PATTERN.sub("", value)
    value = value.split("/", 1)[0]
    value = value.split("?", 1)[0]
    value = value.split("#", 1)[0]
    value = value.split(":", 1)[0]
    if value.startswith("www."):
        value = value[len("www.") :]
    value = value.rstrip(".")

    if not value:
        raise ValueError("normalized_domain must not be empty")
    return value
