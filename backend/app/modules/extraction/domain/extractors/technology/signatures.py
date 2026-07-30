"""Centralized, versioned technology-signature rules (brief section 9).

Every technology is backed by one or more `rule_id`s — a page with no
matching signature for a given technology simply produces no candidate
for it (never a `false`/negative fact). Generic CDN hosts are
deliberately never listed here (they would prove nothing about a specific
product), and framework signatures are kept in their own family, never
folded into a commerce-platform/CRM signature (brief's explicit "framework
detection must not be treated as internal technical capability").
"""

from dataclasses import dataclass, field

from app.modules.evidence.domain.enums import EvidenceStrength
from app.modules.extraction.domain.field_catalogue import FieldPath

TECHNOLOGY_SIGNATURES_VERSION = "v1"


@dataclass(frozen=True)
class TechnologySignature:
    technology: str
    field_path: FieldPath
    rule_id: str
    host_markers: tuple[str, ...] = field(default_factory=tuple)
    generator_markers: tuple[str, ...] = field(default_factory=tuple)
    html_markers: tuple[str, ...] = field(default_factory=tuple)
    base_confidence: int = 75
    evidence_strength: EvidenceStrength = EvidenceStrength.STRONG
    notes: str = ""


def _sig(
    technology: str,
    field_path: FieldPath,
    rule_suffix: str,
    *,
    host_markers: tuple[str, ...] = (),
    generator_markers: tuple[str, ...] = (),
    html_markers: tuple[str, ...] = (),
    base_confidence: int = 75,
) -> TechnologySignature:
    return TechnologySignature(
        technology=technology,
        field_path=field_path,
        rule_id=f"technology.{field_path.value.split('.')[1]}.{rule_suffix}",
        host_markers=host_markers,
        generator_markers=generator_markers,
        html_markers=html_markers,
        base_confidence=base_confidence,
    )


