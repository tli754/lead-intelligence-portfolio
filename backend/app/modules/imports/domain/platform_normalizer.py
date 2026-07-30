"""Platform value normalization. Pure — no FastAPI or MongoDB imports.

Deliberately does not infer a platform from the website/domain — only
normalizes whatever the `platform` column already says.
"""

_KNOWN_PLATFORMS = frozenset(
    {"shopify", "woocommerce", "magento", "custom", "prestashop", "opencart"}
)


def normalize_platform(raw: str | None) -> str | None:
    """Normalizes a raw platform value, or `None` if unknown/blank."""
    if raw is None:
        return None
    value = raw.strip().lower()
    if value in _KNOWN_PLATFORMS:
        return value
    return None
