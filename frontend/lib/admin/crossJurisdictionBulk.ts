import { chunkSourceIds } from "./bulkReview";
import type {
  BulkReviewAction,
  BulkReviewResponse,
} from "@/lib/schemas";

export interface QueueSelection {
  source_id: string;
  jurisdiction_id: string;
}

/** Group a flat list of {source_id, jurisdiction_id} selections by jurisdiction.
 *  Pure function — no I/O. */
export function groupByJurisdiction(
  selections: QueueSelection[],
): Record<string, string[]> {
  const out: Record<string, string[]> = {};
  for (const s of selections) {
    if (!out[s.jurisdiction_id]) out[s.jurisdiction_id] = [];
    out[s.jurisdiction_id].push(s.source_id);
  }
  return out;
}

interface RunArgs {
  selections: QueueSelection[];
  send: (
    jurisdictionId: string,
    chunk: string[],
  ) => Promise<BulkReviewResponse>;
}

export interface CrossJurisdictionBulkResult {
  updated: number;
  skipped: number;
  jurisdictions_touched: number;
  /** One entry per jurisdiction in the order they were processed. */
  per_jurisdiction: Array<{
    jurisdiction_id: string;
    updated: number;
    skipped: number;
  }>;
}

/** Fan a cross-jurisdiction bulk action out by jurisdiction → 50-row chunks.
 *  Sequential — keeps DB write contention low and produces deterministic
 *  per-juris results the UI can show after the run. */
export async function runCrossJurisdictionBulk({
  selections,
  send,
}: RunArgs): Promise<CrossJurisdictionBulkResult> {
  const grouped = groupByJurisdiction(selections);
  let updated = 0;
  let skipped = 0;
  const perJur: CrossJurisdictionBulkResult["per_jurisdiction"] = [];

  for (const [jid, ids] of Object.entries(grouped)) {
    let jUpdated = 0;
    let jSkipped = 0;
    for (const chunk of chunkSourceIds(ids)) {
      const res = await send(jid, chunk);
      jUpdated += res.updated;
      jSkipped += res.skipped;
    }
    updated += jUpdated;
    skipped += jSkipped;
    perJur.push({ jurisdiction_id: jid, updated: jUpdated, skipped: jSkipped });
  }

  return {
    updated,
    skipped,
    jurisdictions_touched: perJur.length,
    per_jurisdiction: perJur,
  };
}

/** Convenience type alias to keep callers tidy. */
export type CrossJurBulkAction = BulkReviewAction;
