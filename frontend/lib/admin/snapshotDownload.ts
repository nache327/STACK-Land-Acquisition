import type { RescoreResponse, RescoreSnapshot } from "@/lib/schemas";

/** Browser-only helper to save a rescore snapshot as JSON the operator can
 *  re-upload to `_rescore-rollback`. Uses an in-memory blob URL — no server
 *  round-trip. Caller is responsible for invoking this from a click handler.
 */
export function downloadRescoreSnapshot(
  res: RescoreResponse,
  filenamePrefix: string = "rescore-snapshot",
): void {
  const snapshots: RescoreSnapshot[] = res.changes
    .filter((c) => c.applied)
    .map((c) => c.before);

  if (snapshots.length === 0) return;

  const payload = {
    jurisdiction_id: res.jurisdiction_id,
    jurisdiction_name: res.jurisdiction_name,
    captured_at: new Date().toISOString(),
    summary: res.summary,
    snapshots,
  };

  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const filename = `${filenamePrefix}-${res.jurisdiction_name.replace(/\s+/g, "_")}-${Date.now()}.json`;

  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  // Give the browser a frame to start the download before revoking.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Try to parse a pasted JSON blob into a `snapshots[]` payload suitable for
 *  the rollback endpoint. Accepts either the full export from
 *  `downloadRescoreSnapshot` or a bare array of snapshots. */
export function parseRollbackInput(raw: string): RescoreSnapshot[] {
  const parsed = JSON.parse(raw);
  if (Array.isArray(parsed)) return parsed as RescoreSnapshot[];
  if (parsed && typeof parsed === "object" && Array.isArray(parsed.snapshots)) {
    return parsed.snapshots as RescoreSnapshot[];
  }
  throw new Error("Expected an array of snapshots or { snapshots: [...] }");
}
