import { describe, expect, it } from "vitest";

import { FIELD_LABELS, getFieldLabel } from "./fieldLabels";

/**
 * Every `FieldPath` value currently in
 * `backend/app/modules/extraction/domain/field_catalogue.py` (52 entries,
 * `FIELD_CATALOGUE_VERSION = "v1"`). Kept as a literal list (not imported
 * — the catalogue is backend-only Python) so a future field-path addition
 * to the backend catalogue without a matching frontend label surfaces here
 * as a failing test, not a silent gap.
 */
const ALL_FIELD_PATHS = [
  "identity.company_name",
  "identity.trading_name",
  "identity.platform",
  "identity.country",
  "identity.city",
  "identity.language",
  "business.wholesale",
  "business.trade_accounts",
  "business.click_and_collect",
  "business.subscription",
  "business.booking",
  "business.online_only",
  "business.custom_products",
  "business.brands",
  "catalogue.product_count",
  "catalogue.product_count_estimate",
  "catalogue.sku_count_estimate",
  "catalogue.variant_evidence",
  "catalogue.collection_count",
  "catalogue.bundle_evidence",
  "catalogue.customization_evidence",
  "operations.retail_store_count",
  "operations.showroom_count",
  "operations.warehouse_count",
  "operations.office_count",
  "operations.pickup_available",
  "operations.returns_location_count",
  "operations.locations",
  "technology.commerce_platform",
  "technology.payment_providers",
  "technology.crm",
  "technology.erp",
  "technology.accounting",
  "technology.review_platforms",
  "technology.support_tools",
  "technology.analytics",
  "technology.loyalty",
  "technology.email_marketing",
  "technology.ai_signals",
  "technology.frameworks",
  "organisation.emails",
  "organisation.phone_numbers",
  "organisation.people",
  "organisation.internal_it_status",
  "organisation.recommended_contact_candidates",
  "growth.hiring",
  "growth.expansion",
  "growth.new_store",
  "growth.warehouse_change",
  "growth.platform_migration",
  "growth.new_category",
  "growth.subscription_launch",
];

describe("FIELD_LABELS", () => {
  it("covers every FieldPath value in the backend field_catalogue.py (52 entries)", () => {
    expect(ALL_FIELD_PATHS).toHaveLength(52);
    for (const fieldPath of ALL_FIELD_PATHS) {
      expect(FIELD_LABELS[fieldPath]).toBeDefined();
      expect(FIELD_LABELS[fieldPath]).not.toBe("");
    }
  });
});

describe("getFieldLabel", () => {
  it("returns the known label for a known field path", () => {
    expect(getFieldLabel("business.wholesale")).toBe("Wholesale");
    expect(getFieldLabel("organisation.emails")).toBe("Emails");
  });

  it("falls back to a humanized version of an unknown field path's tail segment", () => {
    expect(getFieldLabel("future_section.new_signal_field")).toBe("New Signal Field");
  });

  it("falls back to the raw path if it has no underscore-separated tail", () => {
    expect(getFieldLabel("mystery")).toBe("Mystery");
  });
});
