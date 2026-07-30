import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as companyDetailApi from "@/api/companyDetail";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { CompanyDetail } from "@/schemas/company";
import { CompanyDetailPage } from "./CompanyDetailPage";

/**
 * Fixture `CompanyDetail` records shaped exactly like `fetchCompanyDetail`'s
 * resolved value — these tests mock `fetchCompanyDetail` itself (the real
 * composition function, see `frontend/src/api/companyDetail.ts`), not
 * `src/api/mock/**`, per the wire-company-detail-to-real-api contract.
 */
function baseCompany(overrides: Partial<CompanyDetail> = {}): CompanyDetail {
  return {
    company_id: "company-1",
    domain: "summit-outfitters.com",
    url: "https://summit-outfitters.com",
    identity: {
      company_name: "Summit Outfitters",
      platform: "Shopify",
      country: "US",
      city: "Denver",
    },
    processing: {
      status: "extracted",
      latest_discovery_run: null,
      latest_crawl_run: null,
      latest_extraction_run: null,
      latest_analysis_run: null,
      latest_scoring_run: null,
      failure_reason: null,
    },
    workflow: { manual_status: "shortlisted", shortlisted: true, notes_count: 2 },
    score: null,
    confidence: null,
    updated_at: "2026-01-15T10:00:00+00:00",
    created_at: "2026-01-01T00:00:00+00:00",
    emails: [],
    phones: [],
    score_factors: [],
    evidence: [],
    ...overrides,
  };
}

function renderDetail(companyId: string) {
  return renderWithProviders(<CompanyDetailPage />, {
    route: `/companies/${companyId}`,
    path: "/companies/:companyId",
  });
}

describe("CompanyDetailPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders identity, processing/workflow status, and evidence-backed facts for a populated company (AC-01)", async () => {
    vi.spyOn(companyDetailApi, "fetchCompanyDetail").mockResolvedValue(
      baseCompany({
        emails: ["sales@summit-outfitters.com"],
        phones: ["+1-303-555-0142"],
        evidence: [
          {
            evidence_id: "evidence-1",
            field: "business.wholesale",
            label: "Wholesale",
            value: "true",
            confidence: "high",
            source: "page_text",
            source_url: "https://summit-outfitters.com/wholesale",
            observed_at: "2026-01-10T00:00:00+00:00",
            conflicts_with: [],
          },
        ],
      }),
    );

    renderDetail("company-1");

    expect(await screen.findByRole("heading", { name: "Summit Outfitters" })).toBeInTheDocument();
    expect(screen.getByText("summit-outfitters.com")).toBeInTheDocument();
    expect(screen.getByText("sales@summit-outfitters.com")).toBeInTheDocument();
    expect(screen.getByText("+1-303-555-0142")).toBeInTheDocument();
    expect(screen.getByText("Wholesale")).toBeInTheDocument();
    expect(screen.getByText("true")).toBeInTheDocument();
    expect(companyDetailApi.fetchCompanyDetail).toHaveBeenCalledWith("company-1");
  });

  it("renders EvidenceViewer's empty state for a company with zero accepted facts (AC-02)", async () => {
    vi.spyOn(companyDetailApi, "fetchCompanyDetail").mockResolvedValue(baseCompany());

    renderDetail("company-1");

    await screen.findByRole("heading", { name: "Summit Outfitters" });
    expect(screen.getByTestId("evidence-empty-state")).toBeInTheDocument();
  });

  it("shows an explicit not-yet-scored state instead of a blank/zero score (AC-03)", async () => {
    vi.spyOn(companyDetailApi, "fetchCompanyDetail").mockResolvedValue(baseCompany());

    renderDetail("company-1");

    await screen.findByRole("heading", { name: "Summit Outfitters" });
    expect(screen.getByTestId("score-value")).toHaveTextContent("—");
    expect(screen.getByText("Not yet scored")).toBeInTheDocument();
    expect(
      screen.getByText(/this company hasn.t completed the pipeline/i),
    ).toBeInTheDocument();
  });

  it("renders Unknown placeholders for a thin-data company with no identity/emails/phones", async () => {
    vi.spyOn(companyDetailApi, "fetchCompanyDetail").mockResolvedValue(
      baseCompany({
        identity: { company_name: null, platform: null, country: null, city: null },
        emails: [],
        phones: [],
      }),
    );

    renderDetail("company-1");

    expect(await screen.findByText("Unknown company")).toBeInTheDocument();
    // Platform, country, city, emails, phones are all null/empty on this fixture.
    expect(screen.getAllByText("Unknown").length).toBeGreaterThanOrEqual(5);
  });

  it("renders a failure alert when processing.status is failed", async () => {
    vi.spyOn(companyDetailApi, "fetchCompanyDetail").mockResolvedValue(
      baseCompany({
        processing: {
          status: "failed",
          latest_discovery_run: null,
          latest_crawl_run: null,
          latest_extraction_run: null,
          latest_analysis_run: null,
          latest_scoring_run: null,
          failure_reason: "Crawl blocked by robots.txt after 3 retries",
        },
      }),
    );

    renderDetail("company-1");

    expect(await screen.findByText("Processing failed")).toBeInTheDocument();
    expect(screen.getByText("Crawl blocked by robots.txt after 3 retries")).toBeInTheDocument();
    expect(screen.getByTestId("evidence-empty-state")).toBeInTheDocument();
  });

  it("never shows a 'Conflicting evidence' banner — conflicts_with is always [] (AC-06)", async () => {
    vi.spyOn(companyDetailApi, "fetchCompanyDetail").mockResolvedValue(
      baseCompany({
        evidence: [
          {
            evidence_id: "evidence-1",
            field: "identity.platform",
            label: "Platform",
            value: "Shopify",
            confidence: "high",
            source: "page_text",
            source_url: "https://summit-outfitters.com",
            observed_at: "2026-01-10T00:00:00+00:00",
            conflicts_with: [],
          },
          {
            evidence_id: "evidence-2",
            field: "identity.platform",
            label: "Platform",
            value: "WooCommerce",
            confidence: "low",
            source: "page_text",
            source_url: "https://summit-outfitters.com/legacy",
            observed_at: "2026-01-05T00:00:00+00:00",
            conflicts_with: [],
          },
        ],
      }),
    );

    renderDetail("company-1");

    await screen.findAllByText("Shopify");
    expect(screen.getByText("WooCommerce")).toBeInTheDocument();
    expect(screen.queryByText("Conflicting evidence")).not.toBeInTheDocument();
  });

  it("shows a not-found message for an unknown company id", async () => {
    vi.spyOn(companyDetailApi, "fetchCompanyDetail").mockRejectedValue(
      new companyDetailApi.CompanyDetailNotFoundError("company-does-not-exist"),
    );

    renderDetail("company-does-not-exist");

    expect(await screen.findByText("Company not found")).toBeInTheDocument();
  });

  it("shows a generic error message when the request fails for another reason", async () => {
    vi.spyOn(companyDetailApi, "fetchCompanyDetail").mockRejectedValue(
      new companyDetailApi.CompanyDetailRequestError("boom"),
    );

    renderDetail("company-1");

    expect(await screen.findByText("Something went wrong")).toBeInTheDocument();
    expect(screen.getByText("Couldn't load this company's details.")).toBeInTheDocument();
  });
});
