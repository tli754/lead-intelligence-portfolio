/**
 * Human-readable labels for extraction `FieldPath` values.
 *
 * Mirrors `backend/app/modules/extraction/domain/field_catalogue.py`'s
 * `FieldPath` enum (52 entries, grouped identity/business/catalogue/
 * operations/technology/organisation/growth) — that catalogue is
 * backend-only Python, so this is a small, independently-maintained
 * frontend copy of just the label, not the full field definition.
 *
 * Used by `fetchCompanyDetail` (`./companyDetail.ts`) to turn
 * `EvidenceResponse.factFieldPath` (e.g. `"business.wholesale"`) into
 * `EvidenceItem.label` (e.g. `"Wholesale"`) for `EvidenceViewer`'s
 * per-field grouping.
 */

export const FIELD_LABELS: Record<string, string> = {
  // Identity
  "identity.company_name": "Company name",
  "identity.trading_name": "Trading name",
  "identity.platform": "Platform",
  "identity.country": "Country",
  "identity.city": "City",
  "identity.language": "Language",

  // Business
  "business.wholesale": "Wholesale",
  "business.trade_accounts": "Trade accounts",
  "business.click_and_collect": "Click & collect",
  "business.subscription": "Subscription",
  "business.booking": "Booking",
  "business.online_only": "Online only",
  "business.custom_products": "Custom products",
  "business.brands": "Brands",

  // Catalogue
  "catalogue.product_count": "Product count",
  "catalogue.product_count_estimate": "Product count (estimate)",
  "catalogue.sku_count_estimate": "SKU count (estimate)",
  "catalogue.variant_evidence": "Product variants",
  "catalogue.collection_count": "Collection count",
  "catalogue.bundle_evidence": "Bundles / kits",
  "catalogue.customization_evidence": "Customization options",

  // Physical operations
  "operations.retail_store_count": "Retail stores",
  "operations.showroom_count": "Showrooms",
  "operations.warehouse_count": "Warehouses",
  "operations.office_count": "Offices",
  "operations.pickup_available": "Pickup available",
  "operations.returns_location_count": "Returns locations",
  "operations.locations": "Locations",

  // Technology
  "technology.commerce_platform": "Commerce platform",
  "technology.payment_providers": "Payment providers",
  "technology.crm": "CRM",
  "technology.erp": "ERP",
  "technology.accounting": "Accounting software",
  "technology.review_platforms": "Review platforms",
  "technology.support_tools": "Support tools",
  "technology.analytics": "Analytics",
  "technology.loyalty": "Loyalty programs",
  "technology.email_marketing": "Email marketing",
  "technology.ai_signals": "AI signals",
  "technology.frameworks": "Frontend frameworks",

  // Organisation / contact
  "organisation.emails": "Emails",
  "organisation.phone_numbers": "Phone numbers",
  "organisation.people": "People",
  "organisation.internal_it_status": "Internal IT status",
  "organisation.recommended_contact_candidates": "Recommended contacts",

  // Growth signals
  "growth.hiring": "Hiring",
  "growth.expansion": "Expansion",
  "growth.new_store": "New store openings",
  "growth.warehouse_change": "Warehouse changes",
  "growth.platform_migration": "Platform migration",
  "growth.new_category": "New category",
  "growth.subscription_launch": "Subscription launch",
};

/** Title-cases the final dotted segment (e.g. `"foo.new_field"` -> `"New field"`). */
function humanizeUnknownFieldPath(fieldPath: string): string {
  const tail = fieldPath.includes(".") ? fieldPath.split(".").pop()! : fieldPath;
  const words = tail.split("_").filter(Boolean);
  if (words.length === 0) return fieldPath;
  return words.map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(" ");
}

/**
 * Looks up a human label for a `FieldPath` dotted string. Unknown/future
 * field paths (not yet in `FIELD_LABELS`) fall back to a humanized version
 * of the path's final segment rather than crashing.
 */
export function getFieldLabel(fieldPath: string): string {
  return FIELD_LABELS[fieldPath] ?? humanizeUnknownFieldPath(fieldPath);
}
