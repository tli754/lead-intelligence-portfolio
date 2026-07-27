import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as companiesApi from "../api/companies";
import { ImportRequestError } from "../api/companies";
import type { ImportResponse } from "../types/company";
import { ImportPage } from "./ImportPage";

afterEach(() => {
  vi.restoreAllMocks();
});

function renderPage() {
  return render(<ImportPage />);
}

describe("ImportPage", () => {
  it("renders a textarea and a submit button", () => {
    renderPage();

    expect(
      screen.getByLabelText(/paste domains or storelead\.app html/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /import/i })).toBeInTheDocument();
  });

  it("disables the submit button while a request is in flight", async () => {
    const user = userEvent.setup();
    let resolveImport: (response: ImportResponse) => void = () => {};
    vi.spyOn(companiesApi, "importCompanies").mockReturnValue(
      new Promise((resolve) => {
        resolveImport = resolve;
      }),
    );

    renderPage();
    await user.type(
      screen.getByLabelText(/paste domains or storelead\.app html/i),
      "example.com",
    );
    await user.click(screen.getByRole("button", { name: /import/i }));

    expect(screen.getByRole("button", { name: /importing/i })).toBeDisabled();

    resolveImport({
      detected_format: "domain_list",
      total_rows_detected: 1,
      created: [],
      created_count: 1,
      skipped_duplicate_in_paste: [],
      skipped_existing_in_db: [],
      skipped_invalid: [],
    });

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /^import$/i })).toBeEnabled(),
    );
  });

  it("renders created/skipped counts on a successful response", async () => {
    const user = userEvent.setup();
    vi.spyOn(companiesApi, "importCompanies").mockResolvedValue({
      detected_format: "domain_list",
      total_rows_detected: 3,
      created: [],
      created_count: 2,
      skipped_duplicate_in_paste: ["dup.com"],
      skipped_existing_in_db: [],
      skipped_invalid: [],
    });

    renderPage();
    await user.type(
      screen.getByLabelText(/paste domains or storelead\.app html/i),
      "one.com\ndup.com\ndup.com",
    );
    await user.click(screen.getByRole("button", { name: /import/i }));

    expect(await screen.findByText(/created: 2/i)).toBeInTheDocument();
    expect(screen.getByText("dup.com")).toBeInTheDocument();
  });

  it("renders the error message on a 422 response", async () => {
    const user = userEvent.setup();
    vi.spyOn(companiesApi, "importCompanies").mockRejectedValue(
      new ImportRequestError("raw_text must not be empty or whitespace-only"),
    );

    renderPage();
    await user.type(
      screen.getByLabelText(/paste domains or storelead\.app html/i),
      "   ",
    );
    await user.click(screen.getByRole("button", { name: /import/i }));

    expect(
      await screen.findByText(/raw_text must not be empty or whitespace-only/i),
    ).toBeInTheDocument();
  });

  it("appends a quick-added domain to the paste textarea without submitting", async () => {
    const user = userEvent.setup();
    const importSpy = vi.spyOn(companiesApi, "importCompanies");

    renderPage();
    const textarea = screen.getByLabelText<HTMLTextAreaElement>(
      /paste domains or storelead\.app html/i,
    );
    await user.type(textarea, "one.com");
    await user.type(screen.getByLabelText(/quickly add one domain/i), "two.com");
    await user.click(screen.getByRole("button", { name: /add to paste/i }));

    expect(textarea).toHaveValue("one.com\ntwo.com");
    expect(screen.getByLabelText(/quickly add one domain/i)).toHaveValue("");
    expect(importSpy).not.toHaveBeenCalled();
  });
});
