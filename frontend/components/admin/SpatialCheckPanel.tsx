"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { SpatialCheckResponse } from "@/lib/schemas";
import { VerdictPill } from "./StatusPill";

interface Props {
  jurisdictionId: string;
  sourceId: string;
  /** When false the panel won't fetch — used to lazy-load on drawer open. */
  enabled?: boolean;
}

export function SpatialCheckPanel({
  jurisdictionId,
  sourceId,
  enabled = true,
}: Props) {
  const query = useQuery({
    queryKey: ["spatial-check", jurisdictionId, sourceId],
    queryFn: () => api.getSpatialCheck(jurisdictionId, sourceId),
    enabled,
    staleTime: 60 * 1000,
    retry: 0,
  });

  if (query.isPending) {
    return (
      <p className="text-xs italic text-slate-400">Running spatial check…</p>
    );
  }
  if (query.isError) {
    return (
      <p className="text-xs text-rose-600">
        {(query.error as Error)?.message ?? "Spatial check failed."}
      </p>
    );
  }

  return <SpatialCheckBody data={query.data!} />;
}

function SpatialCheckBody({ data }: { data: SpatialCheckResponse }) {
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-xs">
        <VerdictPill verdict={data.verdict} />
        {data.bbox_overlap_ratio != null && (
          <span className="font-mono text-slate-600">
            overlap = {(data.bbox_overlap_ratio * 100).toFixed(1)}%
          </span>
        )}
        {data.layer_extent_srid != null && (
          <span className="font-mono text-slate-500">
            SRID {data.layer_extent_srid}
          </span>
        )}
      </div>

      {data.error && (
        <p className="rounded-md border border-rose-200 bg-rose-50 px-2 py-1 text-[11px] text-rose-700">
          {data.error}
        </p>
      )}

      <BboxView
        jurisdictionBbox={data.jurisdiction_bbox}
        layerBbox={data.layer_extent_wgs84}
      />

      <dl className="grid grid-cols-[120px_1fr] gap-x-3 gap-y-1 text-[11px] font-mono text-slate-600">
        <dt className="text-slate-400">jurisdiction</dt>
        <dd>{fmtBbox(data.jurisdiction_bbox)}</dd>
        <dt className="text-slate-400">layer (wgs84)</dt>
        <dd>{fmtBbox(data.layer_extent_wgs84)}</dd>
        <dt className="text-slate-400">layer (raw)</dt>
        <dd>{fmtBbox(data.layer_extent_raw)}</dd>
      </dl>
    </div>
  );
}

function fmtBbox(b: number[] | null): string {
  if (!b || b.length !== 4) return "—";
  return b.map((n) => n.toFixed(3)).join(", ");
}

function BboxView({
  jurisdictionBbox,
  layerBbox,
}: {
  jurisdictionBbox: number[] | null;
  layerBbox: number[] | null;
}) {
  if (!jurisdictionBbox && !layerBbox) {
    return (
      <p className="text-[11px] italic text-slate-400">
        No bboxes available to render.
      </p>
    );
  }
  const boxes = [jurisdictionBbox, layerBbox].filter(
    (b): b is number[] => Array.isArray(b) && b.length === 4,
  );
  const xs = boxes.flatMap((b) => [b[0], b[2]]);
  const ys = boxes.flatMap((b) => [b[1], b[3]]);
  const xmin = Math.min(...xs);
  const xmax = Math.max(...xs);
  const ymin = Math.min(...ys);
  const ymax = Math.max(...ys);
  // Pad 5% on each side so rects don't kiss the edge.
  const w = Math.max(xmax - xmin, 0.0001);
  const h = Math.max(ymax - ymin, 0.0001);
  const padX = w * 0.05;
  const padY = h * 0.05;
  const vbx = xmin - padX;
  const vby = ymin - padY;
  const vbw = w + padX * 2;
  const vbh = h + padY * 2;

  const project = (b: number[]) => ({
    x: b[0],
    y: ymin + ymax - b[3], // flip Y for SVG (north up)
    w: b[2] - b[0],
    h: b[3] - b[1],
  });

  return (
    <svg
      viewBox={`${vbx} ${vby} ${vbw} ${vbh}`}
      className="block h-44 w-full rounded-md border border-slate-200 bg-slate-50"
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="bbox overlap"
    >
      {jurisdictionBbox && (() => {
        const r = project(jurisdictionBbox);
        return (
          <rect
            x={r.x}
            y={r.y}
            width={r.w}
            height={r.h}
            fill="rgba(16, 185, 129, 0.15)"
            stroke="#10b981"
            strokeWidth={vbw / 200}
          />
        );
      })()}
      {layerBbox && (() => {
        const r = project(layerBbox);
        return (
          <rect
            x={r.x}
            y={r.y}
            width={r.w}
            height={r.h}
            fill="rgba(244, 63, 94, 0.10)"
            stroke="#f43f5e"
            strokeWidth={vbw / 200}
            strokeDasharray={`${vbw / 80} ${vbw / 160}`}
          />
        );
      })()}
    </svg>
  );
}
