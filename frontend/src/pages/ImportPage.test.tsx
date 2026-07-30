import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as importsApi from "../api/imports";
import { StoreLeadsImportRequestError } from "../api/imports";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { ImportPreviewResponse, ImportResultResponse } from "../schemas/imports";
import { ImportPage } from "./ImportPage";

afterEach(() => {
  vi.restoreAllMocks();
});

function renderPage() {
  return renderWithProviders(<ImportPage />);
}

function previewFixture(overrides: Partial<ImportPreviewResponse["data"]> = {}): ImportPreviewResponse {
  return {
    data: {
      summary: {
        rowsFound: 2,
        validRows: 1,
        invalidRows: 1,
        existingCompanies: 0,
        duplicateRowsInFile: 0,
        importableRows: 1,
      },
      rows: [
        {
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
        },
        {
          rowNumber: 2,
          website: "not-a-domain",
          normalizedDomain: null,
          platform: null,
          country: null,
          city: null,
          validationStatus: "invalid",
          errors: [{ field: "website", message: "malformed host" }],
          duplicateStatus: "unknown",
          outcome: null,
        },
      ],
      ...overrides,
    },
  };
}

function commitFixture(overrides: Partial<ImportResultResponse["data"]> = {}): ImportResultResponse {
  return {
    data: {
      created: 1,
      skippedExisting: 0,
      skippedInvalid: 1,
      failed: 0,
      rows: [
        {
          rowNumber: 1,
          website: "https://www.summitoutfitters.com",
          normalizedDomain: "summitoutfitters.com",
          platform: "shopify",
          country: "United States",
          city: "Denver",
          validationStatus: "valid",
          errors: [],
          duplicateStatus: "new",
          outcome: "created",
        },
        {
          rowNumber: 2,
          website: "not-a-domain",
          normalizedDomain: null,
          platform: null,
          country: null,
          city: null,
          validationStatus: "invalid",
          errors: [{ field: "website", message: "malformed host" }],
          duplicateStatus: "unknown",
          outcome: "skipped_invalid",
        },
      ],
      ...overrides,
    },
  };
}

