import { afterEach, describe, expect, it, vi } from "vitest";

import {
  CompanyDetailNotFoundError,
  CompanyDetailRequestError,
  EVIDENCE_STRENGTH_TO_CONFIDENCE,
  type EvidenceResponseDto,
  fetchCompanyDetail,
  getCompany,
  listCompanyFacts,
  listFactEvidence,
  mapEvidenceItem,
} from "./companyDetail";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function fullCompanyDto() {
  return {
    companyId: "company-1",
    domain: "summit-outfitters.com",
    normalizedDomain: "summit-outfitters.com",
    identity: { companyName: "Summit Outfitters", platform: "Shopify", country: "US", city: "Denver" },
    processing: {
      status: "extracted",
      latestDiscoveryRunId: "run-discovery-1",
      latestCrawlRunId: "run-crawl-1",
      latestExtractionRunId: "run-extraction-1",
      latestAnalysisRunId: null,
      latestScoringRunId: null,
    },
    workflow: { manualStatus: "shortlisted", shortlisted: true, notesCount: 2 },
    createdAt: "2026-01-01T00:00:00+00:00",
    updatedAt: "2026-01-15T10:00:00+00:00",
    documentVersion: 1,
  };
}

function fullEvidenceDto(overrides: Partial<EvidenceResponseDto> = {}): EvidenceResponseDto {
  return {
    evidenceId: "evidence-1",
    factFieldPath: "business.wholesale",
    evidenceType: "page_text",
    pageType: "about",
    strength: "strong",
    sourceUrl: "https://summit-outfitters.com/about",
    rawValue: "true",
    normalizedValue: "true",
    excerpt: { text: "We offer wholesale accounts." },
    observedAt: "2026-01-10T00:00:00+00:00",
    ...overrides,
  };
}

describe("getCompany", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns the parsed CompanyResponseDto on success", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(fullCompanyDto())));

    const dto = await getCompany("company-1");

    expect(dto.companyId).toBe("company-1");
    expect(dto.domain).toBe("summit-outfitters.com");
  });

  it("throws CompanyDetailNotFoundError on a 404", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ detail: "not found" }, 404)),
    );

    await expect(getCompany("missing-id")).rejects.toThrow(CompanyDetailNotFoundError);
  });

  it("throws CompanyDetailRequestError on a non-404 error response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() => Promise.resolve(jsonResponse({ detail: "server exploded" }, 500))),
    );

    await expect(getCompany("company-1")).rejects.toThrow(CompanyDetailRequestError);
    await expect(getCompany("company-1")).rejects.toThrow("server exploded");
  });
});

describe("listCompanyFacts / listFactEvidence", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends page/pageSize query params for facts", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ data: [], pagination: { page: 2, pageSize: 50, total: 0 } }));
    vi.stubGlobal("fetch", fetchMock);

    await listCompanyFacts("company-1", 2, 50);

    const requestedUrl = fetchMock.mock.calls[0][0] as string;
    expect(requestedUrl).toContain("/api/companies/company-1/facts");
    expect(requestedUrl).toContain("page=2");
    expect(requestedUrl).toContain("pageSize=50");
  });

  it("sends page/pageSize query params for fact evidence", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(jsonResponse({ data: [], pagination: { page: 1, pageSize: 50, total: 0 } }));
    vi.stubGlobal("fetch", fetchMock);

    await listFactEvidence("fact-1", 1, 50);

    const requestedUrl = fetchMock.mock.calls[0][0] as string;
    expect(requestedUrl).toContain("/api/facts/fact-1/evidence");
  });

  it("throws CompanyDetailRequestError when the facts request is rejected", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ detail: "bad request" }, 400)),
    );

    await expect(listCompanyFacts("company-1")).rejects.toThrow(CompanyDetailRequestError);
  });
});

