import { Loader2 } from "lucide-react";
import { useState } from "react";

import { StoreLeadsImportRequestError } from "../api/imports";
import { useStoreLeadsCommit, useStoreLeadsPreview } from "../api/queries";
import type { ImportPreviewResponse, ImportResultResponse, ImportRow } from "../schemas/imports";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";

/**
 * The StoreLeads HTML-table import flow: paste -> preview -> commit,
 * against `modules/imports`' preview/commit endpoints (ADR 0002). There is
 * no server-side preview-session state — commit resubmits the full pasted
 * HTML, not row IDs — so this page tracks `previewedHtml` and gates
 * "Confirm import" on the live textarea matching what was last previewed.
 *
 * Results are rendered as plain text/data only — never via
 * `dangerouslySetInnerHTML` — so pasted HTML content is never reflected
 * back into the DOM unsafely.
 */
export function ImportPage() {
  const [rawText, setRawText] = useState("");
  const [previewedHtml, setPreviewedHtml] = useState<string | null>(null);
  const preview = useStoreLeadsPreview();
  const commit = useStoreLeadsCommit();

  const isStale = previewedHtml !== null && rawText !== previewedHtml;
  const canPreview = rawText.trim().length > 0 && !preview.isPending;
  const canCommit = preview.isSuccess && !isStale && previewedHtml !== null && !commit.isPending;

  function handlePreview(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!rawText.trim()) return;

    commit.reset();
    preview.mutate(rawText, {
      onSuccess: () => setPreviewedHtml(rawText),
    });
  }

  function handleConfirm() {
    if (previewedHtml === null) return;
    commit.mutate(previewedHtml);
  }

  function handleStartOver() {
    setRawText("");
    setPreviewedHtml(null);
    preview.reset();
    commit.reset();
  }

  const showStartOver = previewedHtml !== null || commit.isSuccess;

  return (
    <main className="mx-auto flex max-w-7xl flex-col gap-6 p-8">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Import leads</h1>
        <p className="text-muted-foreground text-sm">
          Paste an HTML table copied from StoreLeads. Preview the parsed rows
          before confirming the import.
        </p>
      </div>

      <Card>
        <CardContent className="flex flex-col gap-4">
          <form className="flex flex-col gap-4" onSubmit={handlePreview}>
            <div className="flex flex-col gap-2">
              <Label htmlFor="storeleads-html">Paste StoreLeads HTML table</Label>
              <Textarea
                id="storeleads-html"
                value={rawText}
                onChange={(event) => setRawText(event.target.value)}
                rows={12}
                className="font-mono"
              />
            </div>
            <div className="flex gap-2">
              <Button type="submit" disabled={!canPreview}>
                {preview.isPending && <Loader2 className="animate-spin" />}
                {preview.isPending ? "Previewing..." : "Preview"}
              </Button>
              {showStartOver && (
                <Button type="button" variant="secondary" onClick={handleStartOver}>
                  Start over
                </Button>
              )}
            </div>
          </form>
        </CardContent>
      </Card>

      {preview.isError && (
        <Alert variant="destructive">
          <AlertTitle>Preview failed</AlertTitle>
          <AlertDescription>{errorMessage(preview.error)}</AlertDescription>
        </Alert>
      )}

      {preview.isSuccess && !commit.isSuccess && (
        <ImportPreviewSection
          preview={preview.data}
          isStale={isStale}
          canCommit={canCommit}
          committing={commit.isPending}
          onConfirm={handleConfirm}
        />
      )}

      {commit.isError && (
        <Alert variant="destructive">
          <AlertTitle>Import failed</AlertTitle>
          <AlertDescription>{errorMessage(commit.error)}</AlertDescription>
        </Alert>
      )}

      {commit.isSuccess && <ImportResultSection result={commit.data} />}
    </main>
  );
}

function errorMessage(error: unknown): string {
  return error instanceof StoreLeadsImportRequestError
    ? error.message
    : "Something went wrong importing this paste.";
}

