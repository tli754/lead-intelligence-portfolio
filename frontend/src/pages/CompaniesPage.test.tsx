import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as companiesApi from "@/api/companies";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { CompanyListFilters, CompanyListItem, CompanyListResponse } from "@/schemas/company";
import { CompaniesPage } from "./CompaniesPage";

/**
 * Fixture companies shaped exactly like `listCompanies`'s resolved value
 * (already adapted to the nested `CompanyListItem` shape) — these tests
 * mock `listCompanies` itself (the real API client, see
 * `frontend/src/api/companies.ts`), not `src/api/mock/**`, per Task 010.
 */
const summitOutfitters: CompanyListItem = {
  company_id: "company-1",
  domain: "summit-outfitters.com",
  identity: { company_name: "Summit Outfitters", platform: "Shopify", country: "US", city: "Denver" },
  processing: {
    status: "ready",
    latest_discovery_run: null,
    latest_crawl_run: null,
    latest_extraction_run: null,
    latest_analysis_run: null,
    latest_scoring_run: null,
    failure_reason: null,
  },
  workflow: { manual_status: "shortlisted", shortlisted: true, notes_count: 0 },
  score: null,
  confidence: null,
  updated_at: "2026-01-15T10:00:00+00:00",
};

const ashgroveTextiles: CompanyListItem = {
  company_id: "company-2",
  domain: "ashgrove-textiles.com",
  identity: { company_name: "Ashgrove Textiles", platform: "WooCommerce", country: "GB", city: null },
  processing: {
    status: "failed",
    latest_discovery_run: null,
    latest_crawl_run: null,
    latest_extraction_run: null,
    latest_analysis_run: null,
    latest_scoring_run: null,
    failure_reason: null,
  },
  workflow: { manual_status: "unreviewed", shortlisted: false, notes_count: 0 },
  score: null,
  confidence: null,
  updated_at: "2026-01-12T09:00:00+00:00",
};

const dropship: CompanyListItem = {
  company_id: "company-3",
  domain: "247dropship.net",
  identity: { company_name: null, platform: null, country: null, city: null },
  processing: {
    status: "imported",
    latest_discovery_run: null,
    latest_crawl_run: null,
    latest_extraction_run: null,
    latest_analysis_run: null,
    latest_scoring_run: null,
    failure_reason: null,
  },
  workflow: { manual_status: "unreviewed", shortlisted: false, notes_count: 0 },
  score: null,
  confidence: null,
  updated_at: "2026-01-05T09:00:00+00:00",
};

const ALL_COMPANIES = [summitOutfitters, ashgroveTextiles, dropship];

/**
 * A fake `listCompanies` that filters in memory by `processing_status`/
 * `workflow_status`/`platform`, mirroring what the real backend's
 * `GET /api/companies` supports. `q`/`sort`/`order` are intentionally
 * ignored — the real endpoint has no free-text search or server-side
 * sort (see the companies-list feature contract's "Filters" gap).
 */
function fakeListCompanies(filters: CompanyListFilters = {}): Promise<CompanyListResponse> {
  const items = ALL_COMPANIES.filter((company) => {
    if (filters.processing_status && company.processing.status !== filters.processing_status) {
      return false;
    }
    if (filters.workflow_status && company.workflow.manual_status !== filters.workflow_status) {
      return false;
    }
    if (filters.platform && company.identity.platform !== filters.platform) {
      return false;
    }
    return true;
  });
  return Promise.resolve({ items, total: items.length });
}

function renderPage() {
  return renderWithProviders(<CompaniesPage />);
}

describe("CompaniesPage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders the ranking table with company rows from the real listCompanies client", async () => {
    vi.spyOn(companiesApi, "listCompanies").mockImplementation(fakeListCompanies);
    renderPage();

    expect(await screen.findByText("Summit Outfitters")).toBeInTheDocument();
    expect(screen.getByText("Ashgrove Textiles")).toBeInTheDocument();
    expect(screen.getByText("3 companies")).toBeInTheDocument();
    expect(screen.getByText("Shortlisted")).toBeInTheDocument();
  });

  it("renders unscored companies with empty-state score/confidence, not 0 or blank", async () => {
    vi.spyOn(companiesApi, "listCompanies").mockImplementation(fakeListCompanies);
    renderPage();
    await screen.findByText("Summit Outfitters");

    // formatScore(null) -> em dash; ConfidenceMeter(null) -> "Not yet scored".
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Not yet scored").length).toBeGreaterThan(0);
  });

  it("filters by processing status, forwarding the filter to listCompanies", async () => {
    const listCompaniesSpy = vi
      .spyOn(companiesApi, "listCompanies")
      .mockImplementation(fakeListCompanies);
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Summit Outfitters");

    await user.selectOptions(screen.getByLabelText(/processing status/i), "failed");

    expect(await screen.findByText("Ashgrove Textiles")).toBeInTheDocument();
    expect(screen.getByText("1 company")).toBeInTheDocument();
    expect(screen.queryByText("Summit Outfitters")).not.toBeInTheDocument();
    expect(listCompaniesSpy).toHaveBeenLastCalledWith(
      expect.objectContaining({ processing_status: "failed" }),
    );
  });

  it("shows an empty state when no company matches the filters", async () => {
    vi.spyOn(companiesApi, "listCompanies").mockImplementation(fakeListCompanies);
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Summit Outfitters");

    await user.selectOptions(screen.getByLabelText(/review status/i), "customer");

    expect(await screen.findByText("No companies match these filters.")).toBeInTheDocument();
  });

  it("does not filter results by search text — GET /api/companies has no free-text search", async () => {
    vi.spyOn(companiesApi, "listCompanies").mockImplementation(fakeListCompanies);
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Summit Outfitters");

    await user.type(screen.getByLabelText(/^search$/i), "meridian");

    // Known gap (see Task 010 contract "Filters"): the search box is
    // inert against the real backend, which has no `q` query param.
    expect(screen.getByText("Summit Outfitters")).toBeInTheDocument();
    expect(screen.getByText("3 companies")).toBeInTheDocument();
  });

  it("sorts rows when a column header is clicked", async () => {
    vi.spyOn(companiesApi, "listCompanies").mockImplementation(fakeListCompanies);
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Summit Outfitters");

    await user.click(screen.getByRole("button", { name: /company/i }));

    const rows = await screen.findAllByRole("row");
    // Ascending by company-name-or-domain: "247dropship.net" sorts before
    // any capitalized company name (digit '2' < 'A' in char-code order).
    expect(within(rows[1]).getByText("247dropship.net")).toBeInTheDocument();
  });

  it("shows an error alert when listCompanies rejects", async () => {
    vi.spyOn(companiesApi, "listCompanies").mockRejectedValue(
      new companiesApi.CompanyListRequestError("boom"),
    );
    renderPage();

    expect(await screen.findByText("Couldn't load companies")).toBeInTheDocument();
  });
});