describe("ImportPage", () => {
  it("renders a textarea and a preview button, with confirm import absent", () => {
    renderPage();

    expect(screen.getByLabelText(/paste storeleads html table/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^preview$/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /confirm import/i })).not.toBeInTheDocument();
  });

  it("disables the preview button while blank", () => {
    renderPage();

    expect(screen.getByRole("button", { name: /^preview$/i })).toBeDisabled();
  });

  it("shows a spinner and disables preview while a preview request is in flight", async () => {
    const user = userEvent.setup();
    let resolvePreview: (response: ImportPreviewResponse) => void = () => {};
    vi.spyOn(importsApi, "previewStoreLeadsImport").mockReturnValue(
      new Promise((resolve) => {
        resolvePreview = resolve;
      }),
    );

    renderPage();
    await user.type(screen.getByLabelText(/paste storeleads html table/i), "<table></table>");
    await user.click(screen.getByRole("button", { name: /^preview$/i }));

    expect(screen.getByRole("button", { name: /previewing/i })).toBeDisabled();

    resolvePreview(previewFixture());

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /^preview$/i })).toBeEnabled(),
    );
  });

  it("shows a spinner and disables confirm import while a commit request is in flight", async () => {
    const user = userEvent.setup();
    vi.spyOn(importsApi, "previewStoreLeadsImport").mockResolvedValue(previewFixture());
    let resolveCommit: (response: ImportResultResponse) => void = () => {};
    vi.spyOn(importsApi, "commitStoreLeadsImport").mockReturnValue(
      new Promise((resolve) => {
        resolveCommit = resolve;
      }),
    );

    renderPage();
    await user.type(screen.getByLabelText(/paste storeleads html table/i), "<table></table>");
    await user.click(screen.getByRole("button", { name: /^preview$/i }));
    await user.click(await screen.findByRole("button", { name: /confirm import/i }));

    expect(screen.getByRole("button", { name: /importing/i })).toBeDisabled();

    resolveCommit(commitFixture());

    await waitFor(() =>
      expect(screen.getByText(/created: 1/i)).toBeInTheDocument(),
    );
  });

  it("renders summary counts and per-row badges/errors on a successful preview", async () => {
    const user = userEvent.setup();
    vi.spyOn(importsApi, "previewStoreLeadsImport").mockResolvedValue(previewFixture());

    renderPage();
    await user.type(screen.getByLabelText(/paste storeleads html table/i), "<table></table>");
    await user.click(screen.getByRole("button", { name: /^preview$/i }));

    expect(await screen.findByText(/rows found: 2/i)).toBeInTheDocument();
    expect(screen.getByText("summitoutfitters.com")).toBeInTheDocument();
    expect(screen.getByText("malformed host")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /confirm import/i })).toBeEnabled();
  });

  it("renders an explicit unknown-platform badge instead of blank/inferred text", async () => {
    const user = userEvent.setup();
    vi.spyOn(importsApi, "previewStoreLeadsImport").mockResolvedValue(previewFixture());

    renderPage();
    await user.type(screen.getByLabelText(/paste storeleads html table/i), "<table></table>");
    await user.click(screen.getByRole("button", { name: /^preview$/i }));

    await screen.findByText(/rows found: 2/i);
    expect(screen.getAllByText("unknown").length).toBeGreaterThan(0);
  });

  it("renders the error message on a preview failure", async () => {
    const user = userEvent.setup();
    vi.spyOn(importsApi, "previewStoreLeadsImport").mockRejectedValue(
      new StoreLeadsImportRequestError("the pasted table could not be parsed"),
    );

    renderPage();
    await user.type(screen.getByLabelText(/paste storeleads html table/i), "<table></table>");
    await user.click(screen.getByRole("button", { name: /^preview$/i }));

    expect(await screen.findByText(/the pasted table could not be parsed/i)).toBeInTheDocument();
  });

  it("disables confirm import and shows a hint when the textarea changes after preview", async () => {
    const user = userEvent.setup();
    vi.spyOn(importsApi, "previewStoreLeadsImport").mockResolvedValue(previewFixture());

    renderPage();
    const textarea = screen.getByLabelText(/paste storeleads html table/i);
    await user.type(textarea, "<table></table>");
    await user.click(screen.getByRole("button", { name: /^preview$/i }));
    await screen.findByRole("button", { name: /confirm import/i });

    await user.type(textarea, " more");

    expect(screen.getByRole("button", { name: /confirm import/i })).toBeDisabled();
    expect(screen.getByText(/preview again/i)).toBeInTheDocument();
  });

  it("commits the previewed html and renders every outcome value on success", async () => {
    const user = userEvent.setup();
    vi.spyOn(importsApi, "previewStoreLeadsImport").mockResolvedValue(previewFixture());
    const commitSpy = vi
      .spyOn(importsApi, "commitStoreLeadsImport")
      .mockResolvedValue(
        commitFixture({
          skippedExisting: 1,
          failed: 1,
          rows: [
            { ...commitFixture().data.rows[0], outcome: "created" },
            { ...commitFixture().data.rows[1], outcome: "skipped_invalid" },
            { ...commitFixture().data.rows[0], rowNumber: 3, outcome: "skipped_existing" },
            { ...commitFixture().data.rows[0], rowNumber: 4, outcome: "failed" },
          ],
        }),
      );

    renderPage();
    await user.type(screen.getByLabelText(/paste storeleads html table/i), "<table></table>");
    await user.click(screen.getByRole("button", { name: /^preview$/i }));
    await user.click(await screen.findByRole("button", { name: /confirm import/i }));

    expect(commitSpy.mock.calls[0][0]).toBe("<table></table>");
    expect(await screen.findByText(/created: 1/i)).toBeInTheDocument();
    expect(screen.getByText("created")).toBeInTheDocument();
    expect(screen.getByText("skipped_invalid")).toBeInTheDocument();
    expect(screen.getByText("skipped_existing")).toBeInTheDocument();
    expect(screen.getByText("failed")).toBeInTheDocument();
  });

  it("renders the error message on a commit failure", async () => {
    const user = userEvent.setup();
    vi.spyOn(importsApi, "previewStoreLeadsImport").mockResolvedValue(previewFixture());
    vi.spyOn(importsApi, "commitStoreLeadsImport").mockRejectedValue(
      new StoreLeadsImportRequestError("the commit request was rejected by the server"),
    );

    renderPage();
    await user.type(screen.getByLabelText(/paste storeleads html table/i), "<table></table>");
    await user.click(screen.getByRole("button", { name: /^preview$/i }));
    await user.click(await screen.findByRole("button", { name: /confirm import/i }));

    expect(
      await screen.findByText(/the commit request was rejected by the server/i),
    ).toBeInTheDocument();
  });

  it("resets the textarea and results when start over is clicked", async () => {
    const user = userEvent.setup();
    vi.spyOn(importsApi, "previewStoreLeadsImport").mockResolvedValue(previewFixture());

    renderPage();
    const textarea = screen.getByLabelText<HTMLTextAreaElement>(/paste storeleads html table/i);
    await user.type(textarea, "<table></table>");
    await user.click(screen.getByRole("button", { name: /^preview$/i }));
    await screen.findByRole("button", { name: /confirm import/i });

    await user.click(screen.getByRole("button", { name: /start over/i }));

    expect(textarea).toHaveValue("");
    expect(screen.queryByRole("button", { name: /confirm import/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /start over/i })).not.toBeInTheDocument();
  });
});
