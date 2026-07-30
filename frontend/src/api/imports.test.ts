import { afterEach, describe, expect, it, vi } from "vitest";

import {
  commitStoreLeadsImport,
  previewStoreLeadsImport,
  StoreLeadsImportRequestError,
} from "./imports";
import type { ImportRow } from "@/schemas/imports";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function row(overrides: Partial<ImportRow> = {}): ImportRow {
  return {
    rowNumber: 1,
    website: "https://www.summitoutfitters.com",
    normalizedDomain: "summitoutfitters.com",
    platform: "shopify",
    country: "United States",
    city: "Denver",
    validationStatus: "valid",
    errors: [],
    duplicateStatus: "new",
    outcome: null,
    ...overrides,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("previewStoreLeadsImport", () => {
  it("posts html to the preview endpoint and returns the parsed response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        data: {
          summary: {
            rowsFound: 1,
            validRows: 1,
            invalidRows: 0,
            existingCompanies: 0,
            duplicateRowsInFile: 0,
            importableRows: 1,
          },
          rows: [row()],
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await previewStoreLeadsImport("<table></table>");

    expect(result.data.summary.rowsFound).toBe(1);
    expect(result.data.rows[0].website).toBe("https://www.summitoutfitters.com");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/imports/storeleads/preview");
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({ html: "<table></table>" });
  });

  it.each([
    ["new"],
    ["existing"],
    ["duplicate_in_file"],
    ["unknown"],
  ] as const)("round-trips a row with duplicateStatus %s through the Zod schema", async (status) => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({
          data: {
            summary: {
              rowsFound: 1,
              validRows: 1,
              invalidRows: 0,
              existingCompanies: 0,
              duplicateRowsInFile: 0,
              importableRows: 1,
            },
            rows: [row({ duplicateStatus: status })],
          },
        }),
      ),
    );

    const result = await previewStoreLeadsImport("<table></table>");

    expect(result.data.rows[0].duplicateStatus).toBe(status);
  });

  it.each(["valid", "invalid"] as const)(
    "round-trips a row with validationStatus %s through the Zod schema",
    async (status) => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(
          jsonResponse({
            data: {
              summary: {
                rowsFound: 1,
                validRows: 0,
                invalidRows: 1,
                existingCompanies: 0,
                duplicateRowsInFile: 0,
                importableRows: 0,
              },
              rows: [row({ validationStatus: status })],
            },
          }),
        ),
      );

      const result = await previewStoreLeadsImport("<table></table>");

      expect(result.data.rows[0].validationStatus).toBe(status);
    },
  );

  it("throws StoreLeadsImportRequestError with the FastAPI detail string on a non-ok response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() =>
        Promise.resolve(jsonResponse({ detail: "html must not be empty" }, 422)),
      ),
    );

    await expect(previewStoreLeadsImport("")).rejects.toThrow(StoreLeadsImportRequestError);
    await expect(previewStoreLeadsImport("")).rejects.toThrow("html must not be empty");
  });

  it("throws StoreLeadsImportRequestError with the first validation-array message on a non-ok response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(
          { detail: [{ msg: "field required", loc: ["body", "html"] }] },
          422,
        ),
      ),
    );

    await expect(previewStoreLeadsImport("")).rejects.toThrow("field required");
  });

  it("falls back to a generic message when the error body has no usable detail", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({}, 500)));

    await expect(previewStoreLeadsImport("<table></table>")).rejects.toThrow(
      "The import request was rejected.",
    );
  });
});

describe("commitStoreLeadsImport", () => {
  it("posts html to the commit endpoint and returns the parsed response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        data: {
          created: 1,
          skippedExisting: 0,
          skippedInvalid: 0,
          failed: 0,
          rows: [row({ outcome: "created" })],
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await commitStoreLeadsImport("<table></table>");

    expect(result.data.created).toBe(1);
    expect(result.data.rows[0].outcome).toBe("created");
    const [url] = fetchMock.mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/imports/storeleads");
  });

  it.each(["created", "skipped_existing", "skipped_invalid", "failed"] as const)(
    "round-trips a row with outcome %s through the Zod schema",
    async (outcome) => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(
          jsonResponse({
            data: {
              created: 0,
              skippedExisting: 0,
              skippedInvalid: 0,
              failed: 0,
              rows: [row({ outcome })],
            },
          }),
        ),
      );

      const result = await commitStoreLeadsImport("<table></table>");

      expect(result.data.rows[0].outcome).toBe(outcome);
    },
  );

  it("throws StoreLeadsImportRequestError with the FastAPI detail string on a non-ok response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ detail: "commit rejected" }, 400)),
    );

    await expect(commitStoreLeadsImport("<table></table>")).rejects.toThrow("commit rejected");
  });

  it("throws StoreLeadsImportRequestError with the first validation-array message on a non-ok response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({ detail: [{ msg: "html too large" }] }, 422),
      ),
    );

    await expect(commitStoreLeadsImport("<table></table>")).rejects.toThrow("html too large");
  });
});