describe("mapEvidenceItem", () => {
  it.each([
    ["authoritative", "high"],
    ["strong", "high"],
    ["moderate", "medium"],
    ["weak", "low"],
  ] as const)("maps EvidenceStrength %s to ConfidenceLevel %s", (strength, expected) => {
    const item = mapEvidenceItem(fullEvidenceDto({ strength }));
    expect(item.confidence).toBe(expected);
  });

  it("covers every EVIDENCE_STRENGTH_TO_CONFIDENCE key with a defined ConfidenceLevel", () => {
    for (const level of Object.values(EVIDENCE_STRENGTH_TO_CONFIDENCE)) {
      expect(["high", "medium", "low"]).toContain(level);
    }
  });

  it("maps field/label from factFieldPath and hardcodes conflicts_with to []", () => {
    const item = mapEvidenceItem(fullEvidenceDto({ factFieldPath: "business.wholesale" }));

    expect(item.field).toBe("business.wholesale");
    expect(item.label).toBe("Wholesale");
    expect(item.conflicts_with).toEqual([]);
  });

  it("maps source from evidenceType", () => {
    const item = mapEvidenceItem(fullEvidenceDto({ evidenceType: "meta_tag" }));
    expect(item.source).toBe("meta_tag");
  });

  it("prefers normalizedValue, then rawValue, then excerpt text for the display value", () => {
    expect(
      mapEvidenceItem(fullEvidenceDto({ normalizedValue: "normalized", rawValue: "raw" })).value,
    ).toBe("normalized");
    expect(
      mapEvidenceItem(fullEvidenceDto({ normalizedValue: null, rawValue: "raw" })).value,
    ).toBe("raw");
    expect(
      mapEvidenceItem(
        fullEvidenceDto({ normalizedValue: null, rawValue: null, excerpt: { text: "fallback text" } }),
      ).value,
    ).toBe("fallback text");
  });
});

