import { AlertTriangle, ArrowLeft, Loader2 } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { useCompany } from "@/api/queries";
import { EvidenceViewer } from "@/components/EvidenceViewer";
import { ConfidenceMeter, ProcessingStatusBadge, WorkflowStatusBadge } from "@/components/status";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { CompanyDetailNotFoundError } from "@/api/companyDetail";
import { formatDateTime, formatScore, unknownOr } from "@/lib/format";
import type { CompanyDetail } from "@/schemas/company";

const PROCESSING_STAGE_LABELS: { key: keyof CompanyDetail["processing"]; label: string }[] = [
  { key: "latest_discovery_run", label: "Discovery" },
  { key: "latest_crawl_run", label: "Crawl" },
  { key: "latest_extraction_run", label: "Extraction" },
  { key: "latest_analysis_run", label: "Analysis" },
  { key: "latest_scoring_run", label: "Scoring" },
];

export function CompanyDetailPage() {
  const { companyId } = useParams<{ companyId: string }>();
  const { data: company, isPending, error } = useCompany(companyId);

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 p-8">
      <Link
        to="/companies"
        className="text-muted-foreground hover:text-foreground inline-flex w-fit items-center gap-1 text-sm"
      >
        <ArrowLeft className="size-4" /> Back to companies
      </Link>

      {isPending && (
        <div className="text-muted-foreground flex items-center gap-2 py-12 text-sm">
          <Loader2 className="size-4 animate-spin" /> Loading company…
        </div>
      )}

      {error && (
        <Alert variant="destructive">
          <AlertTitle>
            {error instanceof CompanyDetailNotFoundError
              ? "Company not found"
              : "Something went wrong"}
          </AlertTitle>
          <AlertDescription>
            {error instanceof CompanyDetailNotFoundError
              ? `No company matches id "${companyId}".`
              : "Couldn't load this company's details."}
          </AlertDescription>
        </Alert>
      )}

      {company && <CompanyDetailContent company={company} />}
    </main>
  );
}

function CompanyDetailContent({ company }: { company: CompanyDetail }) {
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">
            {company.identity.company_name ?? (
              <span className="text-muted-foreground italic">Unknown company</span>
            )}
          </h1>
          <ProcessingStatusBadge status={company.processing.status} />
          <WorkflowStatusBadge status={company.workflow.manual_status} />
        </div>
        <div className="text-muted-foreground flex items-center gap-2 text-sm">
          {company.url ? (
            <a href={company.url} target="_blank" rel="noreferrer" className="hover:underline">
              {company.domain}
            </a>
          ) : (
            <span>{company.domain}</span>
          )}
        </div>
      </div>

      {company.processing.status === "failed" && company.processing.failure_reason && (
        <Alert variant="destructive">
          <AlertTriangle />
          <AlertTitle>Processing failed</AlertTitle>
          <AlertDescription>{company.processing.failure_reason}</AlertDescription>
        </Alert>
      )}

      {company.processing.status === "stale" && (
        <Alert>
          <AlertTriangle />
          <AlertTitle>Analysis is stale</AlertTitle>
          <AlertDescription>
            The site was crawled more recently than it was last analysed — this score may no longer
            reflect the current site.
          </AlertDescription>
        </Alert>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="flex flex-col gap-6 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>Score</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <div className="flex items-center gap-4">
                <span
                  data-testid="score-value"
                  className="text-3xl font-semibold tabular-nums"
                >
                  {formatScore(company.score)}
                </span>
                <ConfidenceMeter level={company.confidence} />
              </div>
              {company.score_factors.length > 0 ? (
                <ul className="flex flex-col gap-2">
                  {company.score_factors.map((factor) => (
                    <li
                      key={factor.label}
                      className="text-muted-foreground flex items-center justify-between text-sm"
                    >
                      <span>{factor.label}</span>
                      <span className="text-foreground tabular-nums">{Math.round(factor.value)}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-muted-foreground text-sm">
                  Not yet scored — this company hasn&apos;t completed the pipeline.
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Evidence</CardTitle>
            </CardHeader>
            <CardContent>
              <EvidenceViewer evidence={company.evidence} />
            </CardContent>
          </Card>
        </div>

        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Identity</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="flex flex-col gap-2 text-sm">
                <DetailRow label="Platform" value={unknownOr(company.identity.platform)} />
                <DetailRow label="Country" value={unknownOr(company.identity.country)} />
                <DetailRow label="City" value={unknownOr(company.identity.city)} />
                <DetailRow
                  label="Emails"
                  value={company.emails.length > 0 ? company.emails.join(", ") : "Unknown"}
                />
                <DetailRow
                  label="Phones"
                  value={company.phones.length > 0 ? company.phones.join(", ") : "Unknown"}
                />
              </dl>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Processing timeline</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="flex flex-col gap-2 text-sm">
                {PROCESSING_STAGE_LABELS.map(({ key, label }) => (
                  <DetailRow
                    key={key}
                    label={label}
                    value={formatDateTime(company.processing[key] as string | null)}
                  />
                ))}
              </dl>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Review</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="flex flex-col gap-2 text-sm">
                <DetailRow label="Shortlisted" value={company.workflow.shortlisted ? "Yes" : "No"} />
                <DetailRow label="Notes" value={String(company.workflow.notes_count)} />
                <DetailRow label="Created" value={formatDateTime(company.created_at)} />
                <DetailRow label="Updated" value={formatDateTime(company.updated_at)} />
              </dl>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="text-foreground text-right">{value}</dd>
    </div>
  );
}
