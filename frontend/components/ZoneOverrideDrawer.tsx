"use client";

/**
 * Slide-in drawer for human override of a single zone × use cell.
 *
 * - Shows parser citations for the zone (read-only reference)
 * - Permission picker (radio): Permitted / Conditional / Prohibited / Unclear
 * - Analyst notes textarea
 * - PATCH /api/jurisdictions/:id/zones/:code on save
 */

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { ZoneRow } from "@/lib/schemas";

// ─── Types ────────────────────────────────────────────────────────────────────

type Permission = "permitted" | "conditional" | "prohibited" | "unclear";

export type UseKey =
  | "self_storage"
  | "mini_warehouse"
  | "light_industrial"
  | "luxury_garage_condo";

const USE_LABELS: Record<UseKey, string> = {
  self_storage: "Self-Storage",
  mini_warehouse: "Mini-Warehouse",
  light_industrial: "Light Industrial",
  luxury_garage_condo: "Garage Condo",
};

const PERMISSIONS: {
  value: Permission;
  label: string;
  short: string;
  ring: string;
  bg: string;
}[] = [
  {
    value: "permitted",
    label: "Permitted",
    short: "P",
    ring: "ring-emerald-400",
    bg: "bg-emerald-50 border-emerald-300 text-emerald-800",
  },
  {
    value: "conditional",
    label: "Conditional",
    short: "C",
    ring: "ring-amber-400",
    bg: "bg-amber-50 border-amber-300 text-amber-800",
  },
  {
    value: "prohibited",
    label: "Prohibited",
    short: "X",
    ring: "ring-red-400",
    bg: "bg-red-50 border-red-300 text-red-800",
  },
  {
    value: "unclear",
    label: "Unclear",
    short: "?",
    ring: "ring-slate-300",
    bg: "bg-slate-50 border-slate-200 text-slate-600",
  },
];

// ─── Props ────────────────────────────────────────────────────────────────────

