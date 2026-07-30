"""Deterministic page-type classification.

No AI classification (per the task) — a versioned, hand-authored rule
table matched against the normalized path/filename, with anchor text as
a weaker corroborating (or conflicting) secondary signal. "Common
multilingual English patterns where practical" is interpreted narrowly
here: the rule table already covers several common English synonyms per
page type (see each list below); true multi-language support is a known
limitation, not attempted.
"""

import re

from app.modules.discovery.domain.enums import PageType
from app.modules.discovery.domain.models import ClassificationResult

CLASSIFICATION_RULES_VERSION = "v1"

_EXTENSION_SUFFIX = re.compile(r"\.(html?|php|aspx?|jsp)$", re.IGNORECASE)

# Ordered (page_type, rule_name, patterns) — order is the tie-break when
# multiple path patterns could otherwise match, keeping results
# deterministic. Each pattern's *last path segment* is what's actually
# compared (see `_last_segment`), so "/pages/about-us" matches the
# "/about-us" pattern just as "/about-us" does.
_PATH_RULES: list[tuple[PageType, str, tuple[str, ...]]] = [
    (PageType.ABOUT, "about", ("/about", "/about-us", "/our-story")),
    (PageType.CONTACT, "contact", ("/contact", "/contact-us", "/get-in-touch")),
    (PageType.WHOLESALE, "wholesale", ("/wholesale", "/wholesale-enquiries", "/become-a-stockist")),
    (PageType.TRADE, "trade", ("/trade", "/trade-account", "/trade-application")),
    (PageType.CAREERS, "careers", ("/careers", "/jobs", "/work-with-us")),
    (PageType.SHIPPING, "shipping", ("/shipping", "/delivery", "/shipping-information")),
    (
        PageType.CLICK_AND_COLLECT,
        "click_and_collect",
        ("/click-and-collect", "/pickup", "/store-pickup"),
    ),
    (
        PageType.STORE_LOCATOR,
        "store_locator",
        ("/stores", "/store-locator", "/locations", "/our-stores"),
    ),
    (PageType.RETURNS, "returns", ("/returns", "/refund-policy", "/returns-and-exchanges")),
    (PageType.FAQ, "faq", ("/faq", "/faqs", "/frequently-asked-questions")),
    (PageType.SUPPORT, "support", ("/support", "/help", "/help-centre")),
    (PageType.BLOG, "blog", ("/blog", "/journal", "/articles")),
    (PageType.NEWS, "news", ("/news", "/press", "/media")),
    (PageType.TEAM, "team", ("/team", "/our-team", "/people")),
    (PageType.BRANDS, "brands", ("/brands", "/our-brands")),
    (PageType.SUBSCRIPTION, "subscription", ("/subscription", "/subscribe")),
    (PageType.PRIVACY, "privacy", ("/privacy", "/privacy-policy")),
    (PageType.TERMS, "terms", ("/terms", "/terms-and-conditions")),
    (PageType.ACCOUNT, "account", ("/account", "/my-account", "/login", "/sign-in", "/register")),
    (PageType.CART, "cart", ("/cart", "/basket")),
    (PageType.CHECKOUT, "checkout", ("/checkout",)),
    (PageType.SEARCH, "search", ("/search",)),
]

# Prefix-based (anything *under* the path), not slug-based — product/
# collection/category listings are namespaced, not single pages.
_PREFIX_RULES: list[tuple[PageType, str, tuple[str, ...]]] = [
    (PageType.PRODUCT, "product_prefix", ("/products/", "/product/")),
    (PageType.COLLECTION, "collection_prefix", ("/collections/",)),
    (PageType.CATEGORY, "category_prefix", ("/category/", "/categories/")),
]

