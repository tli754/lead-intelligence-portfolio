import { afterEach, describe, expect, it, vi } from "vitest";

import { CompanyListRequestError, listCompanies, mapCompanyListItem } from "./companies";
import { companyListItemSchema } from "@/schemas/company";

/** A `CompanyListItemResponse`-shaped fixture with every optional field present. */
function fullDto() {
  return {
    companyId: "company-1",
    companyName: "Summit Outfitters",
    domain: "summit-outfitters.com",
    platform: "Shopify",
    country: "US",
    city: "Denver",
    opportunityScore: null,
    confidence: null,
    mainReason: null,
    processingStatus: "ready",
    workflowStatus: "shortlisted",
    updatedAt: "2026-01-15T10:00:00+00:00",
  };
}

/** A `CompanyListItemResponse`-shaped fixture with every optional field null. */
function allNullDto() {
  return {
    companyId: "company-2",
    companyName: null,
    domain: "247dropship.net",
    platform: null,
    country: null,
    city: null,
    opportunityScore: null,
    confidence: null,
    mainReason: null,
    processingStatus: "imported",
    workflowStatus: "unreviewed",
    updatedAt: "2026-01-10T08:30:00+00:00",
  };
}

describe("mapCompanyListItem", () => {
  it("maps a company with every optional field present into the nested CompanyListItem shape", () => {
    const item = mapCompanyListItem(fullDto());

    expect(item).toEqual({
      company_id: "company-1",
      domain: "summit-outfitters.com",
      identity: {
        company_name: "Summit Outfitters",
        platform: "Shopify",
        country: "US",
        city: "Denver",
      },
      processing: {
        status: "ready",
        latest_discovery_run: null,
        latest_crawl_run: null,
        latest_extraction_run: null,
        latest_analysis_run: null,
        latest_scoring_run: null,
        failure_reason: null,
      },
      workflow: {
        manual_status: "shortlisted",
        shortlisted: true,
        notes_count: 0,
      },
      score: null,
      confidence: null,
      updated_at: "2026-01-15T10:00:00+00:00",
    });
    expect(() => companyListItemSchema.parse(item)).not.toThrow();
  });

  it("maps a company with all-null optional fields, defaulting shortlisted to false", () => {
    const item = mapCompanyListItem(allNullDto());

    expect(item.identity).toEqual({
      company_name: null,
      platform: null,
      country: null,
      city: null,
    });
    expect(item.workflow.shortlisted).toBe(false);
    expect(item.workflow.notes_count).toBe(0);
    expect(item.score).toBeNull();
    expect(item.confidence).toBeNull();
    expect(() => companyListItemSchema.parse(item)).not.toThrow();
  });

  it.each([
    "imported",
    "discovering",
    "discovered",
    "crawling",
    "crawled",
    "extracting",
    "extracted",
    "analysing",
    "analysed",
    "scoring",
    "ready",
    "partial",
    "failed",
    "stale",
  ])("round-trips processingStatus %s through Zod parsing without error", (processingStatus) => {
    const item = mapCompanyListItem({ ...fullDto(), processingStatus });

    expect(() => companyListItemSchema.parse(item)).not.toThrow();
  });

  it.each([
    "unreviewed",
    "reviewed",
    "shortlisted",
    "not_suitable",
    "contacted",
    "customer",
    "archived",
  ])("round-trips workflowStatus %s through Zod parsing without error", (workflowStatus) => {
    const item = mapCompanyListItem({ ...fullDto(), workflowStatus });

    expect(() => companyListItemSchema.parse(item)).not.toThrow();
  });
});

describe("listCompanies", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function stubFetch(response: Response) {
    const fetchMock = vi.fn().mockResolvedValue(response);
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  it("maps the {data, pagination} envelope to {items, total}", async () => {
    const body = {
      data: [fullDto(), allNullDto()],
      pagination: { page: 1, pageSize: 20, total: 2 },
    };
    stubFetch(new Response(JSON.stringify(body), { status: 200 }));

    const result = await listCompanies({});

    expect(result.total).toBe(2);
    expect(result.items).toHaveLength(2);
    expect(result.items[0].company_id).toBe("company-1");
  });

  it("sends processingStatus/workflowStatus/platform as query params, dropping q/sort/order", async () => {
    const fetchMock = stubFetch(
      new Response(JSON.stringify({ data: [], pagination: { page: 1, pageSize: 20, total: 0 } }), {
        status: 200,
      }),
    );

    await listCompanies({
      processing_status: "ready",
      workflow_status: "shortlisted",
      platform: "Shopify",
      q: "meridian",
      sort: "score",
      order: "asc",
    });

    const requestedUrl = fetchMock.mock.calls[0][0] as string;
    expect(requestedUrl).toContain("processingStatus=ready");
    expect(requestedUrl).toContain("workflowStatus=shortlisted");
    expect(requestedUrl).toContain("platform=Shopify");
    expect(requestedUrl).not.toContain("q=");
    expect(requestedUrl).not.toContain("sort=");
    expect(requestedUrl).not.toContain("order=");
  });

  it("throws CompanyListRequestError on a non-2xx response", async () => {
    const errorBody = JSON.stringify({ detail: "processingStatus is not a valid enum value" });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() => Promise.resolve(new Response(errorBody, { status: 422 }))),
    );

    await expect(listCompanies({})).rejects.toThrow(CompanyListRequestError);
    await expect(listCompanies({})).rejects.toThrow(
      "processingStatus is not a valid enum value",
    );
  });
});
