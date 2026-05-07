"use client";

import { useMemo, useState } from "react";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  type SortingState,
  useReactTable,
} from "@tanstack/react-table";
import type { CandidateParcelRow } from "@/lib/schemas";
import {
  computeScore,
  TIER_BADGE_CLASSES,
  TIER_LABELS,
  type CompositeScore,
} from "@/lib/compositeScore";

type RowWithScore = CandidateParcelRow & { _score: CompositeScore };

const columnHelper = createColumnHelper<RowWithScore>();

interface ParcelTableProps {
  parcels: CandidateParcelRow[];
  onRowClick?: (parcel: CandidateParcelRow) => void;
  selectedId?: number | null;
  selectedIds?: Set<number>;
  onSelectionChange?: (ids: Set<number>) => void;
}

export function ParcelTable({
  parcels,
  onRowClick,
  selectedId,
  selectedIds = new Set(),
  onSelectionChange,
}: ParcelTableProps) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: "score", desc: true },
  ]);

  // Annotate every row with its composite score once per render.
  const rows = useMemo<RowWithScore[]>(
    () => parcels.map((p) => ({ ...p, _score: computeScore(p) })),
    [parcels],
  );

  const allVisibleIds = parcels.map((parcel) => parcel.parcel_id);
  const allChecked =
    allVisibleIds.length > 0 && allVisibleIds.every((id) => selectedIds.has(id));
  const someChecked =
    !allChecked && allVisibleIds.some((id) => selectedIds.has(id));

  function toggleAll() {
    if (!onSelectionChange) return;
    const next = new Set(selectedIds);
    if (allChecked) {
      allVisibleIds.forEach((id) => next.delete(id));
    } else {
      allVisibleIds.forEach((id) => next.add(id));
    }
    onSelectionChange(next);
  }

  function toggleOne(id: number, e: React.MouseEvent) {
    e.stopPropagation();
    if (!onSelectionChange) return;
    const next = new Set(selectedIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onSelectionChange(next);
  }

  const columns = [
    columnHelper.display({
      id: "select",
      header: () => (
        <input
          type="checkbox"
          checked={allChecked}
          ref={(el) => {
            if (el) el.indeterminate = someChecked;
          }}
          onChange={toggleAll}
          className="h-3.5 w-3.5 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
          aria-label="Select all"
        />
      ),
      cell: ({ row }) => (
        <input
          type="checkbox"
          checked={selectedIds.has(row.original.parcel_id)}
          onChange={() => {}}
          onClick={(e) => toggleOne(row.original.parcel_id, e)}
          className="h-3.5 w-3.5 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
          aria-label={`Select parcel ${row.original.apn}`}
        />
      ),
      size: 36,
    }),
    columnHelper.accessor((row) => row._score.score, {
      id: "score",
      header: "Score",
      sortDescFirst: true,
      cell: ({ row }) => {
        const s = row.original._score;
        return (
          <span
            className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums ${TIER_BADGE_CLASSES[s.tier]}`}
            title={`${TIER_LABELS[s.tier]} — ${s.factors.map((f) => `${f.label} ${f.delta >= 0 ? "+" : ""}${f.delta}`).join(", ")}`}
          >
            {s.score}
          </span>
        );
      },
    }),
    columnHelper.accessor("apn", {
      header: "APN",
      enableSorting: false,
      cell: (info) => <span className="font-mono text-xs">{info.getValue()}</span>,
    }),
    columnHelper.accessor("address", {
      header: "Address",
      cell: (info) =>
        info.getValue() ?? <span className="text-slate-400">—</span>,
    }),
    columnHelper.accessor("zoning_code", {
      header: "Zone",
      cell: (info) => (
        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs font-medium">
          {info.getValue() ?? "—"}
        </span>
      ),
    }),
    columnHelper.accessor("storage_permission", {
      header: "Storage",
      cell: (info) => {
        const v = info.getValue();
        if (v === "permitted")
          return <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700">Permitted</span>;
        if (v === "conditional")
          return <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">Conditional</span>;
        if (v === "unclear")
          return <span className="rounded-full bg-violet-100 px-2 py-0.5 text-xs font-medium text-violet-600">Unclear</span>;
        if (v === "prohibited")
          return <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">Prohibited</span>;
        return <span className="text-slate-300 text-xs">—</span>;
      },
    }),
    columnHelper.accessor("acres", {
      header: "Acres",
      sortDescFirst: true,
      sortUndefined: "last",
      cell: (info) =>
        info.getValue() != null ? info.getValue()!.toFixed(2) : "—",
    }),
    columnHelper.accessor("is_viable", {
      header: "Viable",
      cell: (info) =>
        info.getValue() ? (
          <span className="text-xs font-medium text-emerald-700">Yes</span>
        ) : (
          <span className="text-xs font-medium text-amber-700">Review</span>
        ),
    }),
    columnHelper.accessor("in_flood_zone", {
      header: "Flood",
      cell: (info) =>
        info.getValue() ? (
          <span className="text-xs font-medium text-red-600">Yes</span>
        ) : (
          <span className="text-xs text-slate-400">No</span>
        ),
    }),
  ];

  const table = useReactTable({
    data: rows,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  if (parcels.length === 0) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-sm text-slate-400">
        No parcels match the current filters.
      </div>
    );
  }

  return (
    <div className="overflow-auto">
      <table className="w-full text-sm">
        <thead className="sticky top-0 border-b border-slate-200 bg-white">
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map((header) => {
                const canSort = header.column.getCanSort();
                const sorted = header.column.getIsSorted();
                return (
                  <th
                    key={header.id}
                    onClick={canSort ? header.column.getToggleSortingHandler() : undefined}
                    className={[
                      "px-2 py-2 text-left text-xs font-medium text-slate-500",
                      canSort ? "cursor-pointer select-none hover:text-slate-700" : "",
                    ].join(" ")}
                    style={{ width: header.id === "select" ? 36 : undefined }}
                  >
                    <span className="inline-flex items-center gap-1">
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      {canSort && (
                        <span aria-hidden className="text-[10px] text-slate-400">
                          {sorted === "asc" ? "▲" : sorted === "desc" ? "▼" : "↕"}
                        </span>
                      )}
                    </span>
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => {
            const isSelected = selectedIds.has(row.original.parcel_id);
            return (
              <tr
                key={row.id}
                onClick={() => onRowClick?.(row.original)}
                className={[
                  "cursor-pointer border-b border-slate-100 hover:bg-slate-50",
                  selectedId === row.original.parcel_id ? "bg-emerald-50" : "",
                  isSelected ? "bg-emerald-50/50" : "",
                ].join(" ")}
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="px-2 py-2">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
