import { Loader2 } from "lucide-react";
import { useState } from "react";

import { ImportRequestError, importCompanies } from "../api/companies";
import type { ImportResponse } from "../types/company";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

/**
 * The single screen of the paste-in importer feature: a textarea for
 * either a plain domain list or raw storelead.app HTML, plus the
 * created/skipped results of the most recent import.
 *
 * Results are rendered as plain text/data only — never via
 * `dangerouslySetInnerHTML` — so pasted HTML content is never reflected
 * back into the DOM unsafely.
 */
export function ImportPage() {
  const [rawText, setRawText] = useState("");
  const [quickAddValue, setQuickAddValue] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [result, setResult] = useState<ImportResponse | null>(null);

  function handleQuickAdd(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const domain = quickAddValue.trim();
    if (!domain) return;

    setRawText((prev) => (prev ? `${prev}\n${domain}` : domain));
    setQuickAddValue("");
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setErrorMessage(null);
    setResult(null);

    try {
      const response = await importCompanies(rawText);
      setResult(response);
    } catch (error) {
      const message =
        error instanceof ImportRequestError
          ? error.message
          : "Something went wrong importing this paste.";
      setErrorMessage(message);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-6 p-8">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Import leads</h1>
        <p className="text-muted-foreground text-sm">
          Paste a list of domains (one per line) or raw HTML copied from
          storelead.app&apos;s results grid.
        </p>
      </div>

      <Card>
        <CardContent className="flex flex-col gap-4">
          <form className="flex flex-col gap-2" onSubmit={handleQuickAdd}>
            <Label htmlFor="quick-add-domain">Quickly add one domain</Label>
            <div className="flex gap-2">
              <Input
                id="quick-add-domain"
                placeholder="example.com"
                value={quickAddValue}
                onChange={(event) => setQuickAddValue(event.target.value)}
              />
              <Button type="submit" variant="secondary">
                Add to paste
              </Button>
            </div>
          </form>

          <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
            <div className="flex flex-col gap-2">
              <Label htmlFor="raw-text">Paste domains or storelead.app HTML</Label>
              <Textarea
                id="raw-text"
                value={rawText}
                onChange={(event) => setRawText(event.target.value)}
                rows={12}
                className="font-mono"
              />
            </div>
            <div>
              <Button type="submit" disabled={isSubmitting}>
                {isSubmitting && <Loader2 className="animate-spin" />}
                {isSubmitting ? "Importing..." : "Import"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {errorMessage && (
        <Alert variant="destructive">
          <AlertTitle>Import failed</AlertTitle>
          <AlertDescription>{errorMessage}</AlertDescription>
        </Alert>
      )}

      {result && <ImportResultsSummary result={result} />}
    </main>
  );
}

function ImportResultsSummary({ result }: { result: ImportResponse }) {
  return (
    <Card aria-label="Import results">
      <CardHeader>
        <CardTitle>Import results</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 text-sm">
        <div className="flex flex-col gap-2">
          <p className="flex items-center gap-2">
            Detected format: <Badge variant="secondary">{result.detected_format}</Badge>
          </p>
          <p>Total rows detected: {result.total_rows_detected}</p>
          <p className="font-medium">Created: {result.created_count}</p>
        </div>

        <ResultList
          title="Skipped: duplicate in paste"
          items={result.skipped_duplicate_in_paste}
          renderItem={(domain) => domain}
          keyFor={(domain) => domain}
        />

        <ResultList
          title="Skipped: already in database"
          items={result.skipped_existing_in_db}
          renderItem={(domain) => domain}
          keyFor={(domain) => domain}
        />

        <ResultList
          title="Skipped: invalid"
          items={result.skipped_invalid}
          renderItem={(entry) => `${entry.raw_value} — ${entry.reason}`}
          keyFor={(entry) => entry.raw_value}
        />
      </CardContent>
    </Card>
  );
}

function ResultList<T>({
  title,
  items,
  renderItem,
  keyFor,
}: {
  title: string;
  items: T[];
  renderItem: (item: T) => string;
  keyFor: (item: T) => string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <h3 className="flex items-center gap-2 font-medium">
        {title} <Badge variant="outline">{items.length}</Badge>
      </h3>
      <ul className="text-muted-foreground list-inside list-disc">
        {items.map((item) => (
          <li key={keyFor(item)}>{renderItem(item)}</li>
        ))}
      </ul>
    </div>
  );
}
