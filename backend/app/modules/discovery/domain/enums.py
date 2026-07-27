"""Enumerations for the discovery module. Pure Python — no FastAPI or MongoDB imports."""

from enum import StrEnum


class DiscoveryStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"


class DiscoverySource(StrEnum):
    HOMEPAGE = "homepage"
    NAVIGATION = "navigation"
    FOOTER = "footer"
    BODY_LINK = "body_link"
    ROBOTS = "robots"
    SITEMAP = "sitemap"
    SITEMAP_INDEX = "sitemap_index"
    CANONICAL = "canonical"
    ALTERNATE = "alternate"
    REDIRECT = "redirect"


class PageType(StrEnum):
    HOMEPAGE = "homepage"
    ABOUT = "about"
    CONTACT = "contact"
    WHOLESALE = "wholesale"
    TRADE = "trade"
    CAREERS = "careers"
    SHIPPING = "shipping"
    CLICK_AND_COLLECT = "click_and_collect"
    STORE_LOCATOR = "store_locator"
    RETURNS = "returns"
    FAQ = "faq"
    SUPPORT = "support"
    BLOG = "blog"
    NEWS = "news"
    TEAM = "team"
    BRANDS = "brands"
    SUBSCRIPTION = "subscription"
    PRODUCT = "product"
    COLLECTION = "collection"
    CATEGORY = "category"
    PRIVACY = "privacy"
    TERMS = "terms"
    ACCOUNT = "account"
    CART = "cart"
    CHECKOUT = "checkout"
    SEARCH = "search"
    UNKNOWN = "unknown"


class DiscoveryPriority(StrEnum):
    """Bare `1`/`2`/`3`/`excluded` per the task spec, as string enum members
    (JSON/Pydantic enum members must be strings; the *values* are still the
    literal digit strings `"1"`/`"2"`/`"3"`)."""

    PRIORITY_1 = "1"
    PRIORITY_2 = "2"
    PRIORITY_3 = "3"
    EXCLUDED = "excluded"
