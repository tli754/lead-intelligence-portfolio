import {
  type SortingState,
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ArrowUpDown, Loader2 } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ConfidenceMeter, ProcessingStatusBadge, WorkflowStatusBadge } from "@/components/status";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatDate, formatScore, unknownOr } from "@/lib/format";
import { useCompanies } from "@/api/queries";
import type { CompanyListFilters, CompanyListItem, ProcessingStatus, WorkflowStatus } from "@/schemas/company";
import { processingStatusSchema, workflowStatusSchema } from "@/schemas/company";
import { cn } from "@/lib/utils";

const PLATFORM_OPTIONS = ["Shopify", "WooCommerce", "BigCommerce"];

const columnHelper = createColumnHelper<CompanyListItem>();

/**
 * The company ranking table, backed by the real `GET /api/companies`
 * endpoint (`listCompanies` in `src/api/companies.ts`). Processing
 * status, workflow status, and platform filters are sent as query
 * params. The search box (`q`) is a known gap: the real endpoint has no
 * free-text search, so typing here has no effect on the results — see
 * the "Filters" section of the companies-list-to-real-api feature
 * contract. Column sorting is handled client-side by TanStack Table
 * over whatever page of results the API returned.
 */
export function CompaniesPage() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [processingStatus, setProcessingStatus] = useState<ProcessingStatus | "all">("all");
  const [workflowStatus, setWorkflowStatus] = useState<WorkflowStatus | "all">("all");
  const [platform, setPlatform] = useState<string>("all");
  const [sorting, setSorting] = useState<SortingState>([{ id: "score", desc: true }]);

  const filters: CompanyListFilters = useMemo(
    () => ({
      q: q.trim() || undefined,
      processing_status: processingStatus === "all" ? undefined : processingStatus,
      workflow_status: workflowStatus === "all" ? undefined : workflowStatus,
      platform: platform === "all" ? undefined : platform,
    }),
    [q, processingStatus, workflowStatus, platform],
  );

  const { data, isPending, isError } = useCompanies(filters);

  const columns = useMemo(
    () => [
      columnHelper.accessor((row) => row.identity.company_name ?? row.domain, {
        id: "company",
        header: "Company",
        cell: ({ row }) => (
          <Link to={`/companies/${row.original.company_id}`} className="flex flex-col hover:underline">
            <span className="text-foreground font-medium">
              {row.original.identity.company_name ?? (
                <span className="text-muted-foreground italic">Unknown</span>
              )}
            </span>
            <span className="text-muted-foreground text-xs">{row.original.domain}</span>
          </Link>
        ),
      }),
      columnHelper.accessor((row) => row.identity.platform ?? "", {
        id: "platform",
        header: "Platform",
        cell: ({ row }) => unknownOr(row.original.identity.platform),
      }),
      columnHelper.accessor((row) => row.identity.country ?? "", {
        id: "country",
        header: "Country",
        cell: ({ row }) => unknownOr(row.original.identity.country),
      }),
      columnHelper.accessor((row) => row.processing.status, {
        id: "processing_status",
        header: "Processing",
        cell: ({ row }) => <ProcessingStatusBadge status={row.original.processing.status} />,
      }),
      columnHelper.accessor((row) => row.workflow.manual_status, {
        id: "workflow_status",
        header: "Review",
        cell: ({ row }) => <WorkflowStatusBadge status={row.original.workflow.manual_status} />,
      }),
      columnHelper.accessor((row) => row.score ?? -1, {
        id: "score",
        header: "Score",
        cell: ({ row }) => (
          <span className="font-medium tabular-nums">{formatScore(row.original.score)}</span>
        ),
      }),
      columnHelper.accessor((row) => row.confidence ?? "", {
        id: "confidence",
        header: "Confidence",
        cell: ({ row }) => <ConfidenceMeter level={row.original.confidence} />,
      }),
      columnHelper.accessor((row) => row.updated_at, {
        id: "updated_at",
        header: "Updated",
        cell: ({ row }) => (
          <span className="text-muted-foreground tabular-nums">
            {formatDate(row.original.updated_at)}
          </span>
        ),
      }),
    ],
    [],
  );

  const table = useReactTable({
    data: data?.items ?? [],
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  return (
    <main className="mx-auto flex max-w-7xl flex-col gap-6 p-8">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Companies</h1>
        <p className="text-muted-foreground text-sm">
          Ranked by score. Click a row to see the full evidence behind it.
        </p>
      </div>

      <div className="flex flex-wrap items-end gap-3" role="search" aria-label="Filter companies">
        <div className="flex flex-col gap-1">
          <label htmlFor="company-search" className="text-muted-foreground text-xs font-medium">
            Search
          </label>
          <Input
            id="company-search"
            placeholder="Domain or company name"
            value={q}
            onChange={(event) => setQ(event.target.value)}
            className="w-56"
          />
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="processing-status-filter" className="text-muted-foreground text-xs font-medium">
            Processing status
          </label>
          <Select
            id="processing-status-filter"
            value={processingStatus}
            onChange={(event) =>
              setProcessingStatus(event.target.value as ProcessingStatus | "all")
            }
            className="w-44"
          >
            <option value="all">All statuses</option>
            {processingStatusSchema.options.map((status) => (
              <option key={status} value={status}>
                {status}
              </option>
            ))}
          </Select>
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="workflow-status-filter" className="text-muted-foreground text-xs font-medium">
            Review status
          </label>
          <Select
            id="workflow-status-filter"
            value={workflowStatus}
            onChange={(event) => setWorkflowStatus(event.target.value as WorkflowStatus | "all")}
            className="w-44"
          >
            <option value="all">All statuses</option>
            {workflowStatusSchema.options.map((status) => (
              <option key={status} value={status}>
                {status}
              </option>
            ))}
          </Select>
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="platform-filter" className="text-muted-foreground text-xs font-medium">
            Platform
          </label>
          <Select
            id="platform-filter"
            value={platform}
            onChange={(event) => setPlatform(event.target.value)}
            className="w-40"
          >
            <option value="all">All platforms</option>
            {PLATFORM_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </Select>
        </div>

        {data && (
          <span className="text-muted-foreground pb-1.5 text-xs">
            {data.total} {data.total === 1 ? "company" : "companies"}
          </span>
        )}
      </div>

      {isError && (
        <Alert variant="destructive">
          <AlertTitle>Couldn&apos;t load companies</AlertTitle>
          <AlertDescription>Something went wrong fetching the ranking table.</AlertDescription>
        </Alert>
      )}

      {isPending && (
        <div className="text-muted-foreground flex items-center gap-2 py-12 text-sm">
          <Loader2 className="size-4 animate-spin" /> Loading companies…
        </div>
      )}

      {!isPending && data && data.items.length === 0 && (
        <p className="text-muted-foreground py-12 text-center text-sm">
          No companies match these filters.
        </p>
      )}

      {!isPending && data && data.items.length > 0 && (
        <Table aria-label="Company ranking table">
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id}>
                {headerGroup.headers.map((header) => {
                  const sortDirection = header.column.getIsSorted();
                  return (
                    <TableHead key={header.id}>
                      <button
                        type="button"
                        className={cn(
                          "flex items-center gap-1",
                          header.column.getCanSort() && "hover:text-foreground cursor-pointer",
                        )}
                        onClick={header.column.getToggleSortingHandler()}
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {header.column.getCanSort() &&
                          (sortDirection === "asc" ? (
                            <ArrowUp className="size-3" />
                          ) : sortDirection === "desc" ? (
                            <ArrowDown className="size-3" />
                          ) : (
                            <ArrowUpDown className="size-3 opacity-40" />
                          ))}
                      </button>
                    </TableHead>
                  );
                })}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.map((row) => (
              <TableRow
                key={row.id}
                className="cursor-pointer"
                onClick={() => navigate(`/companies/${row.original.company_id}`)}
              >
                {row.getVisibleCells().map((cell) => (
                  <TableCell key={cell.id}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </main>
  );
}
