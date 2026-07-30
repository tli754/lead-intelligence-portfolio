import { Loader2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useJobs } from "@/api/queries";
import { JobStatusBadge } from "@/components/status";
import { QueueStatsPanel } from "@/components/QueueStatsPanel";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDateTime } from "@/lib/format";
import { jobStageSchema, jobStatusSchema, type JobListFilters, type JobStage, type JobStatus } from "@/schemas/job";

const STAGE_LABELS: Record<JobStage, string> = {
  discovery: "Discovery",
  crawl: "Crawl",
  extraction: "Extraction",
  analysis: "Analysis",
  scoring: "Scoring",
};

/**
 * Read-only view of the pipeline job queue, backed by real discovery/
 * crawl/extraction run data (`useJobs` -> `fetchPipelineJobs`).
 * `analysis`/`scoring` stages always show no results — no backend
 * module exists for either yet.
 *
 * Also renders `QueueStatsPanel` above the jobs table — a separate,
 * independently-failing `useQueueStats` query surfacing live RQ/Redis
 * queue counts and worker liveness (see Task 019's feature contract).
 */
export function JobsPage() {
  const [stage, setStage] = useState<JobStage | "all">("all");
  const [status, setStatus] = useState<JobStatus | "all">("all");

  const filters: JobListFilters = useMemo(
    () => ({
      stage: stage === "all" ? undefined : stage,
      status: status === "all" ? undefined : status,
    }),
    [stage, status],
  );

  const { data, isPending, isError } = useJobs(filters);

  return (
    <main className="mx-auto flex max-w-7xl flex-col gap-6 p-8">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Jobs</h1>
        <p className="text-muted-foreground text-sm">
          Discovery, crawl, extraction, analysis and scoring jobs across the pipeline.
        </p>
      </div>

      <QueueStatsPanel />

      <div className="flex flex-wrap items-end gap-3" role="search" aria-label="Filter jobs">
        <div className="flex flex-col gap-1">
          <label htmlFor="job-stage-filter" className="text-muted-foreground text-xs font-medium">
            Stage
          </label>
          <Select
            id="job-stage-filter"
            value={stage}
            onChange={(event) => setStage(event.target.value as JobStage | "all")}
            className="w-40"
          >
            <option value="all">All stages</option>
            {jobStageSchema.options.map((option) => (
              <option key={option} value={option}>
                {STAGE_LABELS[option]}
              </option>
            ))}
          </Select>
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="job-status-filter" className="text-muted-foreground text-xs font-medium">
            Status
          </label>
          <Select
            id="job-status-filter"
            value={status}
            onChange={(event) => setStatus(event.target.value as JobStatus | "all")}
            className="w-40"
          >
            <option value="all">All statuses</option>
            {jobStatusSchema.options.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </Select>
        </div>

        {data && (
          <span className="text-muted-foreground pb-1.5 text-xs">
            {data.total} {data.total === 1 ? "job" : "jobs"}
          </span>
        )}
      </div>

      {isError && (
        <Alert variant="destructive">
          <AlertTitle>Couldn&apos;t load jobs</AlertTitle>
          <AlertDescription>Something went wrong fetching the job queue.</AlertDescription>
        </Alert>
      )}

      {isPending && (
        <div className="text-muted-foreground flex items-center gap-2 py-12 text-sm">
          <Loader2 className="size-4 animate-spin" /> Loading jobs…
        </div>
      )}

      {!isPending && data && data.items.length === 0 && (
        <p className="text-muted-foreground py-12 text-center text-sm">No jobs match these filters.</p>
      )}

      {!isPending && data && data.items.length > 0 && (
        <Table aria-label="Pipeline jobs table">
          <TableHeader>
            <TableRow>
              <TableHead>Company</TableHead>
              <TableHead>Stage</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Queued</TableHead>
              <TableHead>Started</TableHead>
              <TableHead>Finished</TableHead>
              <TableHead>Error</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.items.map((job) => (
              <TableRow key={job.job_id}>
                <TableCell>
                  <Link to={`/companies/${job.company_id}`} className="hover:underline">
                    {job.company_domain}
                  </Link>
                </TableCell>
                <TableCell>{STAGE_LABELS[job.stage]}</TableCell>
                <TableCell>
                  <JobStatusBadge status={job.status} />
                </TableCell>
                <TableCell className="text-muted-foreground">{formatDateTime(job.queued_at)}</TableCell>
                <TableCell className="text-muted-foreground">{formatDateTime(job.started_at)}</TableCell>
                <TableCell className="text-muted-foreground">{formatDateTime(job.finished_at)}</TableCell>
                <TableCell
                  className={
                    job.error_message
                      ? "text-status-critical max-w-xs text-wrap"
                      : "text-muted-foreground"
                  }
                >
                  {job.error_message ?? "—"}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </main>
  );
}
