import { Loader2 } from "lucide-react";

import { useQueueStats } from "@/api/queries";
import { StatusPill } from "@/components/status";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { QueueCounts, QueueStats } from "@/schemas/queueStats";

const COUNT_LABELS: { key: keyof QueueCounts; label: string }[] = [
  { key: "queued", label: "Queued" },
  { key: "started", label: "Started" },
  { key: "finished", label: "Finished" },
  { key: "failed", label: "Failed" },
  { key: "deferred", label: "Deferred" },
  { key: "scheduled", label: "Scheduled" },
];

/** Up to this many failed job ids are shown as badges; beyond that a
 * "+N more" text suffix is appended instead of rendering every badge. */
const MAX_VISIBLE_FAILED_JOB_IDS = 8;

/**
 * Auto-refreshing (every 7s, see `useQueueStats`) snapshot of an RQ
 * queue's job counts, failed-job ids, and worker liveness — rendered
 * above the pipeline jobs table on `JobsPage`. A failure here
 * (`isError`) is scoped to this panel only: it comes from its own
 * `useQueueStats` call, entirely independent of `JobsPage`'s own
 * `useJobs` query, so it never blocks or replaces the jobs table below.
 */
export function QueueStatsPanel() {
  const { data, isPending, isError } = useQueueStats();

  return (
    <Card>
      <CardHeader>
        <CardTitle>Queue statistics</CardTitle>
      </CardHeader>
      <CardContent>
        {isError && (
          <Alert variant="destructive">
            <AlertTitle>Couldn&apos;t load queue stats</AlertTitle>
            <AlertDescription>Something went wrong fetching queue statistics.</AlertDescription>
          </Alert>
        )}

        {isPending && (
          <div className="text-muted-foreground flex items-center gap-2 text-sm">
            <Loader2 className="size-4 animate-spin" /> Loading queue stats…
          </div>
        )}

        {!isPending && !isError && data && <QueueStatsBody data={data} />}
      </CardContent>
    </Card>
  );
}

function QueueStatsBody({ data }: { data: QueueStats }) {
  const visibleFailedJobIds = data.failed_job_ids.slice(0, MAX_VISIBLE_FAILED_JOB_IDS);
  const hiddenFailedJobCount = data.counts.failed - MAX_VISIBLE_FAILED_JOB_IDS;
  const workerIsAlive = data.workers_alive >= 1;

  return (
    <div className="flex flex-col gap-4">
      <p className="text-muted-foreground text-sm">Queue: {data.queue}</p>

      <div className="flex flex-wrap gap-6">
        {COUNT_LABELS.map(({ key, label }) => (
          <div key={key} className="flex flex-col gap-0.5">
            <span className="text-muted-foreground text-xs font-medium">{label}</span>
            <span className="text-lg font-semibold">{data.counts[key]}</span>
          </div>
        ))}
      </div>

      <StatusPill
        tone={workerIsAlive ? "good" : "warning"}
        pulse={workerIsAlive}
        label={workerIsAlive ? `${data.workers_alive} worker(s) alive` : "No worker running"}
      />

      <div className="flex flex-wrap items-center gap-2">
        {visibleFailedJobIds.length === 0 ? (
          <span className="text-muted-foreground text-sm">No failed jobs</span>
        ) : (
          <>
            {visibleFailedJobIds.map((jobId) => (
              <Badge key={jobId} variant="secondary">
                {jobId}
              </Badge>
            ))}
            {data.counts.failed > MAX_VISIBLE_FAILED_JOB_IDS && (
              <span className="text-muted-foreground text-xs">+{hiddenFailedJobCount} more</span>
            )}
          </>
        )}
      </div>
    </div>
  );
}