_ANCHOR_KEYWORDS: list[tuple[PageType, str, frozenset[str]]] = [
    (PageType.ABOUT, "about", frozenset({"about", "about us", "our story"})),
    (PageType.CONTACT, "contact", frozenset({"contact", "contact us", "get in touch"})),
    (PageType.WHOLESALE, "wholesale", frozenset({"wholesale", "become a stockist"})),
    (PageType.TRADE, "trade", frozenset({"trade account", "trade"})),
    (PageType.CAREERS, "careers", frozenset({"careers", "jobs", "work with us"})),
    (PageType.SHIPPING, "shipping", frozenset({"shipping", "delivery"})),
    (
        PageType.CLICK_AND_COLLECT,
        "click_and_collect",
        frozenset({"click and collect", "click & collect", "store pickup", "pickup"}),
    ),
    (
        PageType.STORE_LOCATOR,
        "store_locator",
        frozenset({"stores", "store locator", "locations", "find a store"}),
    ),
    (PageType.RETURNS, "returns", frozenset({"returns", "refund policy", "returns and exchanges"})),
    (PageType.FAQ, "faq", frozenset({"faq", "faqs", "frequently asked questions"})),
    (PageType.SUPPORT, "support", frozenset({"support", "help"})),
    (PageType.BLOG, "blog", frozenset({"blog", "journal", "articles"})),
    (PageType.NEWS, "news", frozenset({"news", "press", "media"})),
    (PageType.TEAM, "team", frozenset({"team", "our team", "people"})),
    (PageType.BRANDS, "brands", frozenset({"brands", "our brands"})),
    (PageType.SUBSCRIPTION, "subscription", frozenset({"subscription", "subscribe"})),
    (PageType.PRIVACY, "privacy", frozenset({"privacy", "privacy policy"})),
    (PageType.TERMS, "terms", frozenset({"terms", "terms and conditions", "terms of service"})),
    (PageType.ACCOUNT, "account", frozenset({"account", "sign in", "log in", "login", "register"})),
    (PageType.CART, "cart", frozenset({"cart", "basket"})),
    (PageType.CHECKOUT, "checkout", frozenset({"checkout"})),
    (PageType.SEARCH, "search", frozenset({"search"})),
]

_PATTERN_LAST_SEGMENTS: dict[tuple[str, str], str] = {
    (rule_name, pattern): pattern.rstrip("/").rsplit("/", 1)[-1]
    for _page_type, rule_name, patterns in _PATH_RULES
    for pattern in patterns
}


def _last_segment(path: str) -> str:
    segment = path.rstrip("/").rsplit("/", 1)[-1]
    return _EXTENSION_SUFFIX.sub("", segment)


def _match_path_rules(path: str) -> ClassificationResult | None:
    segment = _last_segment(path)
    if not segment:
        return None
    for page_type, rule_name, patterns in _PATH_RULES:
        for pattern in patterns:
            if _PATTERN_LAST_SEGMENTS[(rule_name, pattern)] == segment:
                return ClassificationResult(
                    page_type=page_type, confidence=95, rule_id=f"path:{rule_name}:{pattern}"
                )
    return None


def _match_prefix_rules(path: str) -> ClassificationResult | None:
    for page_type, rule_name, patterns in _PREFIX_RULES:
        for pattern in patterns:
            if path.startswith(pattern):
                return ClassificationResult(
                    page_type=page_type, confidence=90, rule_id=f"prefix:{rule_name}:{pattern}"
                )
    return None


def _match_anchor_rules(anchor_texts: list[str]) -> list[ClassificationResult]:
    lowered_texts = [text.lower() for text in anchor_texts if text]
    matches: list[ClassificationResult] = []
    for page_type, rule_name, keywords in _ANCHOR_KEYWORDS:
        hits = [text for text in lowered_texts if any(keyword in text for keyword in keywords)]
        if hits:
            confidence = min(60, 45 + 5 * (len(hits) - 1))
            matches.append(
                ClassificationResult(
                    page_type=page_type, confidence=confidence, rule_id=f"anchor:{rule_name}"
                )
            )
    return matches


def classify_page_type(
    *,
    normalized_path: str,
    anchor_texts: list[str] | None = None,
    sitemap_context: str | None = None,
) -> ClassificationResult:
    """Classifies one URL's page type.

    `sitemap_context` is an optional hint from the sitemap parser (e.g.
    `"product"` when the URL came from a sitemap flagged as a product
    sitemap) — used only as a weak fallback signal when nothing stronger
    matched.
    """
    anchor_texts = anchor_texts or []
    path = normalized_path.lower()

    if path in ("", "/"):
        return ClassificationResult(
            page_type=PageType.HOMEPAGE, confidence=100, rule_id="path:homepage:/"
        )

    winner = _match_path_rules(path) or _match_prefix_rules(path)
    anchor_matches = _match_anchor_rules(anchor_texts)

    if winner is not None:
        alternates = [match for match in anchor_matches if match.page_type != winner.page_type]
        return winner.model_copy(update={"alternates": alternates})

    if anchor_matches:
        winner = max(anchor_matches, key=lambda match: match.confidence)
        alternates = [match for match in anchor_matches if match is not winner]
        return winner.model_copy(update={"alternates": alternates})

    if sitemap_context == "product":
        return ClassificationResult(
            page_type=PageType.PRODUCT, confidence=70, rule_id="sitemap_context:product"
        )

    return ClassificationResult(page_type=PageType.UNKNOWN, confidence=0, rule_id="unmatched")