TECHNOLOGY_SIGNATURES: tuple[TechnologySignature, ...] = (
    # --- Commerce ---------------------------------------------------------
    _sig(
        "shopify",
        FieldPath.TECHNOLOGY_COMMERCE_PLATFORM,
        "shopify",
        host_markers=("cdn.shopify.com", "shopifycdn.com"),
        generator_markers=("shopify",),
        base_confidence=85,
    ),
    _sig(
        "woocommerce",
        FieldPath.TECHNOLOGY_COMMERCE_PLATFORM,
        "woocommerce",
        generator_markers=("woocommerce",),
        html_markers=("wp-content/plugins/woocommerce",),
        base_confidence=85,
    ),
    _sig(
        "magento",
        FieldPath.TECHNOLOGY_COMMERCE_PLATFORM,
        "magento",
        generator_markers=("magento",),
        html_markers=("mage.cookies", "mage/cookies"),
        base_confidence=85,
    ),
    _sig(
        "bigcommerce",
        FieldPath.TECHNOLOGY_COMMERCE_PLATFORM,
        "bigcommerce",
        host_markers=("bigcommerce.com", "cdn11.bigcommerce.com"),
        base_confidence=85,
    ),
    _sig(
        "shopline",
        FieldPath.TECHNOLOGY_COMMERCE_PLATFORM,
        "shopline",
        host_markers=("shoplineapp.com",),
        base_confidence=80,
    ),
    _sig(
        "squarespace_commerce",
        FieldPath.TECHNOLOGY_COMMERCE_PLATFORM,
        "squarespace",
        host_markers=("squarespace.com",),
        generator_markers=("squarespace",),
        base_confidence=80,
    ),
    _sig(
        "wix_stores",
        FieldPath.TECHNOLOGY_COMMERCE_PLATFORM,
        "wix",
        host_markers=("wix.com", "wixstatic.com"),
        generator_markers=("wix",),
        base_confidence=80,
    ),
    # --- Payments -------------------------------------------------------
    _sig(
        "stripe",
        FieldPath.TECHNOLOGY_PAYMENT_PROVIDERS,
        "stripe",
        host_markers=("js.stripe.com", "api.stripe.com"),
    ),
    _sig(
        "paypal",
        FieldPath.TECHNOLOGY_PAYMENT_PROVIDERS,
        "paypal",
        host_markers=("paypal.com", "paypalobjects.com"),
    ),
    _sig(
        "afterpay",
        FieldPath.TECHNOLOGY_PAYMENT_PROVIDERS,
        "afterpay",
        host_markers=("afterpay.com",),
    ),
    _sig("klarna", FieldPath.TECHNOLOGY_PAYMENT_PROVIDERS, "klarna", host_markers=("klarna.com",)),
    _sig("laybuy", FieldPath.TECHNOLOGY_PAYMENT_PROVIDERS, "laybuy", host_markers=("laybuy.com",)),
    _sig(
        "windcave",
        FieldPath.TECHNOLOGY_PAYMENT_PROVIDERS,
        "windcave",
        host_markers=("windcave.com", "paymentexpress.com"),
    ),
    _sig(
        "shopify_payments",
        FieldPath.TECHNOLOGY_PAYMENT_PROVIDERS,
        "shopify_payments",
        html_markers=("shopify_pay",),
    ),
    _sig(
        "apple_pay",
        FieldPath.TECHNOLOGY_PAYMENT_PROVIDERS,
        "apple_pay",
        html_markers=("apple-pay", "applepay"),
    ),
    _sig(
        "google_pay",
        FieldPath.TECHNOLOGY_PAYMENT_PROVIDERS,
        "google_pay",
        html_markers=("google-pay", "gpay"),
    ),
    # --- CRM / marketing --------------------------------------------------
    _sig(
        "hubspot",
        FieldPath.TECHNOLOGY_CRM,
        "hubspot",
        host_markers=("hs-scripts.com", "hsforms.net", "hubspot.com"),
    ),
    _sig(
        "salesforce",
        FieldPath.TECHNOLOGY_CRM,
        "salesforce",
        host_markers=("salesforce.com", "force.com"),
    ),
    _sig("klaviyo", FieldPath.TECHNOLOGY_EMAIL_MARKETING, "klaviyo", host_markers=("klaviyo.com",)),
    _sig(
        "mailchimp",
        FieldPath.TECHNOLOGY_EMAIL_MARKETING,
        "mailchimp",
        host_markers=("list-manage.com", "mailchimp.com"),
    ),
    _sig(
        "activecampaign",
        FieldPath.TECHNOLOGY_EMAIL_MARKETING,
        "activecampaign",
        host_markers=("activehosted.com",),
    ),
    # --- ERP / accounting ---------------------------------------------------
    _sig("odoo", FieldPath.TECHNOLOGY_ERP, "odoo", host_markers=("odoo.com",)),
    _sig("netsuite", FieldPath.TECHNOLOGY_ERP, "netsuite", host_markers=("netsuite.com",)),
    _sig("xero", FieldPath.TECHNOLOGY_ACCOUNTING, "xero", host_markers=("xero.com",)),
    _sig("myob", FieldPath.TECHNOLOGY_ACCOUNTING, "myob", host_markers=("myob.com",)),
    _sig("cin7", FieldPath.TECHNOLOGY_ERP, "cin7", host_markers=("cin7.com",)),
    _sig(
        "unleashed", FieldPath.TECHNOLOGY_ERP, "unleashed", host_markers=("unleashedsoftware.com",)
    ),
    # --- Reviews ------------------------------------------------------------
    _sig(
        "yotpo",
        FieldPath.TECHNOLOGY_REVIEW_PLATFORMS,
        "yotpo",
        host_markers=("staticw2.yotpo.com", "yotpo.com"),
    ),
    _sig("judge_me", FieldPath.TECHNOLOGY_REVIEW_PLATFORMS, "judge_me", host_markers=("judge.me",)),
    _sig(
        "reviews_io",
        FieldPath.TECHNOLOGY_REVIEW_PLATFORMS,
        "reviews_io",
        host_markers=("reviews.io",),
    ),
    _sig(
        "trustpilot",
        FieldPath.TECHNOLOGY_REVIEW_PLATFORMS,
        "trustpilot",
        host_markers=("trustpilot.com",),
    ),
    _sig("stamped", FieldPath.TECHNOLOGY_REVIEW_PLATFORMS, "stamped", host_markers=("stamped.io",)),
    # --- Support --------------------------------------------------------------
    _sig("zendesk", FieldPath.TECHNOLOGY_SUPPORT_TOOLS, "zendesk", host_markers=("zendesk.com",)),
    _sig(
        "gorgias",
        FieldPath.TECHNOLOGY_SUPPORT_TOOLS,
        "gorgias",
        host_markers=("gorgias.chat", "gorgias.com"),
    ),
    _sig("intercom", FieldPath.TECHNOLOGY_SUPPORT_TOOLS, "intercom", host_markers=("intercom.io",)),
    _sig("tidio", FieldPath.TECHNOLOGY_SUPPORT_TOOLS, "tidio", host_markers=("tidio.co",)),
    _sig(
        "freshdesk",
        FieldPath.TECHNOLOGY_SUPPORT_TOOLS,
        "freshdesk",
        host_markers=("freshdesk.com",),
    ),
    # --- Analytics ------------------------------------------------------------
    _sig(
        "google_analytics",
        FieldPath.TECHNOLOGY_ANALYTICS,
        "google_analytics",
        host_markers=("google-analytics.com",),
    ),
    _sig(
        "google_tag_manager",
        FieldPath.TECHNOLOGY_ANALYTICS,
        "google_tag_manager",
        host_markers=("googletagmanager.com",),
    ),
    _sig(
        "meta_pixel",
        FieldPath.TECHNOLOGY_ANALYTICS,
        "meta_pixel",
        host_markers=("connect.facebook.net",),
    ),
    _sig("hotjar", FieldPath.TECHNOLOGY_ANALYTICS, "hotjar", host_markers=("hotjar.com",)),
    _sig(
        "microsoft_clarity",
        FieldPath.TECHNOLOGY_ANALYTICS,
        "microsoft_clarity",
        host_markers=("clarity.ms",),
    ),
    # --- Loyalty ------------------------------------------------------------
    _sig("smile_io", FieldPath.TECHNOLOGY_LOYALTY, "smile_io", host_markers=("smile.io",)),
    _sig(
        "loyaltylion",
        FieldPath.TECHNOLOGY_LOYALTY,
        "loyaltylion",
        host_markers=("loyaltylion.com",),
    ),
    _sig(
        "yotpo_loyalty",
        FieldPath.TECHNOLOGY_LOYALTY,
        "yotpo_loyalty",
        host_markers=("loyalty.yotpo.com",),
    ),
    # --- Frameworks -----------------------------------------------------------
    _sig(
        "react",
        FieldPath.TECHNOLOGY_FRAMEWORKS,
        "react",
        html_markers=("data-reactroot",),
        base_confidence=65,
    ),
    _sig(
        "vue",
        FieldPath.TECHNOLOGY_FRAMEWORKS,
        "vue",
        html_markers=("v-cloak", "__vue__"),
        base_confidence=65,
    ),
    _sig(
        "nuxt",
        FieldPath.TECHNOLOGY_FRAMEWORKS,
        "nuxt",
        html_markers=("__nuxt__",),
        base_confidence=68,
    ),
    _sig(
        "nextjs",
        FieldPath.TECHNOLOGY_FRAMEWORKS,
        "nextjs",
        html_markers=("__next_data__", 'id="__next"'),
        base_confidence=68,
    ),
    _sig(
        "angular",
        FieldPath.TECHNOLOGY_FRAMEWORKS,
        "angular",
        html_markers=("ng-version",),
        base_confidence=65,
    ),
    _sig(
        "svelte",
        FieldPath.TECHNOLOGY_FRAMEWORKS,
        "svelte",
        html_markers=("data-svelte",),
        base_confidence=65,
    ),
)
