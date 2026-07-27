import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EvidenceViewer } from "./EvidenceViewer";
import type { EvidenceItem } from "@/schemas/company";

const platformShopify: EvidenceItem = {
  evidence_id: "ev-1",
  field: "platform",
  label: "Platform",
  value: "Shopify",
  confidence: "medium",
  source: "crawl:tech-stack (a)",
  source_url: null,
  observed_at: "2026-07-14T00:00:00.000Z",
  conflicts_with: ["ev-2"],
};

const platformWooCommerce: EvidenceItem = {
  evidence_id: "ev-2",
  field: "platform",
  label: "Platform",
  value: "WooCommerce",
  confidence: "medium",
  source: "crawl:page-source (b)",
  source_url: null,
  observed_at: "2026-07-19T00:00:00.000Z",
  conflicts_with: ["ev-1"],
};

const revenueEvidence: EvidenceItem = {
  evidence_id: "ev-3",
  field: "estimated_revenue",
  label: "Estimated annual revenue",
  value: "$8.2M – $9.5M",
  confidence: "high",
  source: "analysis:financial-model",
  source_url: null,
  observed_at: "2026-07-18T00:00:00.000Z",
  conflicts_with: [],
};

describe("EvidenceViewer", () => {
  it("renders an empty state when there is no evidence", () => {
    render(<EvidenceViewer evidence={[]} />);

    expect(screen.getByTestId("evidence-empty-state")).toHaveTextContent(
      "No evidence collected yet.",
    );
  });

  it("groups evidence by field and renders every observed value", () => {
    render(<EvidenceViewer evidence={[platformShopify, platformWooCommerce, revenueEvidence]} />);

    expect(screen.getByText("Shopify")).toBeInTheDocument();
    expect(screen.getByText("WooCommerce")).toBeInTheDocument();
    expect(screen.getByText("$8.2M – $9.5M")).toBeInTheDocument();
    expect(screen.getByText(/crawl:tech-stack \(a\)/)).toBeInTheDocument();
    expect(screen.getByText(/crawl:page-source \(b\)/)).toBeInTheDocument();
  });

  it("flags a field with disagreeing evidence as conflicting", () => {
    render(<EvidenceViewer evidence={[platformShopify, platformWooCommerce, revenueEvidence]} />);

    const conflictWarnings = screen.getAllByText("Conflicting evidence");
    expect(conflictWarnings).toHaveLength(1);

    // The non-conflicting revenue field must not be flagged.
    const revenueGroup = screen.getByText("Estimated annual revenue").closest("div");
    expect(revenueGroup).not.toHaveTextContent("Conflicting evidence");
  });
});
