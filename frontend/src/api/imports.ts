/**
 * Real API client for the StoreLeads HTML-table import flow
 * (`backend/app/modules/imports`), per ADR 0002
 * (`docs/decisions/0002-storeleads-import-targets-modules-imports.md`).
 *
 * Two endpoints, no server-side preview-session state: `commit` resubmits
 * the full `html` string, not row IDs from a prior `preview` call.
 */

import {
  type ImportPreviewResponse,
  type ImportResultResponse,
  importPreviewResponseSchema,
  importResultResponseSchema,
} from "@/schemas/imports";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

/** Raised when either endpoint rejects a request (e.g. blank `html`). */
export class StoreLeadsImportRequestError extends Error {}

interface FastApiValidationDetail {
  msg?: string;
}

interface FastApiErrorBody {
  detail?: string | FastApiValidationDetail[];
}

function extractErrorMessage(body: FastApiErrorBody, fallback: string): string {
  const { detail } = body;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0 && detail[0].msg) return detail[0].msg;
  return fallback;
}

async function postStoreLeadsHtml(path: string, html: string): Promise<unknown> {
  const response = await fetch(`${API_BASE_URL}/api/imports/storeleads${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ html }),
  });

  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as FastApiErrorBody;
    throw new StoreLeadsImportRequestError(
      extractErrorMessage(body, "The import request was rejected."),
    );
  }

  return response.json();
}

/** `POST /api/imports/storeleads/preview` */
export async function previewStoreLeadsImport(html: string): Promise<ImportPreviewResponse> {
  const body = await postStoreLeadsHtml("/preview", html);
  return importPreviewResponseSchema.parse(body);
}

/** `POST /api/imports/storeleads` (commit) */
export async function commitStoreLeadsImport(html: string): Promise<ImportResultResponse> {
  const body = await postStoreLeadsHtml("", html);
  return importResultResponseSchema.parse(body);
}