interface Props {
  zone: ZoneRow;
  useKey: UseKey;
  jurisdictionId: string;
  onClose: () => void;
  onSaved: () => void;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function ZoneOverrideDrawer({
  zone,
  useKey,
  jurisdictionId,
  onClose,
  onSaved,
}: Props) {
  const queryClient = useQueryClient();
  const [permission, setPermission] = useState<Permission>(
    (zone[useKey] as Permission) ?? "unclear"
  );
  const [notes, setNotes] = useState(zone.notes ?? "");

  const isDirty =
    permission !== (zone[useKey] as Permission) ||
    notes.trim() !== (zone.notes ?? "").trim();

  const mutation = useMutation({
    mutationFn: () =>
      api.updateZone(
        jurisdictionId,
        zone.zone_code,
        {
          [useKey]: permission,
          notes: notes.trim() || null,
        },
        // Scope the PATCH to the specific city row when this zone row
        // belongs to a city under a county jurisdiction. Without this,
        // a county's per-city edit would clobber the NULL county-default
        // row instead of the intended city row.
        zone.municipality ?? null
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["zone-matrix", jurisdictionId],
      });
      onSaved();
    },
  });

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/20 backdrop-blur-[1px]"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer panel */}
      <aside className="fixed right-0 top-0 z-50 flex h-full w-96 flex-col bg-white shadow-2xl">
        {/* ── Header ── */}
        <div className="flex items-start justify-between border-b border-slate-200 px-5 py-4">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-slate-400">
              Override
            </p>
            <h2 className="mt-0.5 text-sm font-semibold text-slate-900">
              <code className="rounded bg-slate-100 px-1 text-xs">{zone.zone_code}</code>
              {zone.zone_name ? (
                <span className="ml-1.5 font-normal text-slate-600">
                  {zone.zone_name}
                </span>
              ) : null}
            </h2>
            <p className="mt-1 text-xs text-slate-400">
              {USE_LABELS[useKey]}
              {zone.municipality ? (
                <>
                  <span className="mx-1.5 text-slate-300">·</span>
                  <span className="font-medium text-slate-500">
                    {zone.municipality}
                  </span>
                </>
              ) : null}
            </p>
          </div>
          <button
            onClick={onClose}
            className="mt-0.5 rounded p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
            aria-label="Close drawer"
          >
            <svg className="h-4 w-4" viewBox="0 0 16 16" fill="currentColor">
              <path d="M4.293 4.293a1 1 0 011.414 0L8 6.586l2.293-2.293a1 1 0 111.414 1.414L9.414 8l2.293 2.293a1 1 0 01-1.414 1.414L8 9.414l-2.293 2.293a1 1 0 01-1.414-1.414L6.586 8 4.293 5.707a1 1 0 010-1.414z" />
            </svg>
          </button>
        </div>

        {/* ── Scrollable body ── */}
        <div className="flex-1 space-y-5 overflow-y-auto p-5">
          {/* Permission picker */}
          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Permission
            </h3>
            <div className="grid grid-cols-2 gap-2">
              {PERMISSIONS.map((p) => {
                const selected = permission === p.value;
                return (
                  <button
                    key={p.value}
                    type="button"
                    onClick={() => setPermission(p.value)}
                    className={[
                      "flex items-center gap-2 rounded-lg border px-3 py-2.5 text-left text-sm font-medium transition-all",
                      selected
                        ? `${p.bg} ring-2 ${p.ring}`
                        : "border-slate-200 text-slate-600 hover:bg-slate-50",
                    ].join(" ")}
                  >
                    <span
                      className={[
                        "flex h-6 w-6 shrink-0 items-center justify-center rounded border font-bold text-xs",
                        selected ? p.bg : "border-slate-300 bg-white",
                      ].join(" ")}
                    >
                      {p.short}
                    </span>
                    {p.label}
                  </button>
                );
              })}
            </div>
          </section>

          {/* Citations */}
          {zone.citations && zone.citations.length > 0 && (
            <section>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                Parser Citations
              </h3>
              <div className="space-y-2">
                {zone.citations.map((c, i) => (
                  <div
                    key={i}
                    className="rounded-lg border border-slate-100 bg-slate-50 p-3"
                  >
                    <p className="text-xs font-semibold text-slate-700">
                      {c.section}
                    </p>
                    <p className="mt-1 text-xs italic text-slate-500">
                      &ldquo;{c.quote}&rdquo;
                    </p>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Analyst notes */}
          <section>
            <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Analyst Notes
            </h3>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              placeholder="Why did you change this? (optional)"
              className="w-full resize-none rounded-lg border border-slate-200 px-3 py-2 text-sm placeholder-slate-400 focus:border-emerald-500 focus:outline-none"
            />
          </section>

          {/* Meta */}
          <div className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500">
            <div className="flex items-center justify-between">
              <span>
                Parser confidence:{" "}
                <span className="font-medium text-slate-700">
                  {zone.confidence != null
                    ? `${(zone.confidence * 100).toFixed(0)}%`
                    : "—"}
                </span>
              </span>
              {zone.human_reviewed && (
                <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700">
                  Reviewed
                </span>
              )}
            </div>
          </div>
        </div>

        {/* ── Footer ── */}
        <div className="space-y-2 border-t border-slate-200 p-4">
          {mutation.isError && (
            <p className="text-xs text-red-600">
              {(mutation.error as Error)?.message ?? "Save failed — try again."}
            </p>
          )}
          <div className="flex gap-2">
            <button
              onClick={() => mutation.mutate()}
              disabled={!isDirty || mutation.isPending}
              className="flex-1 rounded-lg bg-emerald-600 py-2 text-sm font-semibold text-white transition-colors hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {mutation.isPending ? "Saving…" : "Save Override"}
            </button>
            <button
              onClick={onClose}
              className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
            >
              Cancel
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}
