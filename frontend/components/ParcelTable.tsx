"use client";

/**
 * Right-side sortable parcel table with row selection for shortlisting.
 *
 * Phase 7: adds checkbox column and selection state.
 */

import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from "@tanstack/react-table";
import { useState } from "react";
import type { ParcelRow } from "@/lib/schemas";

const columnHelper = createColumnHelper<ParcelRow>();

interface ParcelTableProps {
  parcels: ParcelRow[];
  onRowClick?: (parcel: ParcelRow) => void;
  selectedId?: number | null;
  /** IDs checked for shortlist */
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
  const [sorting, setSorting] = useState<SortingState>([]);

  // ── Select all visible parcels ────────────────────────────────────────────
  const allVisibleIds = parcels.map((p) => p.id);
  const allChecked =
    allVisibleIds.length > 0 &&
    allVisibleIds.every((id) => selectedIds.has(id));
  const someChecked = !allChecked && allVisibleIds.some((id) => selectedIds.has(id));

  function toggleAll() {
    if (!onSelectionChange) return;
    if (allChecked) {
      const next = new Set(selectedIds);
      allVisibleIds.forEach((id) => next.delete(id));
      onSelectionChange(next);
    } else {
      const next = new Set(selectedIds);
      allVisibleIds.forEach((id) => next.add(id));
      onSelectionChange(next);
    }
  }

  function toggleOne(id: number, e: React.MouseEvent) {
    e.stopPropagation();
    if (!onSelectionChange) return;
    const next = new Set(selectedIds);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onSelectionChange(next);
  }

  // ── Columns ───────────────────────────────────────────────────────────────
  const columns = [
    // Checkbox column
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
          checked={selectedIds.has(row.original.id)}
          onChange={() => {}}
          onClick={(e) => toggleOne(row.original.id, e)}
          className="h-3.5 w-3.5 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
          aria-label={`Select parcel ${row.original.apn}`}
        />
      ),
      size: 36,
    }),
    columnHelper.accessor("apn", {
      header: "APN",
      cell: (info) => (
        <span className="font-mono text-xs">{info.getValue()}</span>
      ),
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
    columnHelper.accessor("acres", {
      header: "Acres",
      cell: (info) =>
        info.getValue() != null ? info.getValue()!.toFixed(2) : "—",
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
    data: parcels,
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
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((header) => (
                <th
                  key={header.id}
                  onClick={
                    header.id === "select"
                      ? undefined
                      : header.column.getToggleSortingHandler()
                  }
                  className={[
                    "px-3 py-2 text-left text-xs font-medium text-slate-500",
                    header.id !== "select"
                      ? "cursor-pointer select-none hover:text-slate-900"
                      : "",
                  ].join(" ")}
                  style={{ width: header.id === "select" ? 36 : undefined }}
                >
                  {flexRender(header.column.columnDef.header, header.getContext())}
                  {header.column.getIsSorted() === "asc" && " ↑"}
                  {header.column.getIsSorted() === "desc" && " ↓"}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => {
            const isSelected = selectedIds.has(row.original.id);
            return (
              <tr
                key={row.id}
                onClick={() => onRowClick?.(row.original)}
                className={[
                  "cursor-pointer border-b border-slate-100 hover:bg-slate-50",
                  selectedId === row.original.id ? "bg-emerald-50" : "",
                  isSelected ? "bg-emerald-50/50" : "",
                ].join(" ")}
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="px-3 py-2">
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