describe("fetchCompanyDetail", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  /**
   * A router-style fetch fake: dispatches by pathname, and lets each
   * fixture report whatever `pagination.total`/`pagination.pageSize` it
   * wants — `fetchAllPages` decides how many more pages to request from
   * those values, independent of the `pageSize` actually sent in the
   * request. This is what lets a small fixture (2-3 items) exercise real
   * multi-page pagination (AC-04) without needing 200+ fixture rows.
   */
  function stubRoutedFetch(routes: Record<string, () => Response>) {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input));
      const key = `${url.pathname}?page=${url.searchParams.get("page") ?? "1"}`;
      const handler = routes[key] ?? routes[url.pathname];
      if (!handler) {
        throw new Error(`Unhandled request in test: ${url.pathname}${url.search}`);
      }
      return handler();
    });
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  }

  it("renders identity/processing/workflow from the real company summary (AC-01)", async () => {
    stubRoutedFetch({
      "/api/companies/company-1": () => jsonResponse(fullCompanyDto()),
      "/api/companies/company-1/facts?page=1": () =>
        jsonResponse({ data: [], pagination: { page: 1, pageSize: 200, total: 0 } }),
    });

    const detail = await fetchCompanyDetail("company-1");

    expect(detail.company_id).toBe("company-1");
    expect(detail.domain).toBe("summit-outfitters.com");
    expect(detail.url).toBe("https://summit-outfitters.com");
    expect(detail.identity.company_name).toBe("Summit Outfitters");
    expect(detail.processing.status).toBe("extracted");
    expect(detail.workflow.shortlisted).toBe(true);
    expect(detail.workflow.notes_count).toBe(2);
  });

  it("returns an empty evidence array for a company with zero accepted facts (AC-02)", async () => {
    stubRoutedFetch({
      "/api/companies/company-1": () => jsonResponse(fullCompanyDto()),
      "/api/companies/company-1/facts?page=1": () =>
        jsonResponse({ data: [], pagination: { page: 1, pageSize: 200, total: 0 } }),
    });

    const detail = await fetchCompanyDetail("company-1");

    expect(detail.evidence).toEqual([]);
    expect(detail.emails).toEqual([]);
    expect(detail.phones).toEqual([]);
  });

  it("always renders score/score_factors as the not-yet-scored state (AC-03)", async () => {
    stubRoutedFetch({
      "/api/companies/company-1": () => jsonResponse(fullCompanyDto()),
      "/api/companies/company-1/facts?page=1": () =>
        jsonResponse({ data: [], pagination: { page: 1, pageSize: 200, total: 0 } }),
    });

    const detail = await fetchCompanyDetail("company-1");

    expect(detail.score).toBeNull();
    expect(detail.confidence).toBeNull();
    expect(detail.score_factors).toEqual([]);
  });

  it("paginates through every page of facts and every page of each fact's evidence (AC-04)", async () => {
    const emailsFact = {
      factId: "fact-emails",
      companyId: "company-1",
      fieldPath: "organisation.emails",
      value: ["sales@summit-outfitters.com"],
      normalizedValue: [{ value: "sales@summit-outfitters.com" }],
      evidenceIds: ["evidence-emails-1"],
      status: "accepted",
    };
    const wholesaleFact = {
      factId: "fact-wholesale",
      companyId: "company-1",
      fieldPath: "business.wholesale",
      value: true,
      normalizedValue: true,
      evidenceIds: ["evidence-wholesale-1", "evidence-wholesale-2"],
      status: "accepted",
    };

    stubRoutedFetch({
      "/api/companies/company-1": () => jsonResponse(fullCompanyDto()),
      // Facts: 2 total, reported one-per-page to force a second page request.
      "/api/companies/company-1/facts?page=1": () =>
        jsonResponse({ data: [emailsFact], pagination: { page: 1, pageSize: 1, total: 2 } }),
      "/api/companies/company-1/facts?page=2": () =>
        jsonResponse({ data: [wholesaleFact], pagination: { page: 2, pageSize: 1, total: 2 } }),
      // Evidence for the emails fact: a single page.
      "/api/facts/fact-emails/evidence?page=1": () =>
        jsonResponse({
          data: [fullEvidenceDto({ evidenceId: "evidence-emails-1", factFieldPath: "organisation.emails" })],
          pagination: { page: 1, pageSize: 200, total: 1 },
        }),
      // Evidence for the wholesale fact: 2 total, one-per-page.
      "/api/facts/fact-wholesale/evidence?page=1": () =>
        jsonResponse({
          data: [
            fullEvidenceDto({
              evidenceId: "evidence-wholesale-1",
              factFieldPath: "business.wholesale",
              strength: "weak",
            }),
          ],
          pagination: { page: 1, pageSize: 1, total: 2 },
        }),
      "/api/facts/fact-wholesale/evidence?page=2": () =>
        jsonResponse({
          data: [
            fullEvidenceDto({
              evidenceId: "evidence-wholesale-2",
              factFieldPath: "business.wholesale",
              strength: "authoritative",
            }),
          ],
          pagination: { page: 2, pageSize: 1, total: 2 },
        }),
    });

    const detail = await fetchCompanyDetail("company-1");

    expect(detail.emails).toEqual(["sales@summit-outfitters.com"]);
    expect(detail.evidence).toHaveLength(3);
    const evidenceIds = detail.evidence.map((item) => item.evidence_id).sort();
    expect(evidenceIds).toEqual(["evidence-emails-1", "evidence-wholesale-1", "evidence-wholesale-2"]);
  });

  it("defaults emails/phones to [] when the company has no matching organisation fact (AC-07)", async () => {
    const wholesaleFact = {
      factId: "fact-wholesale",
      companyId: "company-1",
      fieldPath: "business.wholesale",
      value: true,
      normalizedValue: true,
      evidenceIds: [],
      status: "accepted",
    };

    stubRoutedFetch({
      "/api/companies/company-1": () => jsonResponse(fullCompanyDto()),
      "/api/companies/company-1/facts?page=1": () =>
        jsonResponse({ data: [wholesaleFact], pagination: { page: 1, pageSize: 200, total: 1 } }),
      "/api/facts/fact-wholesale/evidence?page=1": () =>
        jsonResponse({ data: [], pagination: { page: 1, pageSize: 200, total: 0 } }),
    });

    const detail = await fetchCompanyDetail("company-1");

    expect(detail.emails).toEqual([]);
    expect(detail.phones).toEqual([]);
  });
});
