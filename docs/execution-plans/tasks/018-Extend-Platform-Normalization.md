Add Platform data from html code to company.

Clarified in conversation: three different notions of "platform" exist
in this codebase — (1) `modules/imports`' StoreLeads-HTML import path,
which already extracts a `platform` value and writes it to
`Company.identity.platform` on creation, but only via
`platform_normalizer.normalize_platform`, which recognizes just
`{shopify, woocommerce, magento, custom}`; (2) `modules/extraction`'s
signature-based detector (`extractors/technology/signatures.py`),
which inspects a company's own *crawled* website HTML (generator meta
tags, script src patterns) to populate a separate
`technology.commerce_platform` field; (3) an unimplemented
`identity.platform` field-catalogue slot with no extractor. Asked to
scope to option (1): fix the StoreLeads import normalizer so it stops
silently dropping real platform values.

Concretely: Task 016 (Vaadin-grid StoreLeads import support) shipped
using the existing narrow `normalize_platform`, and its own contract
text explicitly documents — as a confirmed, accepted behavior — that a
`platform` cell value of `"PrestaShop"` normalizes to `null`, "same
documented behavior as any unrecognized platform value." But
PrestaShop and OpenCart are exactly the two platforms in Task 016's own
motivating real fixtures (`.claude/data/storeLeads_prestaShop.html`,
`.claude/data/storeLeads_openCart.html`) — confirmed by parsing both
files directly: `storeLeads_prestaShop.html` contains raw platform
values `PrestaShop`/`WooCommerce`; `storeLeads_openCart.html` contains
`OpenCart`. So the real-world data this feature was built to import
has its platform silently dropped to `null` on every PrestaShop/
OpenCart row.

Ask: extend `normalize_platform` to also recognize `PrestaShop` and
`OpenCart` (case-insensitive, matching the existing pattern for
shopify/woocommerce/magento/custom), so these two confirmed-real
platform values flow through into `Company.identity.platform` instead
of being dropped. Do not add speculative platform values with no
confirmed real-fixture evidence (e.g. BigCommerce remains intentionally
unrecognized, per the existing test suite) — scope is limited to the
two platforms this repository has actual evidence for.