function ImportPreviewSection({
  preview,
  isStale,
  canCommit,
  committing,
  onConfirm,
}: {
  preview: ImportPreviewResponse;
  isStale: boolean;
  canCommit: boolean;
  committing: boolean;
  onConfirm: () => void;
}) {
  const { summary, rows } = preview.data;

  return (
    <Card aria-label="Import preview">
      <CardHeader>
        <CardTitle>Preview</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-wrap gap-2 text-sm">
          <Badge variant="outline">Rows found: {summary.rowsFound}</Badge>
          <Badge variant="outline">Valid: {summary.validRows}</Badge>
          <Badge variant="outline">Invalid: {summary.invalidRows}</Badge>
          <Badge variant="outline">Existing: {summary.existingCompanies}</Badge>
          <Badge variant="outline">Duplicates in file: {summary.duplicateRowsInFile}</Badge>
          <Badge variant="outline">Importable: {summary.importableRows}</Badge>
        </div>

        <ImportRowTable rows={rows} />

        <div className="flex flex-col gap-2">
          {isStale && (
            <p className="text-muted-foreground text-sm">
              Textarea changed since preview — preview again.
            </p>
          )}
          <div>
            <Button type="button" disabled={!canCommit} onClick={onConfirm}>
              {committing && <Loader2 className="animate-spin" />}
              {committing ? "Importing..." : "Confirm import"}
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function ImportResultSection({ result }: { result: ImportResultResponse }) {
  const { created, skippedExisting, skippedInvalid, failed, rows } = result.data;

  return (
    <Card aria-label="Import results">
      <CardHeader>
        <CardTitle>Import results</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex flex-wrap gap-2 text-sm">
          <Badge>Created: {created}</Badge>
          <Badge variant="secondary">Skipped (existing): {skippedExisting}</Badge>
          <Badge variant="secondary">Skipped (invalid): {skippedInvalid}</Badge>
          <Badge variant="destructive">Failed: {failed}</Badge>
        </div>

        <ImportRowTable rows={rows} />
      </CardContent>
    </Card>
  );
}

function validationBadgeVariant(status: ImportRow["validationStatus"]) {
  return status === "invalid" ? "destructive" : "secondary";
}

function duplicateBadgeVariant(status: ImportRow["duplicateStatus"]) {
  if (status === "duplicate_in_file") return "destructive";
  if (status === "existing") return "secondary";
  return "outline";
}

function outcomeBadgeVariant(outcome: ImportRow["outcome"]) {
  if (outcome === "created") return "default";
  if (outcome === "failed") return "destructive";
  return "secondary";
}

function ImportRowTable({ rows }: { rows: ImportRow[] }) {
  const hasOutcomes = rows.some((row) => row.outcome !== null);

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Row</TableHead>
          <TableHead>Website</TableHead>
          <TableHead>Domain</TableHead>
          <TableHead>Platform</TableHead>
          <TableHead>Country</TableHead>
          <TableHead>City</TableHead>
          <TableHead>Validation</TableHead>
          <TableHead>Duplicate</TableHead>
          {hasOutcomes && <TableHead>Outcome</TableHead>}
          <TableHead>Errors</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => (
          <TableRow key={row.rowNumber}>
            <TableCell>{row.rowNumber}</TableCell>
            <TableCell>{row.website ?? "—"}</TableCell>
            <TableCell className="text-muted-foreground">
              {row.normalizedDomain ?? "—"}
            </TableCell>
            <TableCell>
              {row.platform ? (
                <Badge variant="secondary">{row.platform}</Badge>
              ) : (
                <Badge variant="outline">unknown</Badge>
              )}
            </TableCell>
            <TableCell>{row.country ?? "—"}</TableCell>
            <TableCell>{row.city ?? "—"}</TableCell>
            <TableCell>
              <Badge variant={validationBadgeVariant(row.validationStatus)}>
                {row.validationStatus}
              </Badge>
            </TableCell>
            <TableCell>
              <Badge variant={duplicateBadgeVariant(row.duplicateStatus)}>
                {row.duplicateStatus}
              </Badge>
            </TableCell>
            {hasOutcomes && (
              <TableCell>
                {row.outcome && (
                  <Badge variant={outcomeBadgeVariant(row.outcome)}>{row.outcome}</Badge>
                )}
              </TableCell>
            )}
            <TableCell>
              {row.errors.length > 0 && (
                <ul className="text-destructive list-inside list-disc text-xs">
                  {row.errors.map((error, index) => (
                    <li key={index}>{error.message}</li>
                  ))}
                </ul>
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
