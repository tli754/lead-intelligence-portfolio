"""Priority assignment for discovered URLs.

The default page-type-to-priority map is a single table, not scattered
conditionals — callers override it via `DiscoveryConfig.priority_overrides`
rather than editing this file, per the task's "allow priority overrides
through configuration rather than hardcoding them throughout the
application."
"""

from app.modules.discovery.domain.config import DiscoveryConfig
from app.modules.discovery.domain.enums import DiscoveryPriority, PageType

DEFAULT_PRIORITY_MAP: dict[PageType, DiscoveryPriority] = {
    # Tier 1.
    PageType.HOMEPAGE: DiscoveryPriority.PRIORITY_1,
    PageType.ABOUT: DiscoveryPriority.PRIORITY_1,
    PageType.CONTACT: DiscoveryPriority.PRIORITY_1,
    PageType.WHOLESALE: DiscoveryPriority.PRIORITY_1,
    PageType.TRADE: DiscoveryPriority.PRIORITY_1,
    PageType.CAREERS: DiscoveryPriority.PRIORITY_1,
    PageType.SHIPPING: DiscoveryPriority.PRIORITY_1,
    PageType.CLICK_AND_COLLECT: DiscoveryPriority.PRIORITY_1,
    PageType.STORE_LOCATOR: DiscoveryPriority.PRIORITY_1,
    # Tier 2.
    PageType.RETURNS: DiscoveryPriority.PRIORITY_2,
    PageType.FAQ: DiscoveryPriority.PRIORITY_2,
    PageType.SUPPORT: DiscoveryPriority.PRIORITY_2,
    PageType.BLOG: DiscoveryPriority.PRIORITY_2,
    PageType.NEWS: DiscoveryPriority.PRIORITY_2,
    PageType.TEAM: DiscoveryPriority.PRIORITY_2,
    PageType.BRANDS: DiscoveryPriority.PRIORITY_2,
    PageType.SUBSCRIPTION: DiscoveryPriority.PRIORITY_2,
    # Tier 3.
    PageType.PRODUCT: DiscoveryPriority.PRIORITY_3,
    PageType.COLLECTION: DiscoveryPriority.PRIORITY_3,
    PageType.CATEGORY: DiscoveryPriority.PRIORITY_3,
    PageType.PRIVACY: DiscoveryPriority.PRIORITY_3,
    PageType.TERMS: DiscoveryPriority.PRIORITY_3,
    PageType.UNKNOWN: DiscoveryPriority.PRIORITY_3,
    # Excluded.
    PageType.ACCOUNT: DiscoveryPriority.EXCLUDED,
    PageType.CART: DiscoveryPriority.EXCLUDED,
    PageType.CHECKOUT: DiscoveryPriority.EXCLUDED,
    PageType.SEARCH: DiscoveryPriority.EXCLUDED,
}

# Checked against the URL's path suffix before page-type classification
# even applies — an image/script/font URL is excluded regardless of what
# page type it might otherwise resemble.
EXCLUDED_EXTENSIONS = frozenset(
    {
        # Images.
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".svg",
        ".webp",
        ".ico",
        ".bmp",
        ".tiff",
        # Video.
        ".mp4",
        ".mov",
        ".avi",
        ".webm",
        ".mkv",
        # Fonts.
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
        ".eot",
        # Stylesheets / scripts.
        ".css",
        ".js",
        ".mjs",
        # Downloadable binaries — deliberately narrow: archives/executables
        # are excluded, but NOT .pdf/.doc/.docx, since a document (e.g. a
        # wholesale terms sheet) may be "specifically useful later" per
        # the task, unlike an installer or archive.
        ".zip",
        ".rar",
        ".tar",
        ".gz",
        ".exe",
        ".dmg",
        ".apk",
        ".msi",
    }
)


def has_excluded_extension(normalized_url: str) -> bool:
    path = normalized_url.split("?", 1)[0].split("#", 1)[0].lower()
    return any(path.endswith(extension) for extension in EXCLUDED_EXTENSIONS)


def assign_priority(
    *,
    page_type: PageType,
    normalized_url: str,
    is_same_domain: bool,
    config: DiscoveryConfig,
) -> DiscoveryPriority:
    """Assigns a priority, checking (in order): off-domain, excluded file
    extension, configured override, then the default map."""
    if not is_same_domain:
        return DiscoveryPriority.EXCLUDED
    if has_excluded_extension(normalized_url):
        return DiscoveryPriority.EXCLUDED
    if page_type in config.priority_overrides:
        return config.priority_overrides[page_type]
    return DEFAULT_PRIORITY_MAP.get(page_type, DiscoveryPriority.PRIORITY_3)
